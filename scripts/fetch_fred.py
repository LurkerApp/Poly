# ============================================================
# FRED Economic Data → Supabase fred_observations table
# ============================================================
# Fetches key macro series from the St. Louis Fed FRED API
# and upserts into Supabase for the Insights page
# ============================================================
# Dependencies: requests supabase
# Secrets required (GitHub Actions → Settings → Secrets):
#   SUPABASE_URL
#   SUPABASE_KEY
#   FRED_API_KEY
# ============================================================

import os
import sys
import requests
from supabase import create_client
from datetime import datetime, timezone
import time

# ── Config ───────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
FRED_API_KEY = os.environ.get("FRED_API_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: SUPABASE_URL and SUPABASE_KEY must be set.")
    sys.exit(1)

if not FRED_API_KEY:
    print("ERROR: FRED_API_KEY must be set.")
    sys.exit(1)

FRED_BASE    = "https://api.stlouisfed.org/fred/series/observations"
BATCH_SIZE   = 500
YEARS_BACK   = 10    # fetch last 10 years of data per series
SLEEP        = 0.3   # be gentle with FRED API

# ── Series to fetch ───────────────────────────────────────────
SERIES = [
    # Inflation
    {"id": "CPIAUCSL",          "name": "CPI All Items"},
    {"id": "CPILFESL",          "name": "Core CPI (ex Food & Energy)"},
    {"id": "PCEPI",             "name": "PCE Inflation"},

    # Labor Market
    {"id": "UNRATE",            "name": "Unemployment Rate"},
    {"id": "ICSA",              "name": "Initial Jobless Claims"},
    {"id": "JTSJOL",            "name": "Job Openings (JOLTS)"},

    # Interest Rates
    {"id": "FEDFUNDS",          "name": "Fed Funds Rate"},
    {"id": "DFEDTARL",          "name": "Fed Funds Target Lower Bound"},
    {"id": "DFEDTARU",          "name": "Fed Funds Target Upper Bound"},
    {"id": "GS2",               "name": "2Y Treasury Yield"},
    {"id": "GS10",              "name": "10Y Treasury Yield"},
    {"id": "GS30",              "name": "30Y Treasury Yield"},
    {"id": "T10Y2Y",            "name": "Yield Curve Spread (10Y-2Y)"},

    # Fed & Money Supply
    {"id": "WALCL",             "name": "Fed Balance Sheet"},
    {"id": "M2SL",              "name": "M2 Money Supply"},

    # Growth
    {"id": "A191RL1Q225SBEA",   "name": "Real GDP Growth"},

    # Consumer
    {"id": "TOTALSL",           "name": "Consumer Credit"},
    {"id": "DRCCLACBS",         "name": "Credit Card Delinquency Rate"},
    {"id": "PSAVERT",           "name": "Personal Savings Rate"},
]

# ── Connect to Supabase ──────────────────────────────────────
print("Connecting to Supabase...")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
print("✓ Connected\n")

# ── Fetch one FRED series ─────────────────────────────────────
def fetch_series(series_id):
    # Start date — 10 years back
    start = datetime(datetime.now().year - YEARS_BACK, 1, 1).strftime("%Y-%m-%d")

    params = {
        "series_id":      series_id,
        "api_key":        FRED_API_KEY,
        "file_type":      "json",
        "observation_start": start,
        "sort_order":     "asc",
    }

    time.sleep(SLEEP)
    resp = requests.get(FRED_BASE, params=params, timeout=20)

    if resp.status_code != 200:
        print(f"  ✗ HTTP {resp.status_code} for {series_id}")
        return []

    data = resp.json()
    obs  = data.get("observations", [])

    # Filter out missing values (FRED uses "." for missing)
    valid = [o for o in obs if o.get("value") and o["value"] != "."]
    return valid

# ── Upsert to Supabase ────────────────────────────────────────
def upsert_series(series_id, series_name, observations):
    if not observations:
        print(f"  ✗ No valid observations for {series_id}")
        return 0

    now     = datetime.now(timezone.utc).isoformat()
    records = []

    for o in observations:
        try:
            records.append({
                "series_id":   series_id,
                "series_name": series_name,
                "date":        o["date"],
                "value":       float(o["value"]),
                "updated_at":  now,
            })
        except (ValueError, KeyError):
            continue

    # Upsert in batches
    inserted = 0
    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i : i + BATCH_SIZE]
        supabase.table("fred_observations").upsert(
            batch,
            on_conflict="series_id,date"
        ).execute()
        inserted += len(batch)

    return inserted

# ── Main ─────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  FRED Economic Data Fetcher")
    print(f"  Fetching {len(SERIES)} series — last {YEARS_BACK} years")
    print("=" * 60)

    total_saved = 0
    failed      = []

    for s in SERIES:
        sid  = s["id"]
        name = s["name"]
        print(f"\nFetching {sid} — {name}...")

        try:
            observations = fetch_series(sid)
            print(f"  ✓ {len(observations)} observations fetched")

            saved = upsert_series(sid, name, observations)
            print(f"  ✓ {saved} records upserted")
            total_saved += saved

        except Exception as e:
            print(f"  ✗ Error: {e}")
            failed.append(sid)
            continue

    print(f"\n{'='*60}")
    print(f"  Done — {total_saved:,} total records upserted")
    print(f"  Series: {len(SERIES) - len(failed)} succeeded, {len(failed)} failed")
    if failed:
        print(f"  Failed: {', '.join(failed)}")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
