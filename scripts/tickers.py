# ============================================================
# SEC EDGAR → Supabase public_companies table
# ============================================================
# Dependencies: requests pandas supabase
# Secrets required (GitHub Actions → Settings → Secrets):
#   SUPABASE_URL
#   SUPABASE_KEY
# ============================================================

import os
import sys
import requests
import pandas as pd
from supabase import create_client

# ── Config — read from environment (GitHub Secrets) ─────────
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: SUPABASE_URL and SUPABASE_KEY must be set as environment variables.")
    sys.exit(1)

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_HEADERS     = {"User-Agent": "your-name your-email@example.com"}
BATCH_SIZE      = 500

# ── Connect to Supabase ──────────────────────────────────────
print("Connecting to Supabase...")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
print("✓ Connected")

# ── Fetch SEC tickers ────────────────────────────────────────
print("\nFetching SEC EDGAR ticker list...")
resp = requests.get(SEC_TICKERS_URL, headers=SEC_HEADERS, timeout=15)
print(f"  Status : {resp.status_code}")
print(f"  Size   : {len(resp.content) / 1024:.1f} KB")

raw = resp.json()
df  = pd.DataFrame.from_dict(raw, orient="index")
print(f"  Records: {len(df):,} companies")

# ── Prepare records ──────────────────────────────────────────
# Drop duplicates on cik_str — SEC data can have the same CIK under multiple tickers
df = df.drop_duplicates(subset="cik_str", keep="first")
print(f"  After dedup: {len(df):,} unique companies")
records = df[["cik_str", "ticker", "title"]].to_dict(orient="records")

# ── Upsert in batches ────────────────────────────────────────
print(f"\nUpserting to Supabase in batches of {BATCH_SIZE}...")
total    = len(records)
inserted = 0

for i in range(0, total, BATCH_SIZE):
    batch  = records[i : i + BATCH_SIZE]
    result = (
        supabase.table("public_companies")
        .upsert(batch, on_conflict="cik_str")
        .execute()
    )
    inserted += len(batch)
    print(f"  Batch {i // BATCH_SIZE + 1}: {inserted:,} / {total:,} upserted")

print(f"\n✓ Done — {inserted:,} companies upserted into public_companies")

# ── Verify — print sample from DB ───────────────────────────
print("\nVerifying — fetching 10 rows from Supabase...")
sample = (
    supabase.table("public_companies")
    .select("cik_str, ticker, title, updated_at")
    .limit(10)
    .execute()
)

df_sample = pd.DataFrame(sample.data)
print(df_sample.to_string(index=False))

# ── Row count ────────────────────────────────────────────────
count = (
    supabase.table("public_companies")
    .select("id", count="exact")
    .execute()
)
print(f"\nTotal rows in public_companies: {count.count:,}")
