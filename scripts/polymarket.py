# ============================================================
# Polymarket Whale Tracker
# Strategy:
#   1. Fetch top 30 active markets
#   2. For each market, get top holders via /holders
#   3. Collect unique whale wallets
#   4. For each wallet, fetch positions (PnL) and trades
#   5. Score using 5-factor model
#   6. Write data/whales.json
#
# Scoring weights:
#   ROI           30%
#   Calibration   25%
#   Consistency   20%
#   Early Entry   15%
#   Volume        10%
# ============================================================
# Dependencies: requests
# No API key required
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

MAX_MARKETS     = 30        # active markets to scan
HOLDERS_PER_MKT = 10        # top holders to pull per market
MAX_WALLETS     = 50        # top wallets in output
MIN_VALUE       = 500       # min position value (USDC) to be a whale
SLEEP           = 0.25      # seconds between API calls

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

def parse_ts(s):
    if not s:
        return None
    try:
        if isinstance(s, (int, float)):
            return datetime.fromtimestamp(float(s), tz=timezone.utc)
        s = str(s)
        if s.isdigit():
            return datetime.fromtimestamp(int(s), tz=timezone.utc)
        for fmt_str in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
                        "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(s, fmt_str).replace(tzinfo=timezone.utc)
            except Exception:
                pass
    except Exception:
        pass
    return None

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

# ── Step 2: Fetch resolved markets for scoring ───────────────
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
        return {}
    markets = data if isinstance(data, list) else data.get("markets", [])

    # Build lookup: conditionId → resolution (1.0 = YES won, 0.0 = NO won)
    resolved = {}
    for m in markets:
        cid    = m.get("conditionId") or m.get("condition_id", "")
        prices = m.get("outcomePrices")
        if cid and prices:
            try:
                p = json.loads(prices) if isinstance(prices, str) else prices
                resolved[cid] = float(p[0])
            except Exception:
                pass

    print(f"  Found {len(resolved)} resolved markets with outcomes")
    return resolved

# ── Step 3: Collect whale wallets via /holders ───────────────
def collect_whale_wallets(markets):
    print(f"\nCollecting top holders from {len(markets)} markets...")
    whale_set   = {}   # wallet → {name, pseudonym, profile}
    market_meta = {}   # conditionId → market info

    for market in markets:
        cid         = market.get("conditionId") or market.get("condition_id", "")
        market_name = market.get("question") or market.get("title", "Unknown")
        created_at  = market.get("createdAt") or market.get("created_at")
        if not cid:
            continue

        market_meta[cid] = {
            "name": market_name,
            "created_at": created_at,
            "volume": market.get("volume", 0)
        }

        holders_data = get(f"{DATA_API}/holders", params={
            "market": cid,
            "limit": HOLDERS_PER_MKT
        })

        if not holders_data:
            continue

        # /holders returns list of token groups, each with holders list
        for token_group in holders_data:
            for h in token_group.get("holders", []):
                wallet = h.get("proxyWallet")
                amount = float(h.get("amount", 0))
                if wallet and amount >= MIN_VALUE:
                    if wallet not in whale_set:
                        whale_set[wallet] = {
                            "name":       h.get("name", ""),
                            "pseudonym":  h.get("pseudonym", ""),
                            "profile_img": h.get("profileImageOptimized") or h.get("profileImage", "")
                        }

        print(f"  ✓ {market_name[:55]}")

    print(f"\n  Found {len(whale_set)} unique whale wallets")
    return whale_set, market_meta

# ── Step 4: Fetch positions + trades per wallet ──────────────
def fetch_wallet_data(whale_set, market_meta, resolved_lookup):
    print(f"\nFetching positions and trades for {len(whale_set)} wallets...")
    wallet_scores = []

    for wallet, profile in whale_set.items():
        # ── Positions ────────────────────────────────────────
        positions = get(f"{DATA_API}/positions", params={
            "user": wallet,
            "limit": 500,
            "sizeThreshold": 1,
            "sortBy": "CASHPNL"
        })
        if not positions:
            positions = []

        total_initial = sum(float(p.get("initialValue") or 0) for p in positions)
        total_current = sum(float(p.get("currentValue") or 0) for p in positions)
        total_pnl     = sum(float(p.get("cashPnl") or 0) for p in positions)
        realized_pnl  = sum(float(p.get("realizedPnl") or 0) for p in positions)

        # ROI from positions
        roi = (total_current - total_initial) / total_initial if total_initial > 0 else None

        # Calibration: check positions in resolved markets
        brier_scores = []
        wins, resolved_count = 0, 0
        for p in positions:
            cid = p.get("conditionId", "")
            if cid in resolved_lookup:
                resolution = resolved_lookup[cid]
                avg_price  = float(p.get("avgPrice") or 0)
                if avg_price > 0:
                    brier_scores.append(1 - (avg_price - resolution) ** 2)
                    resolved_count += 1
                    if (resolution >= 0.5 and avg_price >= 0.5) or \
                       (resolution < 0.5 and avg_price < 0.5):
                        wins += 1

        # ── Trades ────────────────────────────────────────────
        trades = get(f"{DATA_API}/trades", params={
            "user": wallet,
            "limit": 500,
            "filterType": "CASH",
            "filterAmount": 100
        })
        if not trades:
            trades = []

        total_usdc   = sum(float(t.get("usdcSize") or 0) for t in trades)
        trade_count  = len(trades)
        market_ids   = set(t.get("conditionId", "") for t in trades)

        # Early entry: compare first trade timestamp vs market creation
        entry_hours_list = []
        for t in trades:
            cid      = t.get("conditionId", "")
            ts       = t.get("timestamp")
            meta     = market_meta.get(cid, {})
            created  = meta.get("created_at")
            t_trade  = parse_ts(ts)
            t_create = parse_ts(created)
            if t_trade and t_create:
                hours = (t_trade - t_create).total_seconds() / 3600
                if hours >= 0:
                    entry_hours_list.append(hours)

        # Top markets active in
        top_market_names = list({
            market_meta[t.get("conditionId", "")]["name"]
            for t in trades
            if t.get("conditionId", "") in market_meta
        })[:3]

        # ── Scoring ───────────────────────────────────────────

        # ROI Score (30%)
        roi_score = clamp(
            (roi - ROI_FLOOR) / (ROI_CAP - ROI_FLOOR) * 100, 0, 100
        ) if roi is not None else 50

        # Calibration Score (25%)
        calib_score = clamp(
            (sum(brier_scores) / len(brier_scores)) * 100, 0, 100
        ) if brier_scores else 50

        # Consistency Score (20%) — shrunken win rate
        shrunk_wr = (wins + 0.5 * 5) / (resolved_count + 5) if resolved_count > 0 else 0.5
        consistency_score = clamp(shrunk_wr * 100, 0, 100)

        # Volume Score (10%)
        volume_score = clamp(
            math.log10(max(total_usdc, 1)) / math.log10(VOLUME_ANCHOR) * 100, 0, 100
        )

        # Early Entry Score (15%)
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

        wallet_scores.append({
            "wallet":             wallet,
            "name":               profile.get("name") or profile.get("pseudonym") or "",
            "pseudonym":          profile.get("pseudonym", ""),
            "profile_img":        profile.get("profile_img", ""),
            "score":              round(final_score, 1),
            "roi_score":          round(roi_score, 1),
            "calibration_score":  round(calib_score, 1),
            "consistency_score":  round(consistency_score, 1),
            "early_entry_score":  round(early_score, 1),
            "volume_score":       round(volume_score, 1),
            "roi":                round(roi * 100, 1) if roi is not None else None,
            "total_pnl":          round(total_pnl, 2),
            "realized_pnl":       round(realized_pnl, 2),
            "total_usdc":         round(total_usdc, 2),
            "trade_count":        trade_count,
            "market_count":       len(market_ids),
            "position_count":     len(positions),
            "top_markets":        top_market_names,
        })

        print(f"  ✓ {wallet[:10]}... | Score: {round(final_score,1)} | ROI: {round(roi*100,1) if roi else 'n/a'}%")

    wallet_scores.sort(key=lambda x: x["score"], reverse=True)
    return wallet_scores[:MAX_WALLETS]

# ── Step 5: Write JSON ───────────────────────────────────────
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
        write_output([], [])
        return

    resolved_lookup              = fetch_resolved_markets()
    whale_set, market_meta       = collect_whale_wallets(active_markets)

    if not whale_set:
        print("No whale wallets found. Writing empty output.")
        write_output(active_markets, [])
        return

    ranked = fetch_wallet_data(whale_set, market_meta, resolved_lookup)
    write_output(active_markets, ranked)

    if ranked:
        print("\n── Top 5 Whales ──────────────────────────────────────")
        for i, w in enumerate(ranked[:5], 1):
            name    = w["name"] or w["pseudonym"] or w["wallet"][:10] + "..."
            roi_str = f"{w['roi']:+.1f}%" if w["roi"] is not None else "n/a"
            print(f"  {i}. {name:<20} | Score: {w['score']} | Vol: {fmt(w['total_usdc'])} | ROI: {roi_str}")

if __name__ == "__main__":
    main()
