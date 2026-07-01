# ============================================================
# Polymarket Whale Tracker
# Uses Data API (public, no auth) instead of CLOB API
# Scoring weights:
#   ROI           30%
#   Calibration   25%
#   Consistency   20%
#   Early Entry   15%
#   Volume        10%
# ============================================================
# Dependencies: requests
# ============================================================

import requests
import json
import time
import os
import math
from datetime import datetime, timezone
from collections import defaultdict

# ── Config ───────────────────────────────────────────────────
GAMMA_API       = "https://gamma-api.polymarket.com"
DATA_API        = "https://data-api.polymarket.com"

WHALE_MIN_USDC  = 500       # minimum trade size to qualify
MAX_MARKETS     = 30        # active markets to scan
MAX_WALLETS     = 50        # top wallets in output
MIN_VOLUME      = 1000      # min lifetime USDC volume
SLEEP           = 0.3       # seconds between API calls

# Scoring bounds
ROI_FLOOR       = -0.50
ROI_CAP         =  1.00
VOLUME_ANCHOR   = 500000
EARLY_DAYS      = 7

OUTPUT_DIR      = "data"
OUTPUT_FILE     = os.path.join(OUTPUT_DIR, "whales.json")

# ── Helpers ──────────────────────────────────────────────────
def get(url, params=None):
    time.sleep(SLEEP)
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  ERROR {url}: {e}")
        return None

def clamp(val, lo, hi):
    return max(lo, min(hi, val))

def fmt(val):
    return f"${val:,.0f}"

# ── Step 1: Fetch active markets ─────────────────────────────
def fetch_markets():
    print("Fetching active markets...")
    data = get(f"{GAMMA_API}/markets", params={
        "active": "true",
        "closed": "false",
        "limit": MAX_MARKETS,
        "order": "volume24hr",
        "ascending": "false"
    })
    if not data:
        return []
    markets = data if isinstance(data, list) else data.get("markets", [])
    print(f"  Found {len(markets)} active markets")
    return markets

# ── Step 2: Fetch resolved markets ───────────────────────────
def fetch_resolved_markets():
    print("Fetching recently resolved markets...")
    data = get(f"{GAMMA_API}/markets", params={
        "active": "false",
        "closed": "true",
        "limit": 100,
        "order": "endDate",
        "ascending": "false"
    })
    if not data:
        return []
    markets = data if isinstance(data, list) else data.get("markets", [])
    print(f"  Found {len(markets)} resolved markets")
    return markets

# ── Step 3: Fetch trades from Data API (public, no auth) ─────
def fetch_whale_trades(markets):
    print(f"\nScanning for trades >= ${WHALE_MIN_USDC} via Data API...")

    wallet_markets = defaultdict(lambda: defaultdict(lambda: {
        "usdc": 0, "trades": 0, "prices": [],
        "first_trade_ts": None, "market_created": None,
        "market_name": ""
    }))

    wallet_totals = defaultdict(lambda: {
        "total_usdc": 0, "total_trades": 0, "market_ids": set()
    })

    for market in markets:
        cid         = market.get("conditionId") or market.get("condition_id", "")
        market_name = market.get("question") or market.get("title", "Unknown")
        created_at  = market.get("createdAt") or market.get("created_at")
        if not cid:
            continue

        # Data API trades endpoint — public, no auth required
        trades = get(f"{DATA_API}/trades", params={
            "market": cid,
            "limit": 500,
            "filterType": "CASH",
            "filterAmount": WHALE_MIN_USDC
        })

        if not trades:
            continue

        trade_list = trades if isinstance(trades, list) else trades.get("data", [])

        for t in trade_list:
            usdc   = float(t.get("usdcSize") or t.get("cash_amount") or 0)
            price  = float(t.get("price") or 0)
            ts     = t.get("timestamp") or t.get("created_at", "")
            wallet = t.get("proxyWallet") or t.get("proxy_wallet") or t.get("maker_address")

            if not wallet or usdc < WHALE_MIN_USDC:
                continue

            wm = wallet_markets[wallet][cid]
            wm["usdc"]         += usdc
            wm["trades"]       += 1
            wm["prices"].append(price)
            wm["market_name"]   = market_name
            wm["market_created"] = created_at
            if not wm["first_trade_ts"] or str(ts) < str(wm["first_trade_ts"]):
                wm["first_trade_ts"] = ts

            wt = wallet_totals[wallet]
            wt["total_usdc"]   += usdc
            wt["total_trades"] += 1
            wt["market_ids"].add(cid)

        print(f"  ✓ {market_name[:55]}")

    print(f"\n  Found {len(wallet_totals)} whale wallets")
    return wallet_markets, wallet_totals

# ── Step 4: ROI + calibration from resolved markets ──────────
def compute_roi_calibration(wallet_markets, resolved_markets):
    resolved_lookup = {}
    for m in resolved_markets:
        cid    = m.get("conditionId") or m.get("condition_id", "")
        prices = m.get("outcomePrices")
        if prices:
            try:
                outcome_prices = json.loads(prices) if isinstance(prices, str) else prices
                resolved_lookup[cid] = float(outcome_prices[0])
            except Exception:
                pass

    wallet_roi   = {}
    wallet_calib = {}

    for wallet, markets_data in wallet_markets.items():
        roi_list, brier_list = [], []
        for cid, data in markets_data.items():
            if cid not in resolved_lookup or not data["prices"]:
                continue
            resolution = resolved_lookup[cid]
            avg_price  = sum(data["prices"]) / len(data["prices"])
            if avg_price <= 0:
                continue
            roi_list.append((resolution - avg_price) / avg_price)
            brier_list.append(1 - (avg_price - resolution) ** 2)

        wallet_roi[wallet]   = sum(roi_list) / len(roi_list) if roi_list else None
        wallet_calib[wallet] = sum(brier_list) / len(brier_list) if brier_list else None

    return wallet_roi, wallet_calib

# ── Step 5: Score wallets ─────────────────────────────────────
def score_wallets(wallet_markets, wallet_totals, wallet_roi, wallet_calib, active_markets):
    print(f"\nScoring wallets...")

    market_created = {}
    for m in active_markets:
        cid = m.get("conditionId") or m.get("condition_id", "")
        market_created[cid] = m.get("createdAt") or m.get("created_at")

    def parse_ts(s):
        if not s:
            return None
        s = str(s)
        # Handle unix timestamps
        if s.isdigit():
            return datetime.fromtimestamp(int(s), tz=timezone.utc)
        for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
                    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            except Exception:
                pass
        return None

    ranked = []

    for wallet, totals in wallet_totals.items():
        if totals["total_usdc"] < MIN_VOLUME:
            continue

        # ROI Score (30%)
        roi = wallet_roi.get(wallet)
        roi_score = clamp((roi - ROI_FLOOR) / (ROI_CAP - ROI_FLOOR) * 100, 0, 100) if roi is not None else 50

        # Calibration Score (25%)
        calib = wallet_calib.get(wallet)
        calib_score = clamp(calib * 100, 0, 100) if calib is not None else 50

        # Consistency Score (20%)
        resolved_trades = [(c, d) for c, d in wallet_markets[wallet].items()
                           if wallet_roi.get(wallet) is not None]
        if resolved_trades:
            wins = sum(1 for c, d in resolved_trades if (wallet_roi.get(wallet) or 0) > 0)
            shrunk_wr = (wins + 0.5 * 5) / (len(resolved_trades) + 5)
            consistency_score = clamp(shrunk_wr * 100, 0, 100)
        else:
            consistency_score = 50

        # Volume Score (10%)
        vol = totals["total_usdc"]
        volume_score = clamp(math.log10(max(vol, 1)) / math.log10(VOLUME_ANCHOR) * 100, 0, 100)

        # Early Entry Score (15%)
        entry_hours_list = []
        for cid, data in wallet_markets[wallet].items():
            created = data.get("market_created") or market_created.get(cid)
            first   = data.get("first_trade_ts")
            t_created = parse_ts(created)
            t_first   = parse_ts(first)
            if t_created and t_first:
                hours = (t_first - t_created).total_seconds() / 3600
                entry_hours_list.append(hours)

        if entry_hours_list:
            avg_hours   = sum(entry_hours_list) / len(entry_hours_list)
            early_score = clamp((1 - avg_hours / (EARLY_DAYS * 24)) * 100, 0, 100)
        else:
            early_score = 50

        # Composite
        final_score = (
            roi_score         * 0.30 +
            calib_score       * 0.25 +
            consistency_score * 0.20 +
            early_score       * 0.15 +
            volume_score      * 0.10
        )

        top_markets = list({d["market_name"] for d in wallet_markets[wallet].values()})[:3]

        ranked.append({
            "wallet":             wallet,
            "score":              round(final_score, 1),
            "roi_score":          round(roi_score, 1),
            "calibration_score":  round(calib_score, 1),
            "consistency_score":  round(consistency_score, 1),
            "early_entry_score":  round(early_score, 1),
            "volume_score":       round(volume_score, 1),
            "total_usdc":         round(totals["total_usdc"], 2),
            "trade_count":        totals["total_trades"],
            "market_count":       len(totals["market_ids"]),
            "roi":                round(roi * 100, 1) if roi is not None else None,
            "top_markets":        top_markets,
        })

    ranked.sort(key=lambda x: x["score"], reverse=True)
    ranked = ranked[:MAX_WALLETS]
    print(f"  Ranked {len(ranked)} wallets")
    return ranked

# ── Step 6: Write JSON ───────────────────────────────────────
def write_output(active_markets, ranked):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    market_list = [{
        "id":        m.get("conditionId") or m.get("condition_id", ""),
        "question":  m.get("question") or m.get("title", ""),
        "volume":    m.get("volume", 0),
        "liquidity": m.get("liquidity", 0),
        "end_date":  m.get("endDate") or m.get("end_date", ""),
    } for m in active_markets]

    output = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "whale_count":  len(ranked),
        "market_count": len(market_list),
        "whales":       ranked,
        "markets":      market_list,
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    size_kb = os.path.getsize(OUTPUT_FILE) / 1024
    print(f"\n✓ Written to {OUTPUT_FILE}  ({size_kb:.1f} KB)")

# ── Main ─────────────────────────────────────────────────────
def main():
    print("=" * 55)
    print("  Polymarket Whale Tracker")
    print("=" * 55)

    active_markets            = fetch_markets()
    if not active_markets:
        print("No markets returned. Exiting.")
        return

    resolved_markets          = fetch_resolved_markets()
    wallet_markets, wallet_totals = fetch_whale_trades(active_markets)

    if not wallet_totals:
        print("No whale trades found. Writing empty output.")
        write_output(active_markets, [])
        return

    wallet_roi, wallet_calib  = compute_roi_calibration(wallet_markets, resolved_markets)
    ranked                    = score_wallets(wallet_markets, wallet_totals,
                                              wallet_roi, wallet_calib, active_markets)
    write_output(active_markets, ranked)

    if ranked:
        print("\n── Top 5 Whales ──────────────────────────────────────")
        for i, w in enumerate(ranked[:5], 1):
            roi_str = f"{w['roi']:+.1f}%" if w["roi"] is not None else "n/a"
            print(f"  {i}. {w['wallet'][:12]}... | Score: {w['score']} | Vol: {fmt(w['total_usdc'])} | ROI: {roi_str}")

if __name__ == "__main__":
    main()
