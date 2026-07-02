# ============================================================
# Polymarket Whale Tracker — Simple Consensus Model
# ============================================================
# Strategy:
#   1. Pull top 50 accounts from leaderboard (by PNL, MONTH)
#   2. For each account, fetch their top 5 open positions
#   3. Find which bets appear most across accounts
#   4. Write data/whales.json with consensus bets + account list
# ============================================================
# Dependencies: requests
# No API key required
# ============================================================

import requests
import json
import time
import os
from datetime import datetime, timezone
from collections import defaultdict
from dataclasses import dataclass

# ── Config ───────────────────────────────────────────────────
@dataclass
class Config:
    leaderboard_limit:  int   = 50      # top accounts to pull
    top_positions:      int   = 5       # open positions per account
    sleep:              float = 0.25
    timeout:            int   = 15
    output_dir:         str   = "data"
    output_file:        str   = "data/whales.json"
    meta_file:          str   = "data/last_updated.json"

CFG = Config()

DATA_API  = "https://data-api.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"

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

# ── Step 1: Leaderboard ──────────────────────────────────────
def fetch_leaderboard():
    print(f"Fetching top {CFG.leaderboard_limit} accounts from leaderboard...")

    # Try multiple sort options in case one fails
    for sort in ["PNL", "VOLUME", "PROFIT"]:
        data = get(f"{DATA_API}/leaderboard", params={
            "limit":      CFG.leaderboard_limit,
            "sortBy":     sort,
        })
        if data:
            entries = data if isinstance(data, list) else data.get("data", [])
            if entries:
                print(f"  Found {len(entries)} accounts (sortBy={sort})")
                return entries

    # Fallback: try without sort params
    data = get(f"{DATA_API}/leaderboard", params={"limit": CFG.leaderboard_limit})
    if data:
        entries = data if isinstance(data, list) else data.get("data", [])
        print(f"  Found {len(entries)} accounts (no sort)")
        return entries

    print("  No leaderboard data found")
    return []

# ── Step 2: Open positions per account ───────────────────────
def fetch_open_positions(wallet):
    """Fetch top 5 open (non-resolved) positions for a wallet."""
    positions = get(f"{DATA_API}/positions", params={
        "user":          wallet,
        "limit":         50,
        "sizeThreshold": 10,    # ignore dust positions
        "sortBy":        "CURRENT_VALUE",
    }) or []

    # Filter to open positions only (currentValue > 0, not resolved)
    open_pos = []
    for p in positions:
        current_val = float(p.get("currentValue") or 0)
        redeemable  = float(p.get("redeemable") or 0)
        if current_val > 0 and redeemable == 0:
            open_pos.append(p)
        if len(open_pos) >= CFG.top_positions:
            break

    return open_pos

# ── Step 3: Build consensus ───────────────────────────────────
def build_consensus(accounts, positions_by_wallet):
    """
    Group positions by market + outcome.
    Count how many whales hold the same bet.
    """
    # Key: (conditionId, outcome) → list of whale data
    bet_groups = defaultdict(list)

    for wallet, positions in positions_by_wallet.items():
        acct = accounts.get(wallet, {})
        for p in positions:
            cid     = p.get("conditionId", "")
            outcome = p.get("outcome", "YES")
            title   = p.get("title") or p.get("market", "Unknown")
            if not cid:
                continue

            key = (cid, outcome)
            bet_groups[key].append({
                "wallet":       wallet,
                "name":         acct.get("name", ""),
                "avg_price":    round(float(p.get("avgPrice") or 0), 4),
                "current_val":  round(float(p.get("currentValue") or 0), 2),
                "size":         round(float(p.get("size") or 0), 2),
                "pnl":          round(float(p.get("cashPnl") or 0), 2),
                "title":        title,
                "outcome":      outcome,
                "cid":          cid,
            })

    # Build sorted consensus list
    consensus = []
    for (cid, outcome), holders in bet_groups.items():
        if len(holders) < 2:  # only show bets held by 2+ whales
            continue

        title       = holders[0]["title"]
        avg_price   = sum(h["avg_price"] for h in holders) / len(holders)
        total_cap   = sum(h["current_val"] for h in holders)
        avg_pnl     = sum(h["pnl"] for h in holders) / len(holders)
        payoff_pct  = round((1 / avg_price - 1) * 100, 1) if avg_price > 0 else None

        consensus.append({
            "market":       title,
            "outcome":      outcome,
            "cid":          cid,
            "whale_count":  len(holders),
            "avg_price":    round(avg_price, 4),
            "total_capital": round(total_cap, 2),
            "avg_pnl":      round(avg_pnl, 2),
            "payoff_pct":   payoff_pct,
            "whales":       [{
                "wallet":    h["wallet"],
                "name":      h["name"],
                "avg_price": h["avg_price"],
                "size":      h["current_val"],
            } for h in holders],
        })

    consensus.sort(key=lambda x: x["whale_count"], reverse=True)
    return consensus

# ── Step 4: Write output ──────────────────────────────────────
def write_output(accounts_list, consensus, positions_by_wallet):
    os.makedirs(CFG.output_dir, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    # Build account summary list
    account_summary = []
    for acct in accounts_list:
        wallet = (acct.get("proxyWallet") or acct.get("proxy_wallet")
                  or acct.get("address", ""))
        if not wallet:
            continue
        positions = positions_by_wallet.get(wallet, [])
        account_summary.append({
            "wallet":     wallet,
            "name":       acct.get("name") or acct.get("userName") or "",
            "pnl":        round(float(acct.get("pnl") or acct.get("profit") or 0), 2),
            "volume":     round(float(acct.get("volume") or acct.get("vol") or 0), 2),
            "positions":  [{
                "market":    p.get("title") or p.get("market", ""),
                "outcome":   p.get("outcome", ""),
                "avg_price": round(float(p.get("avgPrice") or 0), 4),
                "size":      round(float(p.get("currentValue") or 0), 2),
            } for p in positions]
        })

    with open(CFG.output_file, "w") as f:
        json.dump({
            "last_updated":   now,
            "account_count":  len(account_summary),
            "consensus_count": len(consensus),
            "consensus":      consensus,
            "accounts":       account_summary,
        }, f, indent=2)

    with open(CFG.meta_file, "w") as f:
        json.dump({
            "last_updated":    now,
            "account_count":   len(account_summary),
            "consensus_count": len(consensus),
        }, f, indent=2)

    for path in [CFG.output_file, CFG.meta_file]:
        kb = os.path.getsize(path) / 1024
        print(f"  ✓ {path}  ({kb:.1f} KB)")

# ── Main ─────────────────────────────────────────────────────
def main():
    print("=" * 55)
    print("  Polymarket Whale Tracker — Consensus Model")
    print("=" * 55)

    # Step 1: Leaderboard
    leaderboard = fetch_leaderboard()
    if not leaderboard:
        print("No leaderboard data. Exiting.")
        os.makedirs(CFG.output_dir, exist_ok=True)
        with open(CFG.output_file, "w") as f:
            json.dump({"last_updated": datetime.now(timezone.utc).isoformat(),
                       "consensus": [], "accounts": []}, f)
        return

    # Step 2: Fetch open positions for each account
    print(f"\nFetching top {CFG.top_positions} open positions per account...")
    accounts      = {}   # wallet → leaderboard entry
    positions_by_wallet = {}

    for entry in leaderboard:
        wallet = (entry.get("proxyWallet") or entry.get("proxy_wallet")
                  or entry.get("address", ""))
        if not wallet:
            continue

        name = entry.get("name") or entry.get("userName") or wallet[:10] + "..."
        accounts[wallet] = entry

        positions = fetch_open_positions(wallet)
        positions_by_wallet[wallet] = positions

        pos_str = ", ".join(
            f"{p.get('outcome','?')} {(p.get('title') or '')[:30]}"
            for p in positions
        ) or "no open positions"
        print(f"  ✓ {name:<22} {len(positions)} positions: {pos_str[:60]}")

    # Step 3: Build consensus
    print(f"\nBuilding consensus across {len(accounts)} accounts...")
    consensus = build_consensus(accounts, positions_by_wallet)
    print(f"  Found {len(consensus)} shared bets (held by 2+ whales)")

    # Step 4: Write output
    print(f"\nWriting output...")
    write_output(leaderboard, consensus, positions_by_wallet)

    # Summary
    if consensus:
        print(f"\n── Top 5 Consensus Bets ──────────────────────────────")
        for i, c in enumerate(consensus[:5], 1):
            print(f"  {i}. [{c['outcome']}] {c['market'][:50]}")
            print(f"     {c['whale_count']} whales · avg price {c['avg_price']} · "
                  f"capital ${c['total_capital']:,.0f} · "
                  f"payoff +{c['payoff_pct']}%")
    else:
        print("\n  No shared bets found across top accounts.")

    print("\n✓ Done")

if __name__ == "__main__":
    main()
