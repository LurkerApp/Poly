# ============================================================
# Expected Move Calculator — SPY & QQQ
# ============================================================
# Calculates ATM straddle expected move for next 5 expirations
# Also adds VIX, 20-day Historical Volatility, IV vs HV spread
# Writes results to data/expected_move.json
# ============================================================
# Dependencies: yfinance pandas numpy
# ============================================================

import yfinance as yf
import json
import os
import numpy as np
from datetime import datetime, timezone

# ── Config ───────────────────────────────────────────────────
SYMBOLS     = ["SPY", "QQQ"]
NUM_DAYS    = 5
OUTPUT_DIR  = "data"
OUTPUT_FILE = "data/expected_move.json"
HV_WINDOW   = 20    # days for historical volatility calculation
HV_LOOKBACK = 30    # days of price history to fetch

# ── Historical Volatility ─────────────────────────────────────
def get_historical_volatility(symbol, window=20, lookback=30):
    """
    Calculate annualized historical volatility (HV) using
    log returns over the last `window` trading days.
    """
    try:
        ticker = yf.Ticker(symbol)
        hist   = ticker.history(period=f"{lookback}d")["Close"]
        if len(hist) < window + 1:
            return None
        log_returns = np.log(hist / hist.shift(1)).dropna()
        hv          = log_returns.rolling(window).std().iloc[-1] * np.sqrt(252) * 100
        return round(float(hv), 2)
    except Exception as e:
        print(f"  ⚠ HV calc error for {symbol}: {e}")
        return None

# ── VIX ───────────────────────────────────────────────────────
def get_vix():
    try:
        vix   = yf.Ticker("^VIX")
        price = vix.history(period="1d")["Close"].iloc[-1]
        return round(float(price), 2)
    except Exception as e:
        print(f"  ⚠ VIX fetch error: {e}")
        return None

# ── Put/Call Ratio ────────────────────────────────────────────
def get_put_call_ratio(ticker_obj, expirations):
    """
    Calculate put/call ratio from open interest across
    the first available expiration.
    """
    try:
        chain       = ticker_obj.option_chain(expirations[0])
        call_oi     = chain.calls["openInterest"].sum()
        put_oi      = chain.puts["openInterest"].sum()
        if call_oi == 0:
            return None
        return round(float(put_oi / call_oi), 2)
    except Exception as e:
        print(f"  ⚠ Put/Call ratio error: {e}")
        return None

# ── Implied Volatility (annualized from straddle) ─────────────
def straddle_to_iv(straddle_price, current_price, days_to_expiry):
    """
    Approximate IV from ATM straddle price using the
    simplified formula: IV ≈ straddle / (S * sqrt(T))
    where T = days/365
    """
    try:
        if days_to_expiry <= 0:
            return None
        t  = days_to_expiry / 365.0
        iv = (straddle_price / current_price) / np.sqrt(t) * 100
        return round(float(iv), 2)
    except Exception:
        return None

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

        # Days to expiry for IV calc
        try:
            exp_date      = datetime.strptime(exp, "%Y-%m-%d")
            days_to_expiry = max((exp_date - datetime.now()).days, 1)
        except Exception:
            days_to_expiry = 30

        iv = straddle_to_iv(expected_move, float(current_price), days_to_expiry)

        moves.append({
            "expiration":        exp,
            "days_to_expiry":    days_to_expiry,
            "current_price":     round(float(current_price), 2),
            "atm_strike":        float(atm_call["strike"].iloc[0]),
            "call_price":        round(call_price, 2),
            "put_price":         round(put_price, 2),
            "expected_move":     round(expected_move, 2),
            "expected_move_pct": round(move_pct, 2),
            "upper_target":      round(float(current_price) + expected_move, 2),
            "lower_target":      round(float(current_price) - expected_move, 2),
            "iv_pct":            iv,
        })

    # Extra metrics
    hv         = get_historical_volatility(symbol, HV_WINDOW, HV_LOOKBACK)
    pc_ratio   = get_put_call_ratio(ticker, expirations)

    # IV vs HV spread using nearest expiry IV
    iv_hv_spread = None
    if moves[0].get("iv_pct") and hv:
        iv_hv_spread = round(moves[0]["iv_pct"] - hv, 2)

    return float(current_price), moves, hv, pc_ratio, iv_hv_spread

# ── Write JSON ────────────────────────────────────────────────
def write_output(results, vix):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    now    = datetime.now(timezone.utc).isoformat()
    output = {
        "last_updated": now,
        "vix":          vix,
        "symbols":      results
    }
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)
    kb = os.path.getsize(OUTPUT_FILE) / 1024
    print(f"\n✓ Written to {OUTPUT_FILE} ({kb:.1f} KB)")

# ── Print results ─────────────────────────────────────────────
def print_results(symbol, current_price, moves, hv, pc_ratio, iv_hv_spread):
    print(f"\n{'='*60}")
    print(f"  {symbol}  —  Current Price: ${current_price:.2f}")
    print(f"  HV (20d): {hv}%  |  Put/Call: {pc_ratio}  |  IV-HV Spread: {iv_hv_spread}%")
    print(f"{'='*60}")
    print(f"  {'Expiration':<14} {'DTE':<6} {'±Move':<10} {'%':<8} {'IV%':<8} {'Range'}")
    print(f"  {'-'*60}")
    for m in moves:
        print(
            f"  {m['expiration']:<14} "
            f"{m['days_to_expiry']:<6} "
            f"${m['expected_move']:<9} "
            f"{m['expected_move_pct']:.2f}%   "
            f"{str(m['iv_pct']) + '%':<8} "
            f"${m['lower_target']} – ${m['upper_target']}"
        )

# ── Main ─────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"Expected Move Calculator")
    print(f"Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Fetch VIX once
    print("\nFetching VIX...")
    vix = get_vix()
    print(f"  VIX: {vix}")

    results = []
    for symbol in SYMBOLS:
        try:
            current_price, moves, hv, pc_ratio, iv_hv_spread = get_implied_moves(symbol, NUM_DAYS)
            print_results(symbol, current_price, moves, hv, pc_ratio, iv_hv_spread)
            results.append({
                "symbol":        symbol,
                "current_price": current_price,
                "hv_20d":        hv,
                "put_call_ratio": pc_ratio,
                "iv_hv_spread":  iv_hv_spread,
                "moves":         moves,
            })
        except Exception as e:
            print(f"\n❌ Error fetching {symbol}: {e}")

    if results:
        write_output(results, vix)
