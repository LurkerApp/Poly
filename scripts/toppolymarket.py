# ============================================================
# Polymarket Whale Tracker — Consensus Model
# ============================================================
# Strategy:
#   1. Pull top 50 accounts from leaderboard
#   2. Fetch ALL open positions per account
#   3. Group by market + outcome, count how many wallets hold each bet
#   4. Rank by wallet count, output top 5 consensus bets
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
    top_consensus:      int   = 5       # top N consensus bets to output
    min_position_size:  float = 10      # ignore dust positions < $10
    sleep:              float = 0.25
    timeout:            int   = 15
    output_dir:         str   = "data"
    output_file:        str   = "data/whales.json"
    meta_file:          str   = "data/last_updated.json"

CFG = Config()

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

# ── Step 1: Leaderboard ──────────────────────────────────────
def fetch_leaderboard():
    print(f"Fetching top {CFG.leaderboard_limit} accounts from leaderboard...")
    for sort in ["PNL", "VOLUME", "PROFIT"]:
        data = get(f"{DATA_API}/leaderboard", params={
            "limit":  CFG.leaderboard_limit,
            "sortBy": sort,
        })
        if data:
            entries = data if isinstance(data, list) else data.get("data", [])
            if entries:
                print(f"  Found {len(entries)} accounts (sortBy={sort})")
                return entries

    data = get(f"{DATA_API}/leaderboard", params={"limit": CFG.leaderboard_limit})
    if data:
        entries = data if isinstance(data, list) else data.get("data", [])
        print(f"  Found {len(entries)} accounts")
        return entries

    print("  No leaderboard data found")
    return []

# ── Step 2: ALL open positions per account ───────────────────
def fetch_all_open_positions(wallet):
    """Fetch all open (non-resolved) positions for a wallet."""
    positions = get(f"{DATA_API}/positions", params={
        "user":          wallet,
        "limit":         500,
        "sizeThreshold": CFG.min_position_size,
    }) or []

    open_pos = []
    for p in positions:
        current_val = float(p.get("currentValue") or 0)
        redeemable  = float(p.get("redeemable") or 0)
        if current_val > CFG.min_position_size and redeemable == 0:
            open_pos.append(p)

    return open_pos

# ── Step 3: Build consensus — rank by wallet count ───────────
def build_consensus(accounts, positions_by_wallet):
    """
    Group ALL positions by market + outcome.
    Rank by number of wallets holding the same bet.
    Return top 5.
    """
    bet_groups = defaultdict(list)

    for wallet, positions in positions_by_wallet.items():
        acct = accounts.get(wallet, {})
        name = acct.get("name") or acct.get("userName") or ""

        for p in positions:
            cid     = p.get("conditionId", "")
            outcome = p.get("outcome", "YES")
            title   = p.get("title") or p.get("market", "Unknown")
            if not cid:
                continue

            bet_groups[(cid, outcome)].append({
                "wallet":      wallet,
                "name":        name,
                "avg_price":   round(float(p.get("avgPrice") or 0), 4),
                "current_val": round(float(p.get("currentValue") or 0), 2),
                "pnl":         round(float(p.get("cashPnl") or 0), 2),
                "title":       title,
                "outcome":     outcome,
                "cid":         cid,
            })

    # Build ranked list
    consensus = []
    for (cid, outcome), holders in bet_groups.items():
        if len(holders) < 2:
            continue

        title      = holders[0]["title"]
        avg_price  = sum(h["avg_price"] for h in holders) / len(holders)
        total_cap  = sum(h["current_val"] for h in holders)
        payoff_pct = round((1 / avg_price - 1) * 100, 1) if avg_price > 0 else None

        consensus.append({
            "market":        title,
            "outcome":       outcome,
            "cid":           cid,
            "whale_count":   len(holders),
            "avg_price":     round(avg_price, 4),
            "total_capital": round(total_cap, 2),
            "payoff_pct":    payoff_pct,
            "whales": [{
                "wallet":    h["wallet"],
                "name":      h["name"],
                "avg_price": h["avg_price"],
                "size":      h["current_val"],
                "pnl":       h["pnl"],
            } for h in holders],
        })

    # Sort by whale count desc, then total capital desc
    consensus.sort(key=lambda x: (x["whale_count"], x["total_capital"]), reverse=True)

    print(f"  Found {len(consensus)} shared bets across all accounts")
    return consensus[:CFG.top_consensus]

# ── Step 4: Write output ──────────────────────────────────────
def write_output(leaderboard, consensus, positions_by_wallet):
    os.makedirs(CFG.output_dir, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    account_summary = []
    for acct in leaderboard:
        wallet = (acct.get("proxyWallet") or acct.get("proxy_wallet")
                  or acct.get("address", ""))
        if not wallet:
            continue
        positions = positions_by_wallet.get(wallet, [])
        account_summary.append({
            "wallet":    wallet,
            "name":      acct.get("name") or acct.get("userName") or "",
            "pnl":       round(float(acct.get("pnl") or acct.get("profit") or 0), 2),
            "volume":    round(float(acct.get("volume") or acct.get("vol") or 0), 2),
            "positions": [{
                "market":    p.get("title") or p.get("market", ""),
                "outcome":   p.get("outcome", ""),
                "avg_price": round(float(p.get("avgPrice") or 0), 4),
                "size":      round(float(p.get("currentValue") or 0), 2),
                "pnl":       round(float(p.get("cashPnl") or 0), 2),
            } for p in positions]
        })

    with open(CFG.output_file, "w") as f:
        json.dump({
            "last_updated":    now,
            "account_count":   len(account_summary),
            "consensus_count": len(consensus),
            "consensus":       consensus,
            "accounts":        account_summary,
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

    leaderboard = fetch_leaderboard()
    if not leaderboard:
        print("No leaderboard data. Exiting.")
        os.makedirs(CFG.output_dir, exist_ok=True)
        with open(CFG.output_file, "w") as f:
            json.dump({"last_updated": datetime.now(timezone.utc).isoformat(),
                       "consensus": [], "accounts": []}, f)
        return

    # Fetch ALL open positions for every account
    print(f"\nFetching all open positions for {len(leaderboard)} accounts...")
    accounts            = {}
    positions_by_wallet = {}

    for entry in leaderboard:
        wallet = (entry.get("proxyWallet") or entry.get("proxy_wallet")
                  or entry.get("address", ""))
        if not wallet:
            continue

        name = entry.get("name") or entry.get("userName") or wallet[:10] + "..."
        accounts[wallet] = entry

        positions = fetch_all_open_positions(wallet)
        positions_by_wallet[wallet] = positions
        print(f"  ✓ {name:<22} {len(positions)} open positions")

    # Build consensus — rank by wallet count
    print(f"\nRanking shared bets by number of wallets...")
    consensus = build_consensus(accounts, positions_by_wallet)

    # Write output
    print(f"\nWriting output...")
    write_output(leaderboard, consensus, positions_by_wallet)

    if consensus:
        print(f"\n── Top {CFG.top_consensus} Consensus Bets ────────────────────────")
        for i, c in enumerate(consensus, 1):
            print(f"  {i}. [{c['outcome']}] {c['market'][:50]}")
            print(f"     {c['whale_count']} wallets · avg {c['avg_price']} · "
                  f"${c['total_capital']:,.0f} capital · payoff +{c['payoff_pct']}%")
    else:
        print("\n  No shared bets found.")

    print("\n✓ Done")

if __name__ == "__main__":
    main()
