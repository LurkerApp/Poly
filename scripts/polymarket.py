# ============================================================
# Polymarket Whale Tracker — Live Signals
# ============================================================
# Strategy:
#   1. Fetch top 20 active markets by 24hr volume
#   2. Pull top 100 trades >= $500 USDC per market
#   3. Collect unique whale wallets (cap at 50)
#   4. Enrich each wallet: positions + activity
#   5. Score using 5-factor model
#   6. Write data/signals.json, data/markets.json
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
from dataclasses import dataclass
from collections import defaultdict

# ── Config ───────────────────────────────────────────────────
@dataclass
class Config:
    # Discovery
    max_markets:           int   = 20
    whale_min_usdc:        float = 500
    trades_per_market:     int   = 100
    max_wallets_to_enrich: int   = 50
    max_wallets_output:    int   = 50

    # Scoring bounds
    roi_floor:             float = -0.50
    roi_cap:               float =  1.00
    volume_anchor:         float = 500_000
    early_days:            int   = 7

    # Scoring weights (must sum to 1.0)
    w_roi:                 float = 0.30
    w_calibration:         float = 0.25
    w_consistency:         float = 0.20
    w_early_entry:         float = 0.15
    w_volume:              float = 0.10

    # API
    sleep:                 float = 0.20
    timeout:               int   = 15

    # Output — writes to signals.json, NOT whales.json
    output_dir:            str   = "data"
    output_file:           str   = "data/signals.json"
    markets_file:          str   = "data/markets.json"
    meta_file:             str   = "data/signals_meta.json"

CFG = Config()

GAMMA_API = "https://gamma-api.polymarket.com"
DATA_API  = "https://data-api.polymarket.com"

# ── Helpers ──────────────────────────────────────────────────
def get(url, params=None):
    time.sleep(CFG.sleep)
    try:
        resp = requests.get(url, params=params, timeout=CFG.timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  ERROR {url}: {e}")
        return None

def clamp(val, lo=0.0, hi=100.0):
    return max(lo, min(hi, val))

def fmt(val):
    if abs(val) >= 1e6: return f"${val/1e6:.1f}M"
    if abs(val) >= 1e3: return f"${val/1e3:.0f}K"
    return f"${val:.0f}"

def parse_ts(s):
    if s is None:
        return None
    try:
        if isinstance(s, (int, float)):
            return datetime.fromtimestamp(float(s), tz=timezone.utc)
        s = str(s).strip()
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

def z_score(wins, n):
    if n < 5:
        return 0.0
    return (wins / n - 0.5) / math.sqrt(0.25 / n)

# ── Step 1: Active markets ────────────────────────────────────
def fetch_markets():
    print("Fetching active markets...")
    data = get(f"{GAMMA_API}/markets", params={
        "active": "true", "closed": "false",
        "limit": CFG.max_markets,
        "order": "volume24hr", "ascending": "false"
    })
    if not data:
        return []
    markets = data if isinstance(data, list) else data.get("markets", [])
    print(f"  Found {len(markets)} active markets")
    return markets

# ── Step 2: Resolved market lookup ────────────────────────────
def fetch_resolved_lookup():
    print("Fetching resolved markets...")
    data = get(f"{GAMMA_API}/markets", params={
        "active": "false", "closed": "true",
        "limit": 200, "order": "endDate", "ascending": "false"
    })
    if not data:
        return {}
    markets = data if isinstance(data, list) else data.get("markets", [])
    lookup = {}
    for m in markets:
        cid    = m.get("conditionId") or m.get("condition_id", "")
        prices = m.get("outcomePrices")
        if cid and prices:
            try:
                p = json.loads(prices) if isinstance(prices, str) else prices
                lookup[cid] = float(p[0])
            except Exception:
                pass
    print(f"  Built resolution lookup for {len(lookup)} markets")
    return lookup

# ── Step 3: Scan markets for whale wallets ────────────────────
def discover_whales(markets):
    print(f"\nScanning {len(markets)} markets for trades >= ${CFG.whale_min_usdc}...")

    wallet_profiles = {}
    wallet_markets  = defaultdict(set)
    market_meta     = {}

    for m in markets:
        cid         = m.get("conditionId") or m.get("condition_id", "")
        market_name = m.get("question") or m.get("title", "Unknown")
        created_at  = m.get("createdAt") or m.get("created_at")
        if not cid:
            continue

        market_meta[cid] = {
            "name":       market_name,
            "created_at": created_at,
            "volume":     m.get("volume", 0),
        }

        trades = get(f"{DATA_API}/trades", params={
            "market":       cid,
            "limit":        CFG.trades_per_market,
            "takerOnly":    "false",
            "filterType":   "CASH",
            "filterAmount": CFG.whale_min_usdc,
        })

        if not trades:
            print(f"  - {market_name[:55]} (no data)")
            continue

        trade_list  = trades if isinstance(trades, list) else trades.get("data", [])
        new_wallets = 0

        for t in trade_list:
            wallet = t.get("proxyWallet")
            if not wallet:
                continue

            usdc = float(t.get("size", 0)) * float(t.get("price", 0))
            if usdc < CFG.whale_min_usdc:
                continue

            wallet_markets[wallet].add(cid)

            if wallet not in wallet_profiles:
                wallet_profiles[wallet] = {
                    "name":       t.get("name") or t.get("pseudonym") or "",
                    "pseudonym":  t.get("pseudonym", ""),
                    "first_seen": parse_ts(t.get("timestamp")),
                }
                new_wallets += 1
            else:
                ts = parse_ts(t.get("timestamp"))
                if ts and (wallet_profiles[wallet]["first_seen"] is None or
                           ts < wallet_profiles[wallet]["first_seen"]):
                    wallet_profiles[wallet]["first_seen"] = ts

        print(f"  ✓ {market_name[:55]} — {len(trade_list)} trades, {new_wallets} new wallets")

    if len(wallet_profiles) > CFG.max_wallets_to_enrich:
        print(f"\n  Capping to {CFG.max_wallets_to_enrich} wallets for runtime")
        wallet_profiles = dict(list(wallet_profiles.items())[:CFG.max_wallets_to_enrich])

    print(f"\n  Total whale wallets to enrich: {len(wallet_profiles)}")
    return wallet_profiles, wallet_markets, market_meta

# ── Step 4: Enrich and score wallets ─────────────────────────
def enrich_and_score(wallet_profiles, wallet_markets, market_meta,
                     resolved_lookup, active_markets):
    print(f"\nEnriching {len(wallet_profiles)} wallets...")

    mkt_current_price = {}
    mkt_created       = {}
    for m in active_markets:
        cid = m.get("conditionId") or m.get("condition_id", "")
        mkt_created[cid] = m.get("createdAt") or m.get("created_at")
        prices = m.get("outcomePrices")
        if prices:
            try:
                p = json.loads(prices) if isinstance(prices, str) else prices
                mkt_current_price[cid] = float(p[0])
            except Exception:
                pass
    for cid, meta in market_meta.items():
        if cid not in mkt_created:
            mkt_created[cid] = meta.get("created_at")

    scored = []

    for wallet, profile in wallet_profiles.items():

        # ── Positions ────────────────────────────────────────
        positions = get(f"{DATA_API}/positions", params={
            "user": wallet, "limit": 500, "sizeThreshold": 0
        }) or []

        total_initial = sum(float(p.get("initialValue") or 0) for p in positions)
        cash_pnl      = sum(float(p.get("cashPnl") or 0) for p in positions)
        realized_pnl  = sum(float(p.get("realizedPnl") or 0) for p in positions)

        roi = (cash_pnl / total_initial) if total_initial > 0 else None

        brier_scores = []
        wins_all     = 0
        resolved_cnt = 0

        for p in positions:
            cid       = p.get("conditionId", "")
            avg_price = float(p.get("avgPrice") or 0)
            if cid not in resolved_lookup or avg_price <= 0:
                continue
            resolution = resolved_lookup[cid]
            brier_scores.append(1 - (avg_price - resolution) ** 2)
            resolved_cnt += 1
            won = ((resolution >= 0.5 and avg_price >= 0.5) or
                   (resolution <  0.5 and avg_price <  0.5))
            if won:
                wins_all += 1

        win_rate = wins_all / resolved_cnt if resolved_cnt > 0 else 0
        z        = z_score(wins_all, resolved_cnt)

        # ── Activity ─────────────────────────────────────────
        activity = get(f"{DATA_API}/activity", params={
            "user": wallet, "limit": 500,
            "type": "TRADE",
            "sortBy": "TIMESTAMP", "sortDirection": "DESC"
        }) or []

        last_active    = None
        trade_count    = len(activity)
        all_market_ids = set(wallet_markets[wallet])
        usdc_volume    = 0.0

        for a in activity:
            ts = parse_ts(a.get("timestamp"))
            if ts and last_active is None:
                last_active = ts
            cid = a.get("conditionId", "")
            if cid:
                all_market_ids.add(cid)
            usdc_volume += float(a.get("usdcSize") or a.get("cashAmount") or 0)

        # ── Early entry ───────────────────────────────────────
        mkt_first = defaultdict(list)
        for a in reversed(activity):
            cid = a.get("conditionId", "")
            ts  = parse_ts(a.get("timestamp"))
            if cid and ts:
                mkt_first[cid].append(ts)

        entry_hours = []
        for cid, times in mkt_first.items():
            t_c = parse_ts(mkt_created.get(cid))
            t_f = min(times, default=None)
            if t_c and t_f and t_f >= t_c:
                entry_hours.append((t_f - t_c).total_seconds() / 3600)

        # Top markets by frequency
        mkt_counts = defaultdict(int)
        for a in activity:
            title = a.get("title") or ""
            if title:
                mkt_counts[title] += 1
        top_markets = [m for m, _ in sorted(
            mkt_counts.items(), key=lambda x: x[1], reverse=True)][:3]

        # ── Open position signals ─────────────────────────────
        signals = []
        for p in positions:
            cid       = p.get("conditionId", "")
            avg_price = float(p.get("avgPrice") or 0)
            cur_price = mkt_current_price.get(cid)
            usdc_size = float(p.get("currentValue") or 0)
            title     = p.get("title") or ""
            outcome   = p.get("outcome", "")

            if avg_price >= 0.90 or not cur_price or usdc_size < 500:
                continue
            drift = abs(cur_price - avg_price) / max(avg_price, 0.01)
            if drift >= 0.07:
                label = "SKIP"
            elif drift >= 0.03 or avg_price >= 0.75:
                label = "LATE"
            else:
                label = "ENTER"

            signals.append({
                "market":    title,
                "signal":    label,
                "avg_price": round(avg_price, 4),
                "cur_price": round(cur_price, 4),
                "usdc_size": round(usdc_size, 2),
                "outcome":   outcome,
            })
        signals.sort(key=lambda x: {"ENTER": 0, "LATE": 1, "SKIP": 2}[x["signal"]])

        # ── 5-Factor Scoring ─────────────────────────────────
        roi_score = clamp(
            (roi - CFG.roi_floor) / (CFG.roi_cap - CFG.roi_floor) * 100
        ) if roi is not None else 50.0

        calib_score = clamp(
            sum(brier_scores) / len(brier_scores) * 100
        ) if brier_scores else 50.0

        shrunk = (wins_all + 0.5 * 5) / (resolved_cnt + 5) if resolved_cnt > 0 else 0.5
        consistency_score = clamp(shrunk * 100)

        volume_score = clamp(
            math.log10(max(usdc_volume, 1)) / math.log10(CFG.volume_anchor) * 100
        ) if usdc_volume > 0 else 0.0

        if entry_hours:
            avg_h       = sum(entry_hours) / len(entry_hours)
            early_score = clamp((1 - avg_h / (CFG.early_days * 24)) * 100)
        else:
            early_score = 50.0

        final_score = (
            roi_score         * CFG.w_roi         +
            calib_score       * CFG.w_calibration  +
            consistency_score * CFG.w_consistency  +
            early_score       * CFG.w_early_entry  +
            volume_score      * CFG.w_volume
        )

        name = profile.get("name") or profile.get("pseudonym") or ""
        scored.append({
            "wallet":             wallet,
            "name":               name,
            "score":              round(final_score, 1),
            "roi_score":          round(roi_score, 1),
            "calibration_score":  round(calib_score, 1),
            "consistency_score":  round(consistency_score, 1),
            "early_entry_score":  round(early_score, 1),
            "volume_score":       round(volume_score, 1),
            "roi":                round(roi * 100, 1) if roi is not None else None,
            "cash_pnl":           round(cash_pnl, 2),
            "realized_pnl":       round(realized_pnl, 2),
            "total_usdc":         round(usdc_volume, 2),
            "trade_count":        trade_count,
            "market_count":       len(all_market_ids),
            "position_count":     len(positions),
            "resolved_count":     resolved_cnt,
            "win_rate":           round(win_rate * 100, 1),
            "z_score":            round(z, 2),
            "last_active":        last_active.isoformat() if last_active else None,
            "top_markets":        top_markets,
            "signals":            signals,
        })

        roi_str   = f"{roi*100:+.1f}%" if roi is not None else "n/a"
        sig_enter = sum(1 for s in signals if s["signal"] == "ENTER")
        print(f"  ✓ {(name or wallet[:10]+'...'):<22} Score:{round(final_score,1):<6} "
              f"WR:{win_rate*100:.0f}% ROI:{roi_str} ENTER:{sig_enter}")

    scored.sort(key=lambda x: x["score"], reverse=True)
    print(f"\n  Scored {len(scored)} wallets")
    return scored[:CFG.max_wallets_output]

# ── Step 5: Write output files ────────────────────────────────
def write_output(ranked, active_markets):
    os.makedirs(CFG.output_dir, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    market_list = [{
        "id":        m.get("conditionId") or m.get("condition_id", ""),
        "question":  m.get("question") or m.get("title", ""),
        "volume":    m.get("volume", 0),
        "liquidity": m.get("liquidity", 0),
        "end_date":  m.get("endDate") or m.get("end_date", ""),
    } for m in active_markets]

    with open(CFG.output_file, "w") as f:
        json.dump({
            "last_updated": now,
            "whale_count":  len(ranked),
            "market_count": len(market_list),
            "whales":       ranked,
            "markets":      market_list,
        }, f, indent=2)

    with open(CFG.markets_file, "w") as f:
        json.dump({"last_updated": now, "markets": market_list}, f, indent=2)

    with open(CFG.meta_file, "w") as f:
        json.dump({
            "last_updated": now,
            "whale_count":  len(ranked),
            "market_count": len(market_list),
        }, f, indent=2)

    for path in [CFG.output_file, CFG.markets_file, CFG.meta_file]:
        kb = os.path.getsize(path) / 1024
        print(f"  ✓ {path}  ({kb:.1f} KB)")

# ── Main ─────────────────────────────────────────────────────
def main():
    print("=" * 55)
    print("  Polymarket Whale Tracker")
    print("=" * 55)

    active_markets  = fetch_markets()
    resolved_lookup = fetch_resolved_lookup()

    if not active_markets:
        print("No markets found. Writing empty output.")
        write_output([], [])
        return

    wallet_profiles, wallet_markets, market_meta = discover_whales(active_markets)

    if not wallet_profiles:
        print("No whale wallets found. Writing empty output.")
        write_output([], active_markets)
        return

    ranked = enrich_and_score(
        wallet_profiles, wallet_markets, market_meta,
        resolved_lookup, active_markets
    )

    print(f"\nWriting output files...")
    write_output(ranked, active_markets)

    if ranked:
        print(f"\n── Top 5 Whales ──────────────────────────────────────")
        for i, w in enumerate(ranked[:5], 1):
            label   = w["name"] or w["wallet"][:10] + "..."
            roi_str = f"{w['roi']:+.1f}%" if w["roi"] is not None else "n/a"
            sig_e   = sum(1 for s in w["signals"] if s["signal"] == "ENTER")
            print(f"  {i}. {label:<22} Score:{w['score']:<6} "
                  f"WR:{w['win_rate']}% ROI:{roi_str} ENTER:{sig_e}")
    else:
        print("\n  No wallets scored.")

    print("\n✓ Done")

if __name__ == "__main__":
    main()
