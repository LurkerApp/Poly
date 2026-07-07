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
from datetime import datetime, timezone, timedelta
import time
import math
import re

# ── Config ───────────────────────────────────────────────────
SUPABASE_URL    = os.environ.get("SUPABASE_URL")
SUPABASE_KEY    = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: SUPABASE_URL and SUPABASE_KEY must be set as environment variables.")
    sys.exit(1)

BASE_URL        = "https://api.usaspending.gov/api/v2"
DAYS_BACK       = 2
PAGE_LIMIT      = 100
MATCH_THRESHOLD = 92    # higher = fewer false positives
BATCH_SIZE      = 500
MIN_AMOUNT      = 1     # filter out awards below $1
MIN_LEN_RATIO   = 0.6   # cleaned names must be within 60% length of each other

# ── Date range ───────────────────────────────────────────────
end_date   = datetime.today()
start_date = end_date - timedelta(days=DAYS_BACK)
date_start = start_date.strftime("%Y-%m-%d")
date_end   = end_date.strftime("%Y-%m-%d")

# ── Connect to Supabase ──────────────────────────────────────
print("Connecting to Supabase...")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
print("✓ Connected")

# ── Load ALL public companies from Supabase (paginated) ──────
print("\nLoading public companies from Supabase...")
all_companies = []
page_size     = 1000
offset        = 0

while True:
    resp = (
        supabase.table("public_companies")
        .select("ticker, title")
        .range(offset, offset + page_size - 1)
        .execute()
    )
    batch = resp.data
    if not batch:
        break
    all_companies.extend(batch)
    offset += page_size
    if len(batch) < page_size:
        break

companies_df = pd.DataFrame(all_companies)
print(f"  Loaded {len(companies_df):,} public companies")

# ── Normalize company names for matching ─────────────────────
# Note: "federal" and "security" removed from strip list intentionally —
# stripping them causes short generic tokens that produce false positives
STRIP_WORDS = r"\b(inc|corp|llc|ltd|co|the|and|of|group|holdings|international|corporation|company|services|solutions|systems|technologies|technology|enterprises|partners|consulting)\b"

def normalize(name: str) -> str:
    if not name:
        return ""
    name = name.lower()
    name = re.sub(STRIP_WORDS, "", name)
    name = re.sub(r"[^a-z0-9\s]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name

companies_df["title_clean"] = companies_df["title"].apply(normalize)
company_titles = companies_df["title_clean"].tolist()

# ── Fuzzy match helper ───────────────────────────────────────
def match_company(recipient_name: str):
    """
    Match recipient name against SEC public companies.

    Guards against false positives:
    1. Minimum cleaned name length of 5 chars
    2. token_sort_ratio scorer (respects word order, less aggressive than token_set)
    3. Length ratio guard: cleaned names must be within 60% length of each other
       — prevents "security" matching "security federal corp"
    4. Matched company name must also be >= 5 chars
    """
    if not recipient_name:
        return None, None

    name_clean = normalize(recipient_name)

    if len(name_clean) < 5:
        return None, None

    result = process.extractOne(
        name_clean,
        company_titles,
        scorer=fuzz.token_sort_ratio,
        score_cutoff=MATCH_THRESHOLD
    )

    if result:
        matched_title, score, idx = result
        matched_clean = company_titles[idx]

        # Length ratio guard
        max_len   = max(len(name_clean), len(matched_clean), 1)
        min_len   = min(len(name_clean), len(matched_clean))
        len_ratio = min_len / max_len
        if len_ratio < MIN_LEN_RATIO:
            return None, None

        # Minimum matched name length
        if len(matched_clean) < 5:
            return None, None

        ticker = companies_df.iloc[idx]["ticker"]
        title  = companies_df.iloc[idx]["title"]
        print(f"    MATCH: '{recipient_name}' → {ticker} ({title}) "
              f"[score: {score}, len_ratio: {len_ratio:.2f}]")
        return ticker, title

    return None, None

# ── Fetch awards from USASpending (all pages) ────────────────
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
    data = fetch_awards_page(page)
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

# ── Filter: award amount > $1 ────────────────────────────────
before = len(df)
df = df[df["Award Amount"].notna() & (df["Award Amount"] > MIN_AMOUNT)]
print(f"\n  After amount filter (>${MIN_AMOUNT}): {len(df):,} of {before:,} records kept")

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
print(f"\n  Matched {matched_count:,} of {len(df):,} records to public companies")

# ── Clean NaN → None for JSON serialization ──────────────────
def clean(val):
    if val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    return val

# ── Prepare records for upsert ───────────────────────────────
records = []
for _, row in df.iterrows():
    records.append({
        "award_id":             clean(str(row.get("Award ID", ""))),
        "recipient_name":       clean(row.get("Recipient Name")),
        "award_amount":         clean(row.get("Award Amount")),
        "awarding_agency":      clean(row.get("Awarding Agency")),
        "awarding_sub_agency":  clean(row.get("Awarding Sub Agency")),
        "award_type":           clean(row.get("Award Type")),
        "start_date":           clean(row.get("Start Date")),
        "end_date":             clean(row.get("End Date")),
        "description":          clean(row.get("Description")),
        "place_of_performance": clean(row.get("Place of Performance State Code")),
        "ticker":               clean(row.get("ticker")),
        "matched_company":      clean(row.get("matched_company")),
        "updated_at":           datetime.now(timezone.utc).isoformat(),
    })

# ── Upsert to Supabase ───────────────────────────────────────
print(f"\nUpserting {len(records):,} records to Supabase...")
inserted = 0

for i in range(0, len(records), BATCH_SIZE):
    batch = records[i : i + BATCH_SIZE]
    supabase.table("contract_awards").upsert(batch, on_conflict="award_id").execute()
    inserted += len(batch)
    print(f"  Batch {i // BATCH_SIZE + 1}: {inserted:,} / {len(records):,} upserted")

print(f"\n✓ Done — {inserted:,} records upserted into contract_awards")

# ── Summary ──────────────────────────────────────────────────
print("\n── Matched Public Companies ────────────────────────────")
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
