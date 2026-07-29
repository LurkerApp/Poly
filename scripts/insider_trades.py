# ============================================================
# SEC Form 4 Insider Trades → Supabase insider_trades table
# ============================================================
# Dependencies: requests beautifulsoup4 supabase
# Secrets required (GitHub Actions → Settings → Secrets):
#   SUPABASE_URL
#   SUPABASE_KEY
# ============================================================

import os
import sys
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from supabase import create_client
from datetime import datetime, timezone
import time

# ── Config ───────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: SUPABASE_URL and SUPABASE_KEY must be set as environment variables.")
    sys.exit(1)

HEADERS                 = {"User-Agent": "LurkerApp contact@lurkerapp.com"}
REQUEST_TIMEOUT         = 30   # increased from 15
SLEEP_BETWEEN_CALLS_SEC = 0.5  # increased to be gentler on SEC servers
MAX_RETRIES             = 2

INSIDERS = {
    # ── Tech CEOs / Founders ─────────────────────────────────
    "Elon Musk":        "0001494730",
    "Jeff Bezos":       "0001043298",
    "Andy Jassy":       "0001374545",
    "Mark Zuckerberg":  "0001548760",
    "Sundar Pichai":    "0001534753",
    "Sergey Brin":      "0001295032",
    "Satya Nadella":    "0001513142",
    "Tim Cook":         "0001214156",
    "Jensen Huang":     "0001197649",
    "Lisa Su":          "0001227903",
    "Michael Dell":     "0000908724",
    "Bob Iger":         "0001207394",
    "Jack Dorsey":      "0001590945",
    "Alex Karp":        "0001823951",
    "Sam Altman":       "0001571705",
    "Larry Ellison":    "0000901999",

    # ── Investors ────────────────────────────────────────────
    "Warren Buffett":   "0000315090",
    "Bill Ackman":      "0001056513",
    "Carl Icahn":       "0000921669",
    "Ken Griffin":      "0001255159",
    "George Soros":     "0000900203",
    "Michael Burry":    "0001649339",
    "Dan Loeb":         "0001040570",

    # ── Politics ─────────────────────────────────────────────
    "Donald Trump":     "0000947033",
    "Eric Trump":       "0002057754",
}

# ── Connect to Supabase ──────────────────────────────────────
print("Connecting to Supabase...")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
print("✓ Connected\n")

# ── Helpers ──────────────────────────────────────────────────
def fetch(url, params=None, attempt=1):
    time.sleep(SLEEP_BETWEEN_CALLS_SEC)
    try:
        resp = requests.get(
            url,
            headers=HEADERS,
            params=params,
            timeout=REQUEST_TIMEOUT
        )
        return resp
    except requests.exceptions.Timeout:
        print(f"  ⚠ Timeout (attempt {attempt}) — {url}")
        if attempt < MAX_RETRIES:
            print(f"  Retrying in 3s...")
            time.sleep(3)
            return fetch(url, params=params, attempt=attempt + 1)
        return None
    except Exception as e:
        print(f"  ⚠ Request error: {e}")
        return None

def extract_ns_uri(root):
    if root.tag.startswith("{"):
        return root.tag.split("}")[0][1:]
    return ""

def tag(ns_uri, local):
    return f"{{{ns_uri}}}{local}" if ns_uri else local

def find_xml_urls(filing_index_url):
    resp = fetch(filing_index_url)
    if not resp or resp.status_code != 200:
        return []
    soup  = BeautifulSoup(resp.text, "html.parser")
    links = []
    for tbl_sel in ("table.tableFile", "table.tableFile2"):
        for a in soup.select(f"{tbl_sel} a"):
            href = a.get("href")
            if href and href.endswith(".xml"):
                links.append("https://www.sec.gov" + href)

    def priority(u):
        name = u.rsplit("/", 1)[-1].lower()
        if name in ("primary_doc.xml", "primary-document.xml", "form4.xml",
                    "doc4.xml", "ownership.xml"):
            return 0
        if "/xslf345" in u.lower():
            return 2
        return 1

    links.sort(key=priority)
    return links

def parse_form4_xml(xml_url):
    resp = fetch(xml_url)
    if not resp or resp.status_code != 200:
        return None
    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError:
        return None

    ns_uri  = extract_ns_uri(root)
    issuer  = root.find(tag(ns_uri, "issuer"))

    ticker = (
        issuer.find(tag(ns_uri, "issuerTradingSymbol")).text.strip()
        if issuer is not None and issuer.find(tag(ns_uri, "issuerTradingSymbol")) is not None
        else "Unknown"
    )
    issuer_name = (
        issuer.find(tag(ns_uri, "issuerName")).text.strip()
        if issuer is not None and issuer.find(tag(ns_uri, "issuerName")) is not None
        else "Unknown"
    )

    total_shares   = 0.0
    total_notional = 0.0
    trade_action   = None
    trade_date     = None
    security       = None

    for non_der in root.findall(".//" + tag(ns_uri, "nonDerivativeTransaction")):
        code_elem   = non_der.find(tag(ns_uri, "transactionCoding") + "/" + tag(ns_uri, "transactionCode"))
        date_elem   = non_der.find(tag(ns_uri, "transactionDate") + "/" + tag(ns_uri, "value"))
        shares_elem = non_der.find(tag(ns_uri, "transactionAmounts") + "/" + tag(ns_uri, "transactionShares") + "/" + tag(ns_uri, "value"))
        price_elem  = non_der.find(tag(ns_uri, "transactionAmounts") + "/" + tag(ns_uri, "transactionPricePerShare") + "/" + tag(ns_uri, "value"))
        sec_elem    = non_der.find(tag(ns_uri, "securityTitle") + "/" + tag(ns_uri, "value"))

        if code_elem is None or date_elem is None or shares_elem is None:
            continue

        code = (code_elem.text or "").strip()
        if code not in ("P", "S"):
            continue

        action  = "Buy" if code == "P" else "Sell"
        shares  = float((shares_elem.text or "0").replace(",", ""))
        price   = float((price_elem.text or "0").replace(",", "")) if price_elem is not None else 0.0

        total_shares   += shares if action == "Buy" else -shares
        total_notional += shares * price
        trade_action    = action
        trade_date      = (date_elem.text or "").strip()
        security        = (sec_elem.text or "").strip() if sec_elem is not None else ""

    if total_shares == 0:
        return None

    return {
        "issuer_name":    issuer_name,
        "ticker":         ticker,
        "trade_date":     trade_date,
        "action":         trade_action,
        "shares":         int(total_shares),
        "notional_value": round(total_notional, 2),
        "security":       security,
        "filing_url":     xml_url,
    }

def fetch_most_recent_trade_for_cik(cik):
    feed_url = "https://www.sec.gov/cgi-bin/browse-edgar"
    params   = {
        "action": "getcompany",
        "CIK":    cik,
        "type":   "4",
        "owner":  "only",
        "count":  "5",
        "output": "atom"
    }

    resp = fetch(feed_url, params=params)
    if not resp or resp.status_code != 200:
        print(f"  ✗ Could not fetch filing list (status: {resp.status_code if resp else 'timeout'})")
        return None

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as e:
        print(f"  ✗ XML parse error on feed: {e}")
        return None

    ns      = {"atom": "http://www.w3.org/2005/Atom"}
    entries = root.findall("atom:entry", ns)

    if not entries:
        print(f"  ✗ No filings found in feed")
        return None

    # Only check the most recent filing
    entry = entries[0]
    link  = entry.find("atom:link", ns)

    if link is None or "href" not in link.attrib:
        print(f"  ✗ No link in most recent filing entry")
        return None

    filing_index_url = link.attrib["href"]
    xml_urls         = find_xml_urls(filing_index_url)

    if not xml_urls:
        print(f"  ✗ No XML files found in filing index")
        return None

    for xml_url in xml_urls:
        trade = parse_form4_xml(xml_url)
        if trade:
            return trade

    return None

# ── Save to Supabase ─────────────────────────────────────────
def save_to_supabase(trade, insider_name):
    record = {
        "insider_name":   insider_name,
        "ticker":         trade["ticker"],
        "issuer_name":    trade["issuer_name"],
        "action":         trade["action"],
        "shares":         trade["shares"],
        "notional_value": trade["notional_value"],
        "security":       trade["security"],
        "trade_date":     trade["trade_date"],
        "filing_url":     trade["filing_url"],
    }
    supabase.table("insider_trades").upsert(
        record, on_conflict="filing_url"
    ).execute()
    print(f"  ✓ Saved: {insider_name} — {trade['action']} "
          f"{abs(trade['shares']):,} shares of {trade['ticker']} "
          f"(${trade['notional_value']:,.0f})")

# ── Main ─────────────────────────────────────────────────────
def main():
    saved   = 0
    skipped = 0
    errors  = 0

    for name, cik in INSIDERS.items():
        print(f"\nFetching Form 4 for {name} (CIK {cik})...")
        try:
            trade = fetch_most_recent_trade_for_cik(cik)
            if trade:
                save_to_supabase(trade, name)
                saved += 1
            else:
                print(f"  — No buy/sell found in most recent filing")
                skipped += 1
        except Exception as e:
            print(f"  ✗ Unexpected error for {name}: {e}")
            errors += 1
            continue

    print(f"\n{'='*50}")
    print(f"  Done — {saved} saved | {skipped} skipped | {errors} errors")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()
