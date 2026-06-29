# ============================================================
# USASpending.gov → Supabase contract_awards table
# ============================================================
# Dependencies: requests pandas supabase rapidfuzz
# Secrets required (GitHub Actions → Settings → Secrets):
#   SUPABASE_URL
#   SUPABASE_KEY
# ============================================================

import os
import sys
import requests
import pandas as pd
from supabase import create_client
from rapidfuzz import process, fuzz
from datetime import datetime, timedelta
import time

# ── Config ───────────────────────────────────────────────────
SUPABASE_URL    = os.environ.get("SUPABASE_URL")
SUPABASE_KEY    = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: SUPABASE_URL and SUPABASE_KEY must be set as environment variables.")
    sys.exit(1)

BASE_URL        = "https://api.usaspending.gov/api/v2"
DAYS_BACK       = 2
PAGE_LIMIT      = 100
MATCH_THRESHOLD = 85    # fuzzy match confidence %
BATCH_SIZE      = 500

# ── Date range ───────────────────────────────────────────────
end_date   = datetime.today()
start_date = end_date - timedelta(days=DAYS_BACK)
date_start = start_date.strftime("%Y-%m-%d")
date_end   = end_date.strftime("%Y-%m-%d")

# ── Connect to Supabase ──────────────────────────────────────
print("Connecting to Supabase...")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
print("✓ Connected")

# ── Load public companies from Supabase ──────────────────────
print("\nLoading public companies from Supabase...")
companies_resp = supabase.table("public_companies").select("ticker, title").execute()
companies_df   = pd.DataFrame(companies_resp.data)

# Normalize titles for matching
companies_df["title_clean"] = (
    companies_df["title"]
    .str.lower()
    .str.replace(r"\b(inc|corp|llc|ltd|co|the|and|of|group|holdings|international|corporation|company)\b", "", regex=True)
    .str.replace(r"[^a-z0-9\s]", "", regex=True)
    .str.strip()
)

company_titles  = companies_df["title_clean"].tolist()
print(f"  Loaded {len(companies_df):,} public companies")

# ── Fuzzy match helper ───────────────────────────────────────
def match_company(recipient_name: str):
    """Return (ticker, matched_title) or (None, None) if no match above threshold."""
    if not recipient_name:
        return None, None

    name_clean = (
        recipient_name.lower()
        .replace("inc", "").replace("corp", "").replace("llc", "")
        .replace("ltd", "").replace("co", "").replace("the", "")
        .replace(",", "").replace(".", "").strip()
    )

    result = process.extractOne(
        name_clean,
        company_titles,
        scorer=fuzz.token_sort_ratio,
        score_cutoff=MATCH_THRESHOLD
    )

    if result:
        matched_title, score, idx = result
        ticker = companies_df.iloc[idx]["ticker"]
        title  = companies_df.iloc[idx]["title"]
        return ticker, title

    return None, None

# ── Fetch awards from USASpending ────────────────────────────
def fetch_awards_page(page: int) -> dict:
    url     = f"{BASE_URL}/search/spending_by_award/"
    payload = {
        "filters": {
            "time_period": [{"start_date": date_start, "end_date": date_end}],
            "award_type_codes": ["A", "B", "C", "D"],
        },
        "fields": [
            "Award ID",
            "Recipient Name",
            "Award Amount",
            "Awarding Agency",
            "Awarding Sub Agency",
            "Award Type",
            "Start Date",
            "End Date",
            "Description",
            "Place of Performance State Code",
        ],
        "sort":  "Award Amount",
        "order": "desc",
        "limit": PAGE_LIMIT,
        "page":  page,
    }

    resp = requests.post(url, json=payload, timeout=30)
    if resp.status_code != 200:
        print(f"  ERROR {resp.status_code}: {resp.text[:300]}")
        return {}
    return resp.json()

# ── Main fetch loop ──────────────────────────────────────────
print(f"\nFetching contract awards {date_start} -> {date_end}...")
all_results = []
page        = 1
has_next    = True

while has_next:
    data     = fetch_awards_page(page)
    if not data:
        break

    results  = data.get("results", [])
    has_next = data.get("page_metadata", {}).get("has_next_page", False)
    total    = data.get("page_metadata", {}).get("count", "?")

    print(f"  Page {page}: {len(results)} records (total available: {total})")
    all_results.extend(results)
    page += 1
    time.sleep(0.5)

print(f"\n  Total records fetched: {len(all_results):,}")

if not all_results:
    print("No data returned. Exiting.")
    sys.exit(0)

# ── Build DataFrame ──────────────────────────────────────────
df = pd.DataFrame(all_results)
df.columns = [c.strip() for c in df.columns]

# ── Fuzzy match against public companies ─────────────────────
print("\nMatching recipients against public companies...")
tickers, matched_names = [], []

for name in df["Recipient Name"]:
    ticker, matched = match_company(name)
    tickers.append(ticker)
    matched_names.append(matched)

df["ticker"]          = tickers
df["matched_company"] = matched_names

matched_count = df["ticker"].notna().sum()
print(f"  Matched {matched_count:,} of {len(df):,} records to public companies")

# ── Prepare records for upsert ───────────────────────────────
records = []
for _, row in df.iterrows():
    records.append({
        "award_id":             str(row.get("Award ID", "")),
        "recipient_name":       row.get("Recipient Name"),
        "award_amount":         row.get("Award Amount"),
        "awarding_agency":      row.get("Awarding Agency"),
        "awarding_sub_agency":  row.get("Awarding Sub Agency"),
        "award_type":           row.get("Award Type"),
        "start_date":           row.get("Start Date"),
        "end_date":             row.get("End Date"),
        "description":          row.get("Description"),
        "place_of_performance": row.get("Place of Performance State Code"),
        "ticker":               row.get("ticker"),
        "matched_company":      row.get("matched_company"),
        "updated_at":           datetime.utcnow().isoformat(),
    })

# ── Upsert to Supabase ───────────────────────────────────────
print(f"\nUpserting {len(records):,} records to Supabase...")
inserted = 0

for i in range(0, len(records), BATCH_SIZE):
    batch  = records[i : i + BATCH_SIZE]
    supabase.table("contract_awards").upsert(batch, on_conflict="award_id").execute()
    inserted += len(batch)
    print(f"  Batch {i // BATCH_SIZE + 1}: {inserted:,} / {len(records):,} upserted")

print(f"\n Done -- {inserted:,} records upserted into contract_awards")

# ── Print matched public company summary ─────────────────────
print("\n-- Matched Public Companies ---------------------")
matched_df = df[df["ticker"].notna()].copy()

if matched_df.empty:
    print("  No public company matches found in this date range.")
else:
    summary = (
        matched_df
        .groupby(["ticker", "matched_company"])["Award Amount"]
        .agg(["sum", "count"])
        .reset_index()
        .rename(columns={"sum": "Total Award ($)", "count": "# Contracts"})
        .sort_values("Total Award ($)", ascending=False)
    )
    summary["Total Award ($)"] = summary["Total Award ($)"].apply(lambda x: f"${x:,.0f}")
    print(summary.to_string(index=False))
