# ============================================================
# Expected Move Calculator — SPY & QQQ
# ============================================================
# Writes results to data/expected_move.json
# Served statically via GitHub Pages — no database needed
# ============================================================
# Dependencies: yfinance pandas
# ============================================================

import yfinance as yf
import json
import os
from datetime import datetime, timezone

# ── Config ───────────────────────────────────────────────────
SYMBOLS    = ["SPY", "QQQ"]
NUM_DAYS   = 5
OUTPUT_DIR = "data"
OUTPUT_FILE = "data/expected_move.json"

# ── Core function ─────────────────────────────────────────────
def get_implied_moves(symbol, num_days=5):
    ticker        = yf.Ticker(symbol)
    expirations   = ticker.options[:num_days]
    current_price = ticker.history(period="1d")["Close"].iloc[-1]
    moves         = []

    for exp in expirations:
        opt_chain = ticker.option_chain(exp)
        calls     = opt_chain.calls
        puts      = opt_chain.puts

        atm_call = calls.iloc[(calls["strike"] - current_price).abs().argsort()[:1]]
        atm_put  = puts.iloc[(puts["strike"]  - current_price).abs().argsort()[:1]]

        call_price    = float(atm_call["lastPrice"].iloc[0])
        put_price     = float(atm_put["lastPrice"].iloc[0])
        expected_move = call_price + put_price
        move_pct      = expected_move / current_price * 100

        moves.append({
            "expiration":        exp,
            "current_price":     round(float(current_price), 2),
            "atm_strike":        float(atm_call["strike"].iloc[0]),
            "call_price":        round(call_price, 2),
            "put_price":         round(put_price, 2),
            "expected_move":     round(expected_move, 2),
            "expected_move_pct": round(move_pct, 2),
            "upper_target":      round(float(current_price) + expected_move, 2),
            "lower_target":      round(float(current_price) - expected_move, 2),
        })

    return float(current_price), moves

# ── Write JSON ────────────────────────────────────────────────
def write_output(results):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    output = {
        "last_updated": now,
        "symbols": results
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    kb = os.path.getsize(OUTPUT_FILE) / 1024
    print(f"\n✓ Written to {OUTPUT_FILE} ({kb:.1f} KB)")

# ── Print results ─────────────────────────────────────────────
def print_results(symbol, current_price, moves):
    print(f"\n{'='*60}")
    print(f"  {symbol}  —  Current Price: ${current_price:.2f}")
    print(f"{'='*60}")
    print(f"  {'Expiration':<14} {'±Move':<10} {'%':<8} {'Range'}")
    print(f"  {'-'*50}")
    for m in moves:
        print(
            f"  {m['expiration']:<14} "
            f"${m['expected_move']:<9} "
            f"{m['expected_move_pct']:.2f}%   "
            f"${m['lower_target']} – ${m['upper_target']}"
        )

# ── Main ─────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"Expected Move Calculator")
    print(f"Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    results = []

    for symbol in SYMBOLS:
        try:
            current_price, moves = get_implied_moves(symbol, NUM_DAYS)
            print_results(symbol, current_price, moves)
            results.append({
                "symbol":        symbol,
                "current_price": current_price,
                "moves":         moves
            })
        except Exception as e:
            print(f"\n❌ Error fetching {symbol}: {e}")

    if results:
        write_output(results)
