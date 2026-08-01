# ============================================================
# Hedge Fund 13F Positions → Supabase
# ============================================================
# Pulls latest 13F filing for each tracked fund from SEC EDGAR
# Upserts positions into fund_positions table
# ============================================================
# Dependencies: requests supabase
# Secrets required (GitHub Actions → Settings → Secrets):
#   SUPABASE_URL
#   SUPABASE_KEY
# ============================================================

import os
import sys
import requests
import xml.etree.ElementTree as ET
import re
import time
from datetime import datetime, timezone

# ── Config ───────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: SUPABASE_URL and SUPABASE_KEY must be set.")
    sys.exit(1)

from supabase import create_client
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

HEADERS     = {"User-Agent": "LurkerApp contact@lurkerapp.com"}
SLEEP       = 0.4
MAX_RETRIES = 2

FUNDS = [
    {"name": "Scion Asset Management",    "cik": "0001649339"},
    {"name": "Pershing Square Capital",   "cik": "0001336528"},
    {"name": "Berkshire Hathaway",        "cik": "0001067983"},
    {"name": "Third Point",               "cik": "0001040570"},
    {"name": "Appaloosa Management",      "cik": "0001656456"},
    {"name": "Situational Awareness LP",  "cik": "0002045724"},
]

# ── Helpers ──────────────────────────────────────────────────
def sec_get(url, attempt=1):
    time.sleep(SLEEP)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        return resp
    except requests.exceptions.Timeout:
        print(f"  ⚠ Timeout (attempt {attempt}) — {url}")
        if attempt < MAX_RETRIES:
            time.sleep(3)
            return sec_get(url, attempt + 1)
        return None
    except Exception as e:
        print(f"  ⚠ Error: {e}")
        return None

def quarter_from_date(date_str):
    """Convert filed date to quarter string e.g. '2025-11-03' → '2025-Q4'"""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        q = (d.month - 1) // 3 + 1
        return f"{d.year}-Q{q}"
    except Exception:
        return "Unknown"

# ── Step 1: Get latest 13F filing ────────────────────────────
def get_latest_13f(fund_name, cik):
    print(f"\n  Fetching 13F for {fund_name} (CIK {cik})...")
    resp = sec_get(f"https://data.sec.gov/submissions/CIK{cik}.json")
    if not resp or resp.status_code != 200:
        print(f"  ✗ Could not fetch submissions for {fund_name}")
        return None

    data    = resp.json()
    filings = data.get("filings", {}).get("recent", {})
    forms   = filings.get("form", [])
    dates   = filings.get("filingDate", [])
    accnums = filings.get("accessionNumber", [])

    for i, form in enumerate(forms):
        if form in ("13F-HR", "13F-HR/A"):
            latest = {
                "form":      form,
                "date":      dates[i],
                "accession": accnums[i],
                "quarter":   quarter_from_date(dates[i]),
            }
            print(f"  ✓ Latest 13F: {latest['date']} ({latest['quarter']}) — {latest['accession']}")
            return latest

    print(f"  ✗ No 13F-HR found for {fund_name}")
    return None

# ── Step 2: Get filing index ──────────────────────────────────
def get_filing_index(cik, accession):
    cik_int   = int(cik)
    acc_clean = accession.replace("-", "")
    url       = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/{accession}-index.htm"

    resp = sec_get(url)
    if not resp or resp.status_code != 200:
        return None, cik_int, acc_clean

    xml_files = re.findall(r'href="([^"]+\.xml)"', resp.text, re.IGNORECASE)

    xml_doc = None
    for f in xml_files:
        fname = f.split("/")[-1].lower()
        if "infotable" in fname and "xsl" not in f.lower():
            xml_doc = f.split("/")[-1]
            break
    if not xml_doc:
        for f in xml_files:
            if "infotable" in f.split("/")[-1].lower():
                xml_doc = f.split("/")[-1]
                break
    if not xml_doc:
        for f in xml_files:
            if "primary" not in f.split("/")[-1].lower() and "xsl" not in f.lower():
                xml_doc = f.split("/")[-1]
                break

    return xml_doc, cik_int, acc_clean

# ── Step 3: Parse positions ───────────────────────────────────
def parse_positions(cik_int, acc_clean, xml_doc):
    url  = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/{xml_doc}"
    resp = sec_get(url)
    if not resp or resp.status_code != 200:
        return []

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as e:
        print(f"  ✗ XML parse error: {e}")
        return []

    ns = {}
    if "{" in root.tag:
        ns_uri = root.tag.split("}")[0][1:]
        ns     = {"ns": ns_uri}
        entries = root.findall(".//ns:infoTable", ns)
    else:
        entries = root.findall(".//infoTable")

    print(f"  ✓ Found {len(entries)} positions in XML")

    positions = []
    for entry in entries:

        def get_val(tag_name):
            el = entry.find("ns:" + tag_name, ns)
            if el is None:
                el = entry.find(tag_name)
            if el is None:
                for child in entry.iter():
                    if child.tag.split("}")[-1].lower() == tag_name.lower():
                        el = child
                        break
            return el.text.strip() if el is not None and el.text else ""

        company   = get_val("nameOfIssuer")
        cusip     = get_val("cusip")
        put_call  = get_val("putCall") or None
        sh_type   = get_val("sshPrnamtType")
        value_str = get_val("value")
        value_usd = int(value_str.replace(",", "")) if value_str else 0

        # Shares nested inside shrsOrPrnAmt > sshPrnamt
        shares_str = ""
        parent = entry.find("ns:shrsOrPrnAmt", ns)
        if parent is None:
            parent = entry.find("shrsOrPrnAmt")
        if parent is not None:
            shs_el = parent.find("ns:sshPrnamt", ns)
            if shs_el is None:
                shs_el = parent.find("sshPrnamt")
            if shs_el is not None and shs_el.text:
                shares_str = shs_el.text.strip()
        if not shares_str:
            shares_str = get_val("sshPrnamt")
        shares = int(shares_str.replace(",", "")) if shares_str else 0

        is_option = put_call in ("Put", "Call")

        positions.append({
            "company_name":  company,
            "cusip":         cusip,
            "value_usd":     value_usd,
            "shares":        shares,
            "position_type": sh_type,
            "put_call":      put_call,
            "is_option":     is_option,
        })

    return positions

# ── Step 4: Upsert to Supabase ────────────────────────────────
def upsert_fund(fund_name, cik, filing, positions):
    if not positions:
        print(f"  ✗ No positions to save for {fund_name}")
        return 0

    total   = sum(p["value_usd"] for p in positions)
    quarter = filing["quarter"]

    # Upsert fund record
    supabase.table("hedge_funds").upsert({
        "name":       fund_name,
        "cik":        cik,
        "aum":        total,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }, on_conflict="cik").execute()

    # Build position records
    records = []
    for p in positions:
        pct = round(p["value_usd"] / total * 100, 2) if total > 0 else 0
        records.append({
            "fund_cik":      cik,
            "fund_name":     fund_name,
            "quarter":       quarter,
            "filed_date":    filing["date"],
            "company_name":  p["company_name"],
            "cusip":         p["cusip"],
            "ticker":        None,
            "position_type": p["position_type"],
            "put_call":      p["put_call"],
            "is_option":     p["is_option"],
            "shares":        p["shares"],
            "value_usd":     p["value_usd"],
            "pct_portfolio": pct,
        })

    # Deduplicate by (fund_cik, cusip, put_call, quarter)
    seen    = set()
    deduped = []
    for r in records:
        key = (r["fund_cik"], r["cusip"], str(r["put_call"]), r["quarter"])
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    supabase.table("fund_positions").upsert(
        deduped,
        on_conflict="fund_cik,cusip,put_call,quarter"
    ).execute()

    print(f"  ✓ Saved {len(deduped)} positions for {fund_name} ({quarter})")
    return len(deduped)

# ── Main ─────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  Hedge Fund 13F Puller")
    print("=" * 60)
    print(f"\nConnecting to Supabase...")
    print(f"✓ Connected\n")

    total_saved = 0

    for fund in FUNDS:
        try:
            filing = get_latest_13f(fund["name"], fund["cik"])
            if not filing:
                continue

            xml_doc, cik_int, acc_clean = get_filing_index(fund["cik"], filing["accession"])
            if not xml_doc:
                print(f"  ✗ No XML found for {fund['name']}")
                continue

            positions = parse_positions(cik_int, acc_clean, xml_doc)
            saved     = upsert_fund(fund["name"], fund["cik"], filing, positions)
            total_saved += saved

        except Exception as e:
            print(f"\n  ERROR processing {fund['name']}: {e}")
            continue

    print(f"\n{'='*60}")
    print(f"  Done — {total_saved} total positions saved across {len(FUNDS)} funds")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
