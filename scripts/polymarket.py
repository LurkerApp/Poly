# ============================================================
# Polymarket Whale Tracker
# Scoring weights:
#   ROI           30%
#   Calibration   25%
#   Consistency   20%
#   Early Entry   15%
#   Volume        10%
# ============================================================
# Dependencies: requests
# No API key required — Polymarket APIs are public
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
CLOB_API        = "https://clob.polymarket.com"
DATA_API        = "https://data-api.polymarket.com"

WHALE_MIN_USDC  = 500       # minimum trade size to qualify
MAX_MARKETS     = 30        # active markets to scan
MAX_WALLETS     = 50        # top wallets in output
MIN_MARKETS     = 5         # min resolved markets to be scored
MIN_VOLUME      = 1000      # min lifetime USDC volume
SLEEP           = 0.3       # seconds between API calls

# Scoring bounds
ROI_FLOOR       = -0.50     # -50% ROI → score 0
ROI_CAP         =  1.00     # +100% ROI → score 100
VOLUME_ANCHOR   = 500000    # 500k USDC = top volume score
EARLY_DAYS      = 7         # days ahead of market = max early entry score

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

# ── Step 2: Fetch resolved markets for ROI/calibration ───────
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
    # Only keep markets that have a clear winner
    resolved = [m for m in markets if m.get("outcomePrices") or m.get("outcome")]
    print(f"  Found {len(resolved)} resolved markets")
    return resolved

# ── Step 3: Fetch whale trades across markets ─────────────────
def fetch_whale_trades(markets):
    print(f"\nScanning for trades >= ${WHALE_MIN_USDC}...")
    # wallet → per-market trade data
    wallet_markets = defaultdict(lambda: defaultdict(lambda: {
        "usdc": 0, "shares": 0, "avg_price": 0,
        "trades": 0, "first_trade_ts": None,
        "prices": [], "market_created": None,
        "market_name": ""
    }))

    wallet_totals = defaultdict(lambda: {
        "total_usdc": 0, "total_trades": 0,
        "market_ids": set()
    })

    for market in markets:
        cid          = market.get("conditionId") or market.get("condition_id", "")
        market_name  = market.get("question") or market.get("title", "Unknown")
        created_at   = market.get("createdAt") or market.get("created_at")
        if not cid:
            continue

        trades = get(f"{CLOB_API}/trades", params={"market": cid, "limit": 500})
        if not trades:
            continue

        trade_list = trades if isinstance(trades, list) else trades.get("data", [])

        for t in trade_list:
            size  = float(t.get("size", 0) or 0)
            price = float(t.get("price", 0) or 0)
            usdc  = size * price
            if usdc < WHALE_MIN_USDC:
                continue

            ts     = t.get("timestamp") or t.get("created_at", "")
            side   = (t.get("side") or "").upper()

            for wallet in filter(None, [t.get("maker_address") or t.get("makerAddress"),
                                         t.get("taker_address") or t.get("takerAddress")]):
                wm = wallet_markets[wallet][cid]
                wm["usdc"]        += usdc
                wm["shares"]      += size
                wm["trades"]      += 1
                wm["prices"].append(price)
                wm["market_name"]  = market_name
                wm["market_created"] = created_at
                if not wm["first_trade_ts"] or ts < wm["first_trade_ts"]:
                    wm["first_trade_ts"] = ts

                wt = wallet_totals[wallet]
                wt["total_usdc"]   += usdc
                wt["total_trades"] += 1
                wt["market_ids"].add(cid)

        print(f"  ✓ {market_name[:55]}")

    return wallet_markets, wallet_totals

# ── Step 4: Compute ROI + calibration from resolved markets ───
def compute_roi_calibration(wallet_markets, resolved_markets):
    """
    For each wallet, check if they traded in any resolved market.
    ROI = (outcome_price - avg_entry_price) / avg_entry_price
    Calibration = 1 - (avg_entry_price - resolution)^2  (Brier-style)
    """
    # Build lookup: condition_id → resolution price (1.0 = YES won, 0.0 = NO won)
    resolved_lookup = {}
    for m in resolved_markets:
        cid = m.get("conditionId") or m.get("condition_id", "")
        prices = m.get("outcomePrices")
        if prices:
            try:
                outcome_prices = json.loads(prices) if isinstance(prices, str) else prices
                # First token is YES; if it resolved YES → 1.0
                resolution = float(outcome_prices[0])
                resolved_lookup[cid] = resolution
            except Exception:
                pass

    wallet_roi   = {}
    wallet_calib = {}

    for wallet, markets_data in wallet_markets.items():
        roi_list   = []
        brier_list = []

        for cid, data in markets_data.items():
            if cid not in resolved_lookup:
                continue
            resolution = resolved_lookup[cid]
            avg_price  = sum(data["prices"]) / len(data["prices"]) if data["prices"] else 0.5
            if avg_price <= 0:
                continue

            roi = (resolution - avg_price) / avg_price
            roi_list.append(roi)

            # Brier score component: lower = better, so invert for score
            brier = 1 - (avg_price - resolution) ** 2
            brier_list.append(brier)

        wallet_roi[wallet]   = sum(roi_list) / len(roi_list) if roi_list else None
        wallet_calib[wallet] = sum(brier_list) / len(brier_list) if brier_list else None

    return wallet_roi, wallet_calib

# ── Step 5: Score each wallet ─────────────────────────────────
def score_wallets(wallet_markets, wallet_totals, wallet_roi, wallet_calib, active_markets):
    print(f"\nScoring wallets...")

    # Build market creation lookup for early entry score
    market_created = {}
    for m in active_markets:
        cid = m.get("conditionId") or m.get("condition_id", "")
        market_created[cid] = m.get("createdAt") or m.get("created_at")

    ranked = []

    for wallet, totals in wallet_totals.items():
        if totals["total_trades"] < 1:
            continue
        if totals["total_usdc"] < MIN_VOLUME:
            continue

        # ── ROI Score (30%) ──────────────────────────────────
        roi = wallet_roi.get(wallet)
        if roi is not None:
            roi_score = clamp((roi - ROI_FLOOR) / (ROI_CAP - ROI_FLOOR) * 100, 0, 100)
        else:
            roi_score = 50  # neutral if no resolved markets

        # ── Calibration Score (25%) ──────────────────────────
        calib = wallet_calib.get(wallet)
        if calib is not None:
            calib_score = clamp(calib * 100, 0, 100)
        else:
            # Fallback: shrunken win rate
            wins   = sum(1 for c, d in wallet_markets[wallet].items()
                         if wallet_roi.get(wallet, 0) and wallet_roi[wallet] > 0)
            total  = len(wallet_markets[wallet])
            shrunk = (wins + 0.5 * 5) / (total + 5)   # shrink toward 0.5
            calib_score = clamp(shrunk * 100, 0, 100)

        # ── Consistency Score (20%) ──────────────────────────
        resolved_count = sum(1 for c in wallet_markets[wallet] if wallet_roi.get(wallet) is not None)
        if resolved_count >= 1:
            wins       = sum(1 for c, d in wallet_markets[wallet].items()
                             if wallet_roi.get(wallet, 0) and wallet_roi[wallet] > 0)
            win_rate   = wins / max(resolved_count, 1)
            shrunk_wr  = (wins + 0.5 * 5) / (resolved_count + 5)
            consistency_score = clamp(shrunk_wr * 100, 0, 100)
        else:
            consistency_score = 50

        # ── Volume Score (10%) ───────────────────────────────
        vol = totals["total_usdc"]
        if vol > 0:
            volume_score = clamp(math.log10(vol) / math.log10(VOLUME_ANCHOR) * 100, 0, 100)
        else:
            volume_score = 0

        # ── Early Entry Score (15%) ──────────────────────────
        entry_hours_list = []
        for cid, data in wallet_markets[wallet].items():
            created = data.get("market_created") or market_created.get(cid)
            first   = data.get("first_trade_ts")
            if created and first:
                try:
                    def parse_ts(s):
                        s = str(s)
                        for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
                                    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                            try:
                                return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
                            except Exception:
                                pass
                        return None
                    t_created = parse_ts(created)
                    t_first   = parse_ts(first)
                    if t_created and t_first:
                        hours = (t_first - t_created).total_seconds() / 3600
                        entry_hours_list.append(hours)
                except Exception:
                    pass

        if entry_hours_list:
            avg_hours      = sum(entry_hours_list) / len(entry_hours_list)
            max_hours      = EARLY_DAYS * 24
            early_score    = clamp((1 - avg_hours / max_hours) * 100, 0, 100)
        else:
            early_score = 50

        # ── Composite Score ──────────────────────────────────
        final_score = (
            roi_score         * 0.30 +
            calib_score       * 0.25 +
            consistency_score * 0.20 +
            early_score       * 0.15 +
            volume_score      * 0.10
        )

        # Top 3 markets
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

    active_markets   = fetch_markets()
    if not active_markets:
        print("No markets returned. Exiting.")
        return

    resolved_markets = fetch_resolved_markets()
    wallet_markets, wallet_totals = fetch_whale_trades(active_markets)

    if not wallet_totals:
        print("No whale trades found. Exiting.")
        return

    wallet_roi, wallet_calib = compute_roi_calibration(wallet_markets, resolved_markets)
    ranked = score_wallets(wallet_markets, wallet_totals, wallet_roi, wallet_calib, active_markets)
    write_output(active_markets, ranked)

    if ranked:
        print("\n── Top 5 Whales ─────────────────────────────────────")
        for i, w in enumerate(ranked[:5], 1):
            roi_str = f"{w['roi']:+.1f}%" if w["roi"] is not None else "n/a"
            print(f"  {i}. {w['wallet'][:12]}... | Score: {w['score']} | Vol: {fmt(w['total_usdc'])} | ROI: {roi_str}")

if __name__ == "__main__":
    main()
