#!/usr/bin/env python3
"""
options_poller.py — Deribit BTC Options Signals Poller

Fetches live options data from Deribit public API (no auth required).
Calculates P/C ratio, max pain, IV by expiry, OI clusters.
Outputs to state/options_signals.json.

CLI:
  python3 options_poller.py run     — fetch and save
  python3 options_poller.py status  — show last saved data
  python3 options_poller.py summary — one-line summary for daily brief
"""

import sys
import json
import os
import datetime
import urllib.request
import urllib.error
import time
import math
from collections import defaultdict

# ─── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
STATE_DIR = os.path.join(PROJECT_ROOT, "state")
OUTPUT_FILE = os.path.join(STATE_DIR, "options_signals.json")

BASE_URL = "https://www.deribit.com/api/v2/public"
REQUEST_TIMEOUT = 30


# ─── API helpers ──────────────────────────────────────────────────────────────

def api_get(endpoint: str, params: dict) -> dict | None:
    """Make a GET request to Deribit public API. Returns result dict or None on error."""
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{BASE_URL}/{endpoint}?{query}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "pinch-crypto-bot/1.0"})
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if "result" not in data:
                print(f"[WARN] No result in response for {endpoint}: {data.get('error', 'unknown')}")
                return None
            return data["result"]
    except urllib.error.URLError as e:
        print(f"[ERROR] API request failed ({endpoint}): {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"[ERROR] JSON decode failed ({endpoint}): {e}")
        return None
    except Exception as e:
        print(f"[ERROR] Unexpected error ({endpoint}): {e}")
        return None


# ─── Data fetchers ────────────────────────────────────────────────────────────

def fetch_btc_price() -> float | None:
    """Get BTC index price from Deribit."""
    result = api_get("get_index_price", {"index_name": "btc_usd"})
    if result is None:
        return None
    return float(result.get("index_price", 0))


def fetch_instruments() -> list:
    """Get all active BTC option instruments."""
    result = api_get("get_instruments", {
        "currency": "BTC",
        "kind": "option",
        "expired": "false"
    })
    if result is None:
        return []
    return result


def fetch_book_summaries() -> list:
    """Get book summaries for all BTC options (OI, volume, IV)."""
    result = api_get("get_book_summary_by_currency", {
        "currency": "BTC",
        "kind": "option"
    })
    if result is None:
        return []
    return result


# ─── Calculations ─────────────────────────────────────────────────────────────

def parse_expiry_from_instrument(name: str) -> str | None:
    """
    Parse expiry date from instrument name like BTC-28MAR26-70000-C.
    Returns YYYY-MM-DD or None.
    """
    parts = name.split("-")
    if len(parts) < 2:
        return None
    raw = parts[1]  # e.g. "28MAR26"
    month_map = {
        "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4,
        "MAY": 5, "JUN": 6, "JUL": 7, "AUG": 8,
        "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
    }
    try:
        day = int(raw[:2])
        mon_str = raw[2:5].upper()
        year = 2000 + int(raw[5:])
        month = month_map.get(mon_str)
        if month is None:
            return None
        return f"{year:04d}-{month:02d}-{day:02d}"
    except Exception:
        return None


def compute_put_call_ratios(summaries: list, instruments: dict) -> tuple[float, float]:
    """
    Compute OI-based and volume-based P/C ratios.
    instruments: dict of instrument_name -> {option_type: 'call'/'put', ...}
    Returns (pc_ratio_oi, pc_ratio_volume).
    """
    put_oi = 0.0
    call_oi = 0.0
    put_vol = 0.0
    call_vol = 0.0

    for s in summaries:
        name = s.get("instrument_name", "")
        oi = float(s.get("open_interest", 0) or 0)
        vol = float(s.get("volume", 0) or 0)

        # Determine type from instruments dict, fallback to name suffix
        instr = instruments.get(name)
        if instr:
            opt_type = instr.get("option_type", "").lower()
        else:
            # Fallback: last character of instrument name is C or P
            suffix = name.split("-")[-1].upper() if "-" in name else ""
            opt_type = "put" if suffix == "P" else "call"

        if opt_type == "put":
            put_oi += oi
            put_vol += vol
        else:
            call_oi += oi
            call_vol += vol

    pc_oi = put_oi / call_oi if call_oi > 0 else 0.0
    pc_vol = put_vol / call_vol if call_vol > 0 else 0.0
    return pc_oi, pc_vol


def compute_max_pain(summaries: list, instruments: dict, btc_price: float) -> float:
    """
    Find strike where total dollar pain (ITM intrinsic × OI) is minimized.
    This is the max pain point — price where most options expire worthless.
    """
    # Build per-strike OI by type
    strike_data = defaultdict(lambda: {"call_oi": 0.0, "put_oi": 0.0})
    for s in summaries:
        name = s.get("instrument_name", "")
        oi = float(s.get("open_interest", 0) or 0)
        instr = instruments.get(name)
        if instr:
            strike = float(instr.get("strike", 0))
            opt_type = instr.get("option_type", "").lower()
        else:
            # Parse from name: BTC-28MAR26-70000-C
            parts = name.split("-")
            if len(parts) < 4:
                continue
            try:
                strike = float(parts[2])
                opt_type = "put" if parts[3].upper() == "P" else "call"
            except (ValueError, IndexError):
                continue
        if strike <= 0:
            continue
        if opt_type == "put":
            strike_data[strike]["put_oi"] += oi
        else:
            strike_data[strike]["call_oi"] += oi

    if not strike_data:
        return btc_price

    all_strikes = sorted(strike_data.keys())
    min_pain = None
    max_pain_strike = btc_price

    for test_strike in all_strikes:
        total_pain = 0.0
        for s in all_strikes:
            coi = strike_data[s]["call_oi"]
            poi = strike_data[s]["put_oi"]
            # Call pain: calls ITM if strike < test_strike
            if s < test_strike:
                total_pain += coi * (test_strike - s)
            # Put pain: puts ITM if strike > test_strike
            if s > test_strike:
                total_pain += poi * (s - test_strike)

        if min_pain is None or total_pain < min_pain:
            min_pain = total_pain
            max_pain_strike = test_strike

    return max_pain_strike


def compute_iv_by_expiry(summaries: list) -> dict:
    """
    Group average mark_iv by expiry date.
    Returns dict: expiry_date_str -> avg_iv (as percentage, e.g. 55.2)
    """
    expiry_ivs = defaultdict(list)
    for s in summaries:
        iv = s.get("mark_iv")
        if iv is None:
            continue
        try:
            iv = float(iv)
        except (ValueError, TypeError):
            continue
        if iv <= 0:
            continue
        name = s.get("instrument_name", "")
        expiry = parse_expiry_from_instrument(name)
        if expiry:
            expiry_ivs[expiry].append(iv)

    result = {}
    for expiry, ivs in expiry_ivs.items():
        result[expiry] = sum(ivs) / len(ivs)
    return result


def compute_top_oi_strikes(summaries: list, instruments: dict, n: int = 5) -> list:
    """Get top N strikes by total open interest (calls + puts combined)."""
    strike_oi = defaultdict(float)
    for s in summaries:
        name = s.get("instrument_name", "")
        oi = float(s.get("open_interest", 0) or 0)
        instr = instruments.get(name)
        if instr:
            strike = float(instr.get("strike", 0))
        else:
            parts = name.split("-")
            if len(parts) < 4:
                continue
            try:
                strike = float(parts[2])
            except (ValueError, IndexError):
                continue
        if strike > 0:
            strike_oi[strike] += oi

    sorted_strikes = sorted(strike_oi.items(), key=lambda x: x[1], reverse=True)
    return [int(s) for s, _ in sorted_strikes[:n]]


def find_next_monthly_expiry(iv_by_expiry: dict) -> tuple[str, int]:
    """
    Find the next monthly expiry (last Friday of the month).
    Returns (expiry_date_str, days_to_expiry).
    Looks through available expiry dates and picks the next one >= today.
    """
    today = datetime.date.today()
    future_expiries = sorted([
        e for e in iv_by_expiry.keys()
        if e >= today.strftime("%Y-%m-%d")
    ])
    if not future_expiries:
        # Fallback: compute next end-of-month Friday
        next_month = today.replace(day=28) + datetime.timedelta(days=4)
        next_month = next_month.replace(day=1)
        # Last day of month
        last_day = (next_month.replace(month=next_month.month % 12 + 1, day=1)
                    - datetime.timedelta(days=1))
        # Find last Friday
        while last_day.weekday() != 4:
            last_day -= datetime.timedelta(days=1)
        expiry_str = last_day.strftime("%Y-%m-%d")
        days_to = (last_day - today).days
        return expiry_str, days_to

    # Find the next monthly expiry (prefer end-of-month dates)
    # Monthly options typically expire on last Friday of each month
    # Filter for dates that are near end-of-month (day >= 25)
    monthly = [e for e in future_expiries if int(e.split("-")[2]) >= 25]
    if monthly:
        expiry_str = monthly[0]
    else:
        expiry_str = future_expiries[0]

    expiry_date = datetime.date.fromisoformat(expiry_str)
    days_to = (expiry_date - today).days
    return expiry_str, days_to


def build_signal_summary(pc_oi: float, max_pain: float, btc_price: float, term_structure: str) -> str:
    """Generate human-readable signal summary."""
    pain_pct = (max_pain / btc_price - 1.0) * 100 if btc_price > 0 else 0.0
    pain_dir = "below" if pain_pct < 0 else "above"

    if pc_oi > 1.0:
        sentiment = "Bearish (extreme fear)"
    elif pc_oi > 0.75:
        sentiment = "Bearish"
    elif pc_oi > 0.55:
        sentiment = "Neutral"
    elif pc_oi > 0.35:
        sentiment = "Slightly Bullish"
    else:
        sentiment = "Bullish (euphoria)"

    return (
        f"{sentiment} — P/C {pc_oi:.2f}, max pain ${max_pain:,.0f} "
        f"({abs(pain_pct):.1f}% {pain_dir} spot), {term_structure}"
    )


# ─── Main runner ──────────────────────────────────────────────────────────────

def run_poll() -> dict | None:
    """Fetch all data and compute options signals. Returns result dict or None."""
    print("[*] Fetching BTC index price...")
    btc_price = fetch_btc_price()
    if btc_price is None or btc_price <= 0:
        print("[ERROR] Could not fetch BTC price. Aborting.")
        return None
    print(f"    BTC: ${btc_price:,.2f}")

    print("[*] Fetching instruments...")
    instr_list = fetch_instruments()
    # Small delay to be kind to API
    time.sleep(0.5)

    print(f"    Got {len(instr_list)} instruments")
    # Build lookup dict
    instruments = {}
    for instr in instr_list:
        name = instr.get("instrument_name", "")
        if name:
            instruments[name] = instr

    print("[*] Fetching book summaries...")
    summaries = fetch_book_summaries()
    print(f"    Got {len(summaries)} book summaries")

    if not summaries:
        print("[ERROR] No book summaries returned. Aborting.")
        return None

    # ── Calculations ──────────────────────────────────────────────────────────
    print("[*] Computing P/C ratios...")
    pc_oi, pc_vol = compute_put_call_ratios(summaries, instruments)

    print("[*] Computing max pain...")
    max_pain = compute_max_pain(summaries, instruments, btc_price)
    max_pain_pct = (max_pain / btc_price - 1.0) * 100 if btc_price > 0 else 0.0

    print("[*] Computing IV by expiry...")
    iv_by_expiry = compute_iv_by_expiry(summaries)

    print("[*] Finding top OI strikes...")
    top_oi_strikes = compute_top_oi_strikes(summaries, instruments, n=5)

    print("[*] Finding next monthly expiry...")
    next_expiry, days_to_expiry = find_next_monthly_expiry(iv_by_expiry)

    # Front month and next month IV
    sorted_expiries = sorted(iv_by_expiry.keys())
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    future_expiries_sorted = [e for e in sorted_expiries if e >= today_str]
    iv_front_month = iv_by_expiry.get(future_expiries_sorted[0], 0.0) if len(future_expiries_sorted) >= 1 else 0.0
    iv_next_month = iv_by_expiry.get(future_expiries_sorted[1], 0.0) if len(future_expiries_sorted) >= 2 else 0.0

    # Term structure
    if iv_front_month > 0 and iv_next_month > 0:
        term_structure = "backwardation" if iv_front_month > iv_next_month else "contango"
    else:
        term_structure = "unknown"

    signal_summary = build_signal_summary(pc_oi, max_pain, btc_price, term_structure)

    result = {
        "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
        "btc_price": round(btc_price, 2),
        "put_call_ratio_oi": round(pc_oi, 4),
        "put_call_ratio_volume": round(pc_vol, 4),
        "max_pain": int(round(max_pain, -2)),  # round to nearest 100
        "max_pain_distance_pct": round(max_pain_pct, 2),
        "next_expiry": next_expiry,
        "days_to_expiry": days_to_expiry,
        "top_oi_strikes": top_oi_strikes,
        "iv_front_month": round(iv_front_month, 2),
        "iv_next_month": round(iv_next_month, 2),
        "term_structure": term_structure,
        "signal_summary": signal_summary,
    }

    # Save to state file
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\n[✓] Saved to {OUTPUT_FILE}")
    print(f"    {signal_summary}")
    return result


def cmd_status():
    """Show last saved options signals data."""
    if not os.path.exists(OUTPUT_FILE):
        print("[!] No options signals data found. Run `python3 options_poller.py run` first.")
        return
    with open(OUTPUT_FILE) as f:
        data = json.load(f)
    print(json.dumps(data, indent=2))


def cmd_summary():
    """One-line summary for daily brief."""
    if not os.path.exists(OUTPUT_FILE):
        print("No options data. Run first.")
        return
    with open(OUTPUT_FILE) as f:
        data = json.load(f)
    ts = data.get("timestamp", "?")
    summary = data.get("signal_summary", "No signal")
    btc = data.get("btc_price", 0)
    days = data.get("days_to_expiry", "?")
    expiry = data.get("next_expiry", "?")
    print(f"[{ts}] BTC=${btc:,.0f} | {summary} | Next expiry: {expiry} ({days}d)")


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 options_poller.py [run|status|summary]")
        sys.exit(1)

    cmd = sys.argv[1].lower()
    if cmd == "run":
        result = run_poll()
        if result is None:
            sys.exit(1)
    elif cmd == "status":
        cmd_status()
    elif cmd == "summary":
        cmd_summary()
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: python3 options_poller.py [run|status|summary]")
        sys.exit(1)


if __name__ == "__main__":
    main()
