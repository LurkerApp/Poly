# ============================================================
# Expected Move Calculator — SPY & QQQ
# ============================================================
# Calculates ATM straddle expected move for next 5 expirations
# Adds VIX, 20-day HV, IV vs HV spread, Put/Call per expiry
# Full OI profile (±5% range, min 100 OI) for volume profile
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
SYMBOLS      = ["SPY", "QQQ"]
NUM_DAYS     = 5
OUTPUT_DIR   = "data"
OUTPUT_FILE  = "data/expected_move.json"
HV_WINDOW    = 20
HV_LOOKBACK  = 30
TOP_OI       = 5
OI_RANGE_PCT = 0.05    # ±5% of current price
MIN_OI       = 100     # ignore strikes with OI below this

# ── Historical Volatility ─────────────────────────────────────
def get_historical_volatility(symbol, window=20, lookback=30):
    try:
        ticker      = yf.Ticker(symbol)
        hist        = ticker.history(period=f"{lookback}d")["Close"]
        if len(hist) < window + 1:
            return None
        log_returns = np.log(hist / hist.shift(1)).dropna()
        hv          = log_returns.rolling(window).std().iloc[-1] * np.sqrt(252) * 100
        return round(float(hv), 2)
    except Exception as e:
        print(f"  ⚠ HV error for {symbol}: {e}")
        return None

# ── VIX ───────────────────────────────────────────────────────
def get_vix():
    try:
        vix   = yf.Ticker("^VIX")
        price = vix.history(period="1d")["Close"].iloc[-1]
        return round(float(price), 2)
    except Exception as e:
        print(f"  ⚠ VIX error: {e}")
        return None

# ── Put/Call ratio per expiration ─────────────────────────────
def get_put_call_per_expiry(ticker_obj, expirations):
    ratios = []
    for exp in expirations:
        try:
            chain   = ticker_obj.option_chain(exp)
            call_oi = chain.calls["openInterest"].sum()
            put_oi  = chain.puts["openInterest"].sum()
            ratio   = round(float(put_oi / call_oi), 2) if call_oi > 0 else None
            ratios.append(ratio)
        except Exception:
            ratios.append(None)
    return ratios

# ── IV approximation from straddle ───────────────────────────
def straddle_to_iv(straddle_price, current_price, days_to_expiry):
    try:
        if days_to_expiry <= 0:
            return None
        t  = days_to_expiry / 365.0
        iv = (straddle_price / current_price) / np.sqrt(t) * 100
        return round(float(iv), 2)
    except Exception:
        return None

# ── OI Profile + Max Pain ─────────────────────────────────────
def get_oi_analysis(ticker_obj, expiration, current_price):
    try:
        chain = ticker_obj.option_chain(expiration)
        calls = chain.calls[["strike", "openInterest", "volume"]].copy()
        puts  = chain.puts[["strike",  "openInterest", "volume"]].copy()

        # Fill NaN
        calls["openInterest"] = calls["openInterest"].fillna(0)
        puts["openInterest"]  = puts["openInterest"].fillna(0)
        calls["volume"]       = calls["volume"].fillna(0)
        puts["volume"]        = puts["volume"].fillna(0)

        # ── Filter: ±5% of current price + min OI ────────────
        lo = current_price * (1 - OI_RANGE_PCT)
        hi = current_price * (1 + OI_RANGE_PCT)

        calls_f = calls[
            (calls["strike"] >= lo) &
            (calls["strike"] <= hi) &
            (calls["openInterest"] >= MIN_OI)
        ]
        puts_f = puts[
            (puts["strike"] >= lo) &
            (puts["strike"] <= hi) &
            (puts["openInterest"] >= MIN_OI)
        ]

        print(f"    OI profile: {len(calls_f)} call strikes, {len(puts_f)} put strikes (±5%, min OI {MIN_OI})")

        # ── Build merged profile per strike ───────────────────
        # Combine calls and puts at each strike into one entry
        all_strikes = sorted(set(
            calls_f["strike"].tolist() + puts_f["strike"].tolist()
        ))

        profile = []
        for s in all_strikes:
            c_row    = calls_f[calls_f["strike"] == s]
            p_row    = puts_f[puts_f["strike"] == s]
            call_oi  = int(c_row["openInterest"].iloc[0]) if len(c_row) > 0 else 0
            put_oi   = int(p_row["openInterest"].iloc[0]) if len(p_row) > 0 else 0
            call_vol = int(c_row["volume"].iloc[0]) if len(c_row) > 0 else 0
            put_vol  = int(p_row["volume"].iloc[0]) if len(p_row) > 0 else 0
            profile.append({
                "strike":        round(float(s), 2),
                "call_oi":       call_oi,
                "put_oi":        put_oi,
                "total_oi":      call_oi + put_oi,
                "call_volume":   call_vol,
                "put_volume":    put_vol,
            })

        # Max OI for scaling the profile bars
        max_oi = max((p["total_oi"] for p in profile), default=1)

        # Top 3 call and put strikes by OI (for labels)
        top_calls = sorted(profile, key=lambda x: x["call_oi"], reverse=True)[:3]
        top_puts  = sorted(profile, key=lambda x: x["put_oi"],  reverse=True)[:3]

        # ── Max pain (use all strikes, not filtered) ──────────
        all_strikes_full = sorted(set(
            calls["strike"].tolist() + puts["strike"].tolist()
        ))
        min_pain = None
        min_loss = float("inf")
        for s in all_strikes_full:
            itm_calls  = calls[calls["strike"] < s]
            call_loss  = float((itm_calls["openInterest"] * (s - itm_calls["strike"])).sum())
            itm_puts   = puts[puts["strike"] > s]
            put_loss   = float((itm_puts["openInterest"] * (itm_puts["strike"] - s)).sum())
            total_loss = call_loss + put_loss
            if total_loss < min_loss:
                min_loss = total_loss
                min_pain = s

        print(f"    Max Pain: ${min_pain}")
        print(f"    Profile size: {len(profile)} strikes, max OI: {max_oi:,}")

        return {
            "max_pain":      round(float(min_pain), 2) if min_pain is not None else None,
            "max_pain_diff": round(float(min_pain - current_price), 2) if min_pain is not None else None,
            "max_oi":        int(max_oi),
            "profile":       profile,   # merged call+put OI per strike
            "top_calls":     top_calls,
            "top_puts":      top_puts,
        }

    except Exception as e:
        print(f"  ⚠ OI analysis error: {e}")
        return None

# ── Core function ─────────────────────────────────────────────
def get_implied_moves(symbol, num_days=5):
    ticker        = yf.Ticker(symbol)
    expirations   = ticker.options[:num_days]
    current_price = ticker.history(period="1d")["Close"].iloc[-1]

    print(f"  Fetching put/call ratios per expiration...")
    pc_per_expiry = get_put_call_per_expiry(ticker, expirations)

    print(f"  Fetching OI profile for nearest expiry ({expirations[0]})...")
    oi_analysis = get_oi_analysis(ticker, expirations[0], float(current_price))

    moves = []
    for i, exp in enumerate(expirations):
        opt_chain = ticker.option_chain(exp)
        calls     = opt_chain.calls
        puts      = opt_chain.puts

        atm_call = calls.iloc[(calls["strike"] - current_price).abs().argsort()[:1]]
        atm_put  = puts.iloc[(puts["strike"]  - current_price).abs().argsort()[:1]]

        call_price    = float(atm_call["lastPrice"].iloc[0])
        put_price     = float(atm_put["lastPrice"].iloc[0])
        expected_move = call_price + put_price
        move_pct      = expected_move / current_price * 100

        try:
            exp_date       = datetime.strptime(exp, "%Y-%m-%d")
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
            "put_call_ratio":    pc_per_expiry[i],
        })

    hv           = get_historical_volatility(symbol, HV_WINDOW, HV_LOOKBACK)
    pc_ratio     = pc_per_expiry[0] if pc_per_expiry else None
    iv_hv_spread = None
    if moves[0].get("iv_pct") and hv:
        iv_hv_spread = round(moves[0]["iv_pct"] - hv, 2)

    return float(current_price), moves, hv, pc_ratio, iv_hv_spread, oi_analysis

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
def print_results(symbol, current_price, moves, hv, pc_ratio, iv_hv_spread, oi):
    print(f"\n{'='*60}")
    print(f"  {symbol}  —  Current Price: ${current_price:.2f}")
    print(f"  HV (20d): {hv}%  |  P/C: {pc_ratio}  |  IV-HV: {iv_hv_spread}%")
    if oi:
        print(f"  Max Pain    : ${oi['max_pain']} ({'+' if oi['max_pain_diff'] >= 0 else ''}{oi['max_pain_diff']})")
        print(f"  OI Profile  : {len(oi['profile'])} strikes, max OI: {oi['max_oi']:,}")
        print(f"  Top call OI : {[(c['strike'], c['call_oi']) for c in oi['top_calls']]}")
        print(f"  Top put  OI : {[(p['strike'], p['put_oi'])  for p in oi['top_puts']]}")
    print(f"{'='*60}")
    print(f"  {'Expiration':<14} {'DTE':<6} {'±Move':<10} {'%':<8} {'P/C':<6} {'Range'}")
    print(f"  {'-'*65}")
    for m in moves:
        print(
            f"  {m['expiration']:<14} "
            f"{m['days_to_expiry']:<6} "
            f"${m['expected_move']:<9} "
            f"{m['expected_move_pct']:.2f}%   "
            f"{str(m['put_call_ratio']):<6} "
            f"${m['lower_target']} – ${m['upper_target']}"
        )

# ── Main ─────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"Expected Move Calculator")
    print(f"Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    print("\nFetching VIX...")
    vix = get_vix()
    print(f"  VIX: {vix}")

    results = []
    for symbol in SYMBOLS:
        try:
            current_price, moves, hv, pc_ratio, iv_hv_spread, oi_analysis = get_implied_moves(symbol, NUM_DAYS)
            print_results(symbol, current_price, moves, hv, pc_ratio, iv_hv_spread, oi_analysis)
            results.append({
                "symbol":         symbol,
                "current_price":  current_price,
                "hv_20d":         hv,
                "put_call_ratio": pc_ratio,
                "iv_hv_spread":   iv_hv_spread,
                "oi_analysis":    oi_analysis,
                "moves":          moves,
            })
        except Exception as e:
            print(f"\n❌ Error fetching {symbol}: {e}")

    if results:
        write_output(results, vix)
