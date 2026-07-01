# ============================================================
# Polymarket Whale Tracker
# ============================================================
# Wallet qualification (auto, no manual picking):
#   >= 20 resolved bets
#   >= $10k PnL
#   >= 10% ROI
#   statistically skilled: z >= 1.5 OR (win_rate >= 80% AND n >= 30)
#   active within 14 days
#   30d win-rate >= 60%
#   drawdown < 50% of PnL
#
# Signal labels per position:
#   ENTER  — price near whale entry + real size + payoff worth it
#   LATE   — drift 3-7% OR entry 0.75-0.90
#   SKIP   — drift >7% OR size < $500
#   (entries >= 0.90 dropped entirely)
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
import statistics
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from collections import defaultdict

# ── Config ───────────────────────────────────────────────────
@dataclass
class Config:
    # Discovery
    leaderboard_limit:   int   = 200     # wallets to pull from leaderboard
    leaderboard_window:  str   = "1m"    # 1d | 7d | 1m | all
    max_wallets_output:  int   = 50      # wallets in final JSON
    max_markets:         int   = 30      # active markets in JSON

    # Wallet qualification thresholds
    min_resolved_bets:   int   = 20      # >= 20 resolved bets
    min_pnl:             float = 10_000  # >= $10k PnL
    min_roi:             float = 0.10    # >= 10% ROI
    min_z_score:         float = 1.5     # z >= 1.5 (statistical skill)
    min_winrate_alt:     float = 0.80    # OR win_rate >= 80%
    min_n_alt:           int   = 30      # with n >= 30
    active_days:         int   = 14      # active within 14 days
    min_winrate_30d:     float = 0.60    # 30d win-rate >= 60%
    max_drawdown_ratio:  float = 0.50    # drawdown < 50% of PnL

    # Signal thresholds
    signal_min_size:     float = 500     # min USDC for ENTER signal
    signal_late_min:     float = 0.03    # drift >= 3% = LATE
    signal_late_max:     float = 0.07    # drift >= 7% = SKIP
    signal_late_entry:   float = 0.75    # entry >= 0.75 = LATE
    signal_drop_entry:   float = 0.90    # entry >= 0.90 = drop

    # Scoring bounds
    roi_floor:           float = -0.50
    roi_cap:             float =  1.00
    volume_anchor:       float = 500_000
    early_days:          int   = 7

    # Weights (must sum to 1.0)
    w_roi:               float = 0.30
    w_calibration:       float = 0.25
    w_consistency:       float = 0.20
    w_early_entry:       float = 0.15
    w_volume:            float = 0.10

    # API
    sleep:               float = 0.25
    timeout:             int   = 15

    # Output
    output_dir:          str   = "data"
    output_file:         str   = "data/whales.json"
    markets_file:        str   = "data/markets.json"
    meta_file:           str   = "data/last_updated.json"

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
    """Binomial z-score vs 50% null hypothesis."""
    if n < 5:
        return 0.0
    p = wins / n
    return (p - 0.5) / math.sqrt(0.5 * 0.5 / n)

# ── Step 1: Leaderboard ──────────────────────────────────────
def fetch_leaderboard():
    print(f"Fetching leaderboard (window={CFG.leaderboard_window}, limit={CFG.leaderboard_limit})...")
    data = get(f"{DATA_API}/leaderboard", params={
        "window": CFG.leaderboard_window,
        "limit":  CFG.leaderboard_limit,
        "sortBy": "PROFIT"
    })
    if not data:
        data = get(f"{DATA_API}/leaderboard", params={
            "window": CFG.leaderboard_window,
            "limit":  CFG.leaderboard_limit,
        })
    if not data:
        return []
    entries = data if isinstance(data, list) else data.get("data", data.get("leaderboard", []))
    print(f"  Found {len(entries)} wallets")
    return entries

# ── Step 2: Active markets ───────────────────────────────────
def fetch_markets():
    print("Fetching active markets...")
    data = get(f"{GAMMA_API}/markets", params={
        "active": "true", "closed": "false",
        "limit": CFG.max_markets, "order": "volume24hr", "ascending": "false"
    })
    if not data:
        return []
    markets = data if isinstance(data, list) else data.get("markets", [])
    print(f"  Found {len(markets)} active markets")
    return markets

# ── Step 3: Resolved market lookup ───────────────────────────
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

# ── Step 4: Signal label for a position ─────────────────────
def signal_label(avg_price, current_price, usdc_size):
    """
    ENTER  — near entry, real size, payoff worth it
    LATE   — some drift or high entry price
    SKIP   — too much drift, too small, or entry too high
    DROP   — entries >= 0.90 dropped entirely
    """
    if avg_price is None or current_price is None:
        return "SKIP"
    if avg_price >= CFG.signal_drop_entry:
        return "DROP"
    drift = abs(current_price - avg_price) / max(avg_price, 0.01)
    if usdc_size < CFG.signal_min_size:
        return "SKIP"
    if drift >= CFG.signal_late_max:
        return "SKIP"
    if drift >= CFG.signal_late_min or avg_price >= CFG.signal_late_entry:
        return "LATE"
    return "ENTER"

# ── Step 5: Enrich + qualify + score ────────────────────────
def enrich_and_score(leaderboard, resolved_lookup, active_markets):
    print(f"\nEnriching and qualifying {len(leaderboard)} wallets...")

    mkt_created = {}
    mkt_current_price = {}
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

    now_utc     = datetime.now(timezone.utc)
    cutoff_14d  = now_utc - timedelta(days=CFG.active_days)
    cutoff_30d  = now_utc - timedelta(days=30)

    qualified = []
    skipped   = 0

    for entry in leaderboard:
        wallet   = (entry.get("proxyWallet") or entry.get("proxy_wallet")
                    or entry.get("address", ""))
        if not wallet:
            continue

        name      = entry.get("name") or entry.get("pseudonym") or ""
        pseudonym = entry.get("pseudonym", "")
        profit_lb = float(entry.get("profit") or entry.get("pnl") or 0)
        volume_lb = float(entry.get("volume") or 0)

        # ── Positions ────────────────────────────────────────
        positions = get(f"{DATA_API}/positions", params={
            "user": wallet, "limit": 500, "sizeThreshold": 0
        }) or []

        total_initial  = sum(float(p.get("initialValue") or 0) for p in positions)
        total_current  = sum(float(p.get("currentValue") or 0) for p in positions)
        cash_pnl       = sum(float(p.get("cashPnl") or 0) for p in positions)
        realized_pnl   = sum(float(p.get("realizedPnl") or 0) for p in positions)
        total_pnl      = cash_pnl or profit_lb

        roi = cash_pnl / total_initial if total_initial > 0 else None

        # Resolved position stats
        brier_scores  = []
        wins_all      = 0
        resolved_cnt  = 0
        wins_30d      = 0
        resolved_30d  = 0
        max_drawdown  = 0.0

        for p in positions:
            cid        = p.get("conditionId", "")
            avg_price  = float(p.get("avgPrice") or 0)
            pnl_pos    = float(p.get("cashPnl") or 0)
            end_date   = p.get("endDate") or p.get("end_date")

            if pnl_pos < 0:
                max_drawdown += abs(pnl_pos)

            if cid not in resolved_lookup or avg_price <= 0:
                continue

            resolution = resolved_lookup[cid]
            brier_scores.append(1 - (avg_price - resolution) ** 2)
            resolved_cnt += 1
            won = (resolution >= 0.5 and avg_price >= 0.5) or \
                  (resolution < 0.5 and avg_price < 0.5)
            if won:
                wins_all += 1

            t_end = parse_ts(end_date)
            if t_end and t_end >= cutoff_30d:
                resolved_30d += 1
                if won:
                    wins_30d += 1

        win_rate_all = wins_all / resolved_cnt if resolved_cnt > 0 else 0
        win_rate_30d = wins_30d / resolved_30d if resolved_30d > 0 else 0
        z            = z_score(wins_all, resolved_cnt)

        # ── Activity ─────────────────────────────────────────
        activity = get(f"{DATA_API}/activity", params={
            "user": wallet, "limit": 500,
            "type": "TRADE", "sortBy": "TIMESTAMP", "sortDirection": "DESC"
        }) or []

        # Last active timestamp
        last_active = None
        for a in activity:
            ts = parse_ts(a.get("timestamp"))
            if ts:
                last_active = ts
                break   # DESC order so first = most recent

        trade_count  = len(activity)
        market_ids   = set(a.get("conditionId", "") for a in activity)
        usdc_volume  = sum(float(a.get("usdcSize") or a.get("cashAmount") or 0)
                          for a in activity)
        if usdc_volume == 0:
            usdc_volume = volume_lb

        # ── Qualification filter ──────────────────────────────
        reasons = []
        if resolved_cnt < CFG.min_resolved_bets:
            reasons.append(f"resolved {resolved_cnt}<{CFG.min_resolved_bets}")
        if total_pnl < CFG.min_pnl:
            reasons.append(f"PnL {fmt(total_pnl)}<{fmt(CFG.min_pnl)}")
        if roi is not None and roi < CFG.min_roi:
            reasons.append(f"ROI {roi*100:.1f}%<{CFG.min_roi*100:.0f}%")
        skilled = (z >= CFG.min_z_score or
                   (win_rate_all >= CFG.min_winrate_alt and resolved_cnt >= CFG.min_n_alt))
        if not skilled:
            reasons.append(f"not skilled (z={z:.1f})")
        if last_active and last_active < cutoff_14d:
            reasons.append(f"inactive {(now_utc-last_active).days}d")
        if win_rate_30d < CFG.min_winrate_30d:
            reasons.append(f"30d WR {win_rate_30d*100:.0f}%<{CFG.min_winrate_30d*100:.0f}%")
        if total_pnl > 0 and max_drawdown > CFG.max_drawdown_ratio * total_pnl:
            reasons.append(f"drawdown {max_drawdown/total_pnl*100:.0f}%>50%")

        if reasons:
            skipped += 1
            continue

        # ── Early entry ───────────────────────────────────────
        mkt_first = defaultdict(list)
        for a in reversed(activity):   # ASC order
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

        # Top markets
        mkt_counts = defaultdict(int)
        for a in activity:
            title = a.get("title") or ""
            if title:
                mkt_counts[title] += 1
        top_markets = [m for m, _ in sorted(mkt_counts.items(),
                       key=lambda x: x[1], reverse=True)][:3]

        # ── Signals on open positions ─────────────────────────
        signals = []
        for p in positions:
            cid       = p.get("conditionId", "")
            avg_price = float(p.get("avgPrice") or 0)
            cur_price = mkt_current_price.get(cid)
            usdc_size = float(p.get("currentValue") or 0)
            title     = p.get("title") or p.get("slug", "")
            label     = signal_label(avg_price, cur_price, usdc_size)
            if label == "DROP":
                continue
            signals.append({
                "market":     title,
                "signal":     label,
                "avg_price":  round(avg_price, 4),
                "cur_price":  round(cur_price, 4) if cur_price else None,
                "usdc_size":  round(usdc_size, 2),
                "outcome":    p.get("outcome", ""),
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
            early_score = clamp(
                (1 - sum(entry_hours) / len(entry_hours) / (CFG.early_days * 24)) * 100
            )
        else:
            early_score = 50.0

        final_score = (
            roi_score         * CFG.w_roi         +
            calib_score       * CFG.w_calibration  +
            consistency_score * CFG.w_consistency  +
            early_score       * CFG.w_early_entry  +
            volume_score      * CFG.w_volume
        )

        qualified.append({
            "wallet":             wallet,
            "name":               name,
            "pseudonym":          pseudonym,
            "score":              round(final_score, 1),
            "roi_score":          round(roi_score, 1),
            "calibration_score":  round(calib_score, 1),
            "consistency_score":  round(consistency_score, 1),
            "early_entry_score":  round(early_score, 1),
            "volume_score":       round(volume_score, 1),
            "roi":                round(roi * 100, 1) if roi is not None else None,
            "total_pnl":          round(total_pnl, 2),
            "realized_pnl":       round(realized_pnl, 2),
            "cash_pnl":           round(cash_pnl, 2),
            "total_usdc":         round(usdc_volume, 2),
            "trade_count":        trade_count,
            "market_count":       len(market_ids),
            "position_count":     len(positions),
            "resolved_count":     resolved_cnt,
            "win_rate":           round(win_rate_all * 100, 1),
            "win_rate_30d":       round(win_rate_30d * 100, 1),
            "z_score":            round(z, 2),
            "last_active":        last_active.isoformat() if last_active else None,
            "top_markets":        top_markets,
            "signals":            signals,
        })

        roi_str = f"{roi*100:+.1f}%" if roi is not None else "n/a"
        label   = name or wallet[:10] + "..."
        print(f"  ✓ {label:<22} Score:{round(final_score,1):<6} WR:{win_rate_all*100:.0f}% ROI:{roi_str}")

    print(f"\n  Qualified: {len(qualified)} | Skipped: {skipped}")
    qualified.sort(key=lambda x: x["score"], reverse=True)
    return qualified[:CFG.max_wallets_output]

# ── Step 6: Write output files ───────────────────────────────
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

    # Consensus markets: >= 2 whales on same side, no dissent
    consensus = []
    mkt_signals = defaultdict(lambda: defaultdict(list))
    for w in ranked:
        for sig in w.get("signals", []):
            if sig["signal"] == "ENTER":
                mkt_signals[sig["market"]][sig["outcome"]].append({
                    "wallet": w["wallet"],
                    "score":  w["score"],
                    "avg_price": sig["avg_price"],
                    "usdc_size": sig["usdc_size"],
                })
    for market, sides in mkt_signals.items():
        if len(sides) == 1:   # no dissent
            side, wallets = list(sides.items())[0]
            if len(wallets) >= 2:
                consensus.append({
                    "market":    market,
                    "side":      side,
                    "whales":    len(wallets),
                    "avg_entry": round(sum(w["avg_price"] for w in wallets) / len(wallets), 4),
                    "capital":   round(sum(w["usdc_size"] for w in wallets), 2),
                    "wallets":   [w["wallet"] for w in wallets],
                })
    consensus.sort(key=lambda x: x["whales"], reverse=True)

    with open(CFG.output_file, "w") as f:
        json.dump({
            "last_updated": now,
            "whale_count":  len(ranked),
            "market_count": len(market_list),
            "whales":       ranked,
            "markets":      market_list,
            "consensus":    consensus,
        }, f, indent=2)

    with open(CFG.markets_file, "w") as f:
        json.dump({"last_updated": now, "markets": market_list}, f, indent=2)

    with open(CFG.meta_file, "w") as f:
        json.dump({
            "last_updated":      now,
            "whale_count":       len(ranked),
            "market_count":      len(market_list),
            "consensus_count":   len(consensus),
            "leaderboard_window": CFG.leaderboard_window,
        }, f, indent=2)

    for path in [CFG.output_file, CFG.markets_file, CFG.meta_file]:
        kb = os.path.getsize(path) / 1024
        print(f"  ✓ {path}  ({kb:.1f} KB)")

# ── Main ─────────────────────────────────────────────────────
def main():
    print("=" * 55)
    print("  Polymarket Whale Tracker")
    print("=" * 55)

    leaderboard     = fetch_leaderboard()
    active_markets  = fetch_markets()
    resolved_lookup = fetch_resolved_lookup()

    if not leaderboard:
        print("No leaderboard data. Writing empty output.")
        write_output([], active_markets)
        return

    ranked = enrich_and_score(leaderboard, resolved_lookup, active_markets)
    print(f"\nWriting output files...")
    write_output(ranked, active_markets)

    if ranked:
        print(f"\n── Top 5 Whales ──────────────────────────────────────")
        for i, w in enumerate(ranked[:5], 1):
            label   = w["name"] or w["pseudonym"] or w["wallet"][:10] + "..."
            roi_str = f"{w['roi']:+.1f}%" if w["roi"] is not None else "n/a"
            sigs    = sum(1 for s in w["signals"] if s["signal"] == "ENTER")
            print(f"  {i}. {label:<22} Score:{w['score']:<6} WR:{w['win_rate']}% ROI:{roi_str} ENTER signals:{sigs}")

    print("\n✓ Done")

if __name__ == "__main__":
    main()
