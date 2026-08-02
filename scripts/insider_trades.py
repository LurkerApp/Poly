# ============================================================
# SEC Form 4 Insider Trades → Supabase insider_trades table
# ============================================================
# Tracks Form 4 filings by company CIK — catches all insiders
# at each tracked company (CEO, CFO, Directors, VPs etc.)
# ============================================================
# Dependencies: requests beautifulsoup4 supabase
# Secrets required:
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
    print("ERROR: SUPABASE_URL and SUPABASE_KEY must be set.")
    sys.exit(1)

HEADERS                 = {"User-Agent": "LurkerApp contact@lurkerapp.com"}
REQUEST_TIMEOUT         = 30
SLEEP_BETWEEN_CALLS_SEC = 0.5
MAX_RETRIES             = 2
FILINGS_PER_COMPANY     = 10   # most recent Form 4s to check per company

# ── Tracked companies ─────────────────────────────────────────
# Using company CIKs — catches ALL insiders at each company
COMPANIES = [
    {"name": "Apple",               "cik": "0000320193"},
    {"name": "Microsoft",           "cik": "0000789019"},
    {"name": "NVIDIA",              "cik": "0001045810"},
    {"name": "Alphabet",            "cik": "0001652044"},
    {"name": "Amazon",              "cik": "0001018724"},
    {"name": "Meta",                "cik": "0001326801"},
    {"name": "Tesla",               "cik": "0001318605"},
    {"name": "Berkshire Hathaway",  "cik": "0001067983"},
    {"name": "JPMorgan Chase",      "cik": "0000019617"},
    {"name": "Palantir",            "cik": "0001321655"},
    {"name": "AMD",                 "cik": "0000002488"},
    {"name": "Oracle",              "cik": "0001341439"},
    {"name": "Netflix",             "cik": "0001065280"},
    {"name": "Salesforce",          "cik": "0001108524"},
    {"name": "Disney",              "cik": "0001001039"},
]

# ── Also track specific high-profile individuals ──────────────
INDIVIDUALS = {
    "Elon Musk":        "0001494730",
    "Warren Buffett":   "0000315090",
    "Bill Ackman":      "0001056513",
    "George Soros":     "0000900203",
    "Michael Burry":    "0001649339",
    "Dan Loeb":         "0001040570",
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
        return requests.get(url, headers=HEADERS, params=params, timeout=REQUEST_TIMEOUT)
    except requests.exceptions.Timeout:
        print(f"  ⚠ Timeout (attempt {attempt}) — {url[:80]}")
        if attempt < MAX_RETRIES:
            time.sleep(3)
            return fetch(url, params=params, attempt=attempt + 1)
        return None
    except Exception as e:
        print(f"  ⚠ Error: {e}")
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
        if name in ("primary_doc.xml", "primary-document.xml", "form4.xml", "doc4.xml", "ownership.xml"):
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

    ns_uri = extract_ns_uri(root)

    # ── Issuer info ───────────────────────────────────────
    issuer      = root.find(tag(ns_uri, "issuer"))
    ticker      = "Unknown"
    issuer_name = "Unknown"
    if issuer is not None:
        t = issuer.find(tag(ns_uri, "issuerTradingSymbol"))
        n = issuer.find(tag(ns_uri, "issuerName"))
        if t is not None and t.text: ticker      = t.text.strip()
        if n is not None and n.text: issuer_name = n.text.strip()

    # ── Reporting owner info (name + title) ───────────────
    owner_name  = ""
    owner_title = ""
    owner_el    = root.find(tag(ns_uri, "reportingOwner"))
    if owner_el is not None:
        name_el  = owner_el.find(tag(ns_uri, "reportingOwnerId") + "/" + tag(ns_uri, "rptOwnerName"))
        title_el = owner_el.find(tag(ns_uri, "reportingOwnerRelationship") + "/" + tag(ns_uri, "officerTitle"))
        if name_el  is not None and name_el.text:  owner_name  = name_el.text.strip()
        if title_el is not None and title_el.text: owner_title = title_el.text.strip()

    # ── Transactions ──────────────────────────────────────
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
        "insider_name":    owner_name,
        "title":           owner_title,
        "issuer_name":     issuer_name,
        "ticker":          ticker,
        "trade_date":      trade_date,
        "action":          trade_action,
        "shares":          int(total_shares),
        "notional_value":  round(total_notional, 2),
        "security":        security,
        "filing_url":      xml_url,
    }

# ── Fetch recent Form 4s for a company CIK ────────────────────
def fetch_company_trades(company_name, cik, count):
    feed_url = "https://www.sec.gov/cgi-bin/browse-edgar"
    params   = {
        "action":  "getcompany",
        "CIK":     cik,
        "type":    "4",
        "owner":   "include",
        "count":   str(count),
        "output":  "atom"
    }

    resp = fetch(feed_url, params=params)
    if not resp or resp.status_code != 200:
        return []

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError:
        return []

    ns      = {"atom": "http://www.w3.org/2005/Atom"}
    entries = root.findall("atom:entry", ns)
    trades  = []

    for entry in entries:
        link = entry.find("atom:link", ns)
        if link is None or "href" not in link.attrib:
            continue
        xml_urls = find_xml_urls(link.attrib["href"])
        for xml_url in xml_urls:
            trade = parse_form4_xml(xml_url)
            if trade:
                trades.append(trade)
                break

    return trades

# ── Fetch most recent trade for an individual ─────────────────
def fetch_individual_trade(name, cik):
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
        return None

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError:
        return None

    ns      = {"atom": "http://www.w3.org/2005/Atom"}
    entries = root.findall("atom:entry", ns)
    if not entries:
        return None

    link = entries[0].find("atom:link", ns)
    if link is None or "href" not in link.attrib:
        return None

    xml_urls = find_xml_urls(link.attrib["href"])
    for xml_url in xml_urls:
        trade = parse_form4_xml(xml_url)
        if trade:
            # Override name for known individuals
            trade["insider_name"] = name
            return trade
    return None

# ── Save to Supabase ─────────────────────────────────────────
def save_trade(trade, company_name=None):
    record = {
        "insider_name":   trade["insider_name"],
        "title":          trade.get("title", ""),
        "ticker":         trade["ticker"],
        "issuer_name":    trade["issuer_name"],
        "company":        company_name or trade["issuer_name"],
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
    print(f"    ✓ {trade['insider_name']} ({trade.get('title','?')}) — "
          f"{trade['action']} {abs(trade['shares']):,} {trade['ticker']} "
          f"(${trade['notional_value']:,.0f})")

# ── Main ─────────────────────────────────────────────────────
def main():
    total_saved = 0
    errors      = 0

    # ── Company-based tracking ────────────────────────────
    print("=" * 60)
    print("  Company-based Form 4 tracking")
    print("=" * 60)

    for co in COMPANIES:
        print(f"\n{co['name']} (CIK {co['cik']})...")
        try:
            trades = fetch_company_trades(co["name"], co["cik"], FILINGS_PER_COMPANY)
            if not trades:
                print(f"  — No buy/sell trades found")
                continue
            for trade in trades:
                try:
                    save_trade(trade, co["name"])
                    total_saved += 1
                except Exception as e:
                    print(f"  ✗ Save error: {e}")
                    errors += 1
        except Exception as e:
            print(f"  ✗ Error: {e}")
            errors += 1

    # ── Individual tracking ───────────────────────────────
    print(f"\n{'='*60}")
    print("  Individual tracking")
    print("=" * 60)

    for name, cik in INDIVIDUALS.items():
        print(f"\n{name} (CIK {cik})...")
        try:
            trade = fetch_individual_trade(name, cik)
            if not trade:
                print(f"  — No recent buy/sell found")
                continue
            save_trade(trade)
            total_saved += 1
        except Exception as e:
            print(f"  ✗ Error: {e}")
            errors += 1

    print(f"\n{'='*60}")
    print(f"  Done — {total_saved} trades saved | {errors} errors")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
