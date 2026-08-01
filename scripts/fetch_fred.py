# ============================================================
# FRED Economic Data → Supabase fred_observations table
# ============================================================
# Fetches latest observations from the St. Louis Fed FRED API
# and upserts into Supabase for the Insights/Economics page
# ============================================================
# First run: fetches 10 years of history (already done)
# Daily runs: fetches last 45 days only to catch new releases
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
from datetime import datetime, timezone, timedelta
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

FRED_BASE  = "https://api.stlouisfed.org/fred/series/observations"
BATCH_SIZE = 500
SLEEP      = 0.3

# Fetch last 45 days — catches monthly, weekly, and quarterly releases
# Historical data already stored from initial run
DAYS_BACK  = 45
START_DATE = (datetime.now() - timedelta(days=DAYS_BACK)).strftime("%Y-%m-%d")

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
    params = {
        "series_id":         series_id,
        "api_key":           FRED_API_KEY,
        "file_type":         "json",
        "observation_start": START_DATE,
        "sort_order":        "asc",
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
        print(f"  — No new observations for {series_id} in last {DAYS_BACK} days")
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

    # Upsert in batches — on_conflict updates existing rows
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
    print("  FRED Economic Data — Daily Update")
    print(f"  Fetching new observations since {START_DATE}")
    print(f"  ({len(SERIES)} series)")
    print("=" * 60)

    total_saved = 0
    failed      = []
    skipped     = 0

    for s in SERIES:
        sid  = s["id"]
        name = s["name"]
        print(f"\n{sid} — {name}")

        try:
            observations = fetch_series(sid)

            if not observations:
                skipped += 1
                continue

            print(f"  ✓ {len(observations)} new observation(s) found")
            saved = upsert_series(sid, name, observations)
            print(f"  ✓ {saved} record(s) upserted")
            total_saved += saved

        except Exception as e:
            print(f"  ✗ Error: {e}")
            failed.append(sid)
            continue

    print(f"\n{'='*60}")
    print(f"  Done")
    print(f"  Upserted : {total_saved:,} records")
    print(f"  Skipped  : {skipped} series (no new data in window)")
    print(f"  Failed   : {len(failed)}" + (f" — {', '.join(failed)}" if failed else ""))
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
