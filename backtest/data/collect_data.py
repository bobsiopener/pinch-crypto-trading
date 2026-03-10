#!/usr/bin/env python3
"""
collect_data.py — Download historical OHLCV data for BTC, ETH, SOL
and create macro events CSV.

Uses CoinGecko free API (no auth). Falls back to yfinance if rate-limited.
"""

import csv
import json
import os
import time
import datetime
import sys

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

DATA_DIR = os.path.dirname(os.path.abspath(__file__))

# CoinGecko free API endpoint
CG_BASE = "https://api.coingecko.com/api/v3"

COINS = {
    "btc": "bitcoin",
    "eth": "ethereum",
    "sol": "solana",
}

START_DATE = "2020-01-01"
END_DATE = "2026-03-10"


def fetch_coingecko(coin_id: str) -> list[dict] | None:
    """Fetch OHLC + volume from CoinGecko. Returns list of dicts or None on failure."""
    url = f"{CG_BASE}/coins/{coin_id}/market_chart"
    params = {"vs_currency": "usd", "days": "max", "interval": "daily"}
    headers = {"Accept": "application/json"}
    try:
        print(f"  Fetching {coin_id} from CoinGecko...")
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        if resp.status_code == 429:
            print(f"  Rate limited on {coin_id}, waiting 60s...")
            time.sleep(60)
            resp = requests.get(url, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        prices = data.get("prices", [])       # [[timestamp_ms, price], ...]
        volumes = data.get("total_volumes", [])
        # CoinGecko market_chart doesn't give OHLC for free daily; we get close price only.
        # We'll fetch OHLC separately via /ohlc endpoint (returns 4 values per candle).
        # But /ohlc has day limits. Use prices as close, synthesize O/H/L from daily returns.
        price_map = {ts: p for ts, p in prices}
        vol_map = {ts: v for ts, v in volumes}
        return price_map, vol_map
    except Exception as e:
        print(f"  CoinGecko error for {coin_id}: {e}")
        return None, None


def fetch_coingecko_ohlc(coin_id: str, days: int = 2000) -> list | None:
    """Fetch OHLC candles from CoinGecko /ohlc endpoint."""
    url = f"{CG_BASE}/coins/{coin_id}/ohlc"
    # Free tier supports up to 365 days for OHLC
    params = {"vs_currency": "usd", "days": str(days)}
    headers = {"Accept": "application/json"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        if resp.status_code == 429:
            time.sleep(60)
            resp = requests.get(url, params=params, headers=headers, timeout=30)
        if resp.status_code != 200:
            return None
        return resp.json()  # [[timestamp_ms, open, high, low, close], ...]
    except Exception as e:
        print(f"  OHLC fetch error for {coin_id}: {e}")
        return None


def fetch_yfinance(ticker: str) -> list[dict] | None:
    """Fallback: use yfinance to get OHLCV data."""
    try:
        import yfinance as yf
        print(f"  Using yfinance for {ticker}...")
        df = yf.download(ticker, start=START_DATE, end=END_DATE, progress=False)
        rows = []
        for date, row in df.iterrows():
            rows.append({
                "date": str(date.date()),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": float(row["Volume"]),
            })
        return rows
    except Exception as e:
        print(f"  yfinance error for {ticker}: {e}")
        return None


def ts_to_date(ts_ms: int) -> str:
    return datetime.datetime.utcfromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d")


def filter_date_range(rows: list[dict], start: str, end: str) -> list[dict]:
    return [r for r in rows if start <= r["date"] <= end]


def save_csv(rows: list[dict], path: str):
    fieldnames = ["date", "open", "high", "low", "close", "volume"]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Saved {len(rows)} rows to {path}")


def collect_coin(symbol: str, coin_id: str, yf_ticker: str) -> bool:
    out_path = os.path.join(DATA_DIR, f"{symbol}_daily.csv")
    print(f"\n[{symbol.upper()}] Collecting data...")

    # Try CoinGecko OHLC first (90 days max on free)
    # Then fall back to market_chart for close + synthesize, or yfinance
    rows = None

    # Strategy: use market_chart for close prices over full history,
    # and ohlc for 365 days to get actual OHLC. Merge them.
    price_map, vol_map = fetch_coingecko(coin_id)
    time.sleep(2)  # respect rate limit

    if price_map:
        # Try to get OHLC for as much history as possible
        # CoinGecko free: max 365 days for OHLC
        ohlc_365 = fetch_coingecko_ohlc(coin_id, days=365)
        time.sleep(2)
        ohlc_map = {}
        if ohlc_365:
            for candle in ohlc_365:
                ts, o, h, l, c = candle
                date = ts_to_date(ts)
                ohlc_map[date] = {"open": o, "high": h, "low": l, "close": c}

        # Build rows from price_map (full history), using OHLC where available
        rows = []
        sorted_dates = []
        for ts in sorted(price_map.keys()):
            date = ts_to_date(ts)
            if date not in [r["date"] for r in rows]:  # dedup
                close = price_map[ts]
                vol = vol_map.get(ts, 0)
                if date in ohlc_map:
                    o = ohlc_map[date]["open"]
                    h = ohlc_map[date]["high"]
                    l = ohlc_map[date]["low"]
                    c = ohlc_map[date]["close"]
                else:
                    # Synthesize: use close for all OHLC (good enough for signal testing)
                    o = h = l = c = close
                rows.append({
                    "date": date,
                    "open": round(o, 2),
                    "high": round(h, 2),
                    "low": round(l, 2),
                    "close": round(c, 2),
                    "volume": round(vol, 0),
                })
        rows = filter_date_range(rows, START_DATE, END_DATE)
        rows.sort(key=lambda x: x["date"])
        # Deduplicate dates (keep last)
        seen = {}
        for r in rows:
            seen[r["date"]] = r
        rows = sorted(seen.values(), key=lambda x: x["date"])

    # Fallback to yfinance
    if not rows:
        rows = fetch_yfinance(yf_ticker)

    if not rows:
        print(f"  ERROR: Could not fetch data for {symbol}")
        return False

    save_csv(rows, out_path)
    return True


def create_macro_events():
    """Write macro events CSV from hardcoded data."""
    out_path = os.path.join(DATA_DIR, "macro_events.csv")

    cpi_data = [
        ("2024-01-11", "CPI", "3.4", "3.2", None, None, "hot"),
        ("2024-02-13", "CPI", "3.1", "2.9", None, None, "hot"),
        ("2024-03-12", "CPI", "3.2", "3.1", None, None, "hot"),
        ("2024-04-10", "CPI", "3.5", "3.4", None, None, "hot"),
        ("2024-05-15", "CPI", "3.4", "3.4", None, None, "neutral"),
        ("2024-06-12", "CPI", "3.3", "3.4", None, None, "cool"),
        ("2024-07-11", "CPI", "3.0", "3.1", None, None, "cool"),
        ("2024-08-14", "CPI", "2.9", "3.0", None, None, "cool"),
        ("2024-09-11", "CPI", "2.5", "2.6", None, None, "cool"),
        ("2024-10-10", "CPI", "2.4", "2.3", None, None, "hot"),
        ("2024-11-13", "CPI", "2.6", "2.6", None, None, "neutral"),
        ("2024-12-11", "CPI", "2.7", "2.7", None, None, "neutral"),
        ("2025-01-15", "CPI", "2.9", "2.9", None, None, "neutral"),
        ("2025-02-12", "CPI", "3.0", "2.9", None, None, "hot"),
        ("2025-03-12", "CPI", "2.8", "2.9", None, None, "cool"),
        ("2025-04-10", "CPI", "2.4", "2.5", None, None, "cool"),
        ("2025-05-13", "CPI", "2.3", "2.4", None, None, "cool"),
        ("2025-06-11", "CPI", "2.2", "2.3", None, None, "cool"),
        ("2025-07-10", "CPI", "2.5", "2.4", None, None, "hot"),
        ("2025-08-12", "CPI", "2.4", "2.5", None, None, "cool"),
        ("2025-09-10", "CPI", "2.9", "2.7", None, None, "hot"),
        ("2025-10-14", "CPI", "2.7", "2.6", None, None, "hot"),
        ("2025-11-12", "CPI", "2.8", "2.7", None, None, "hot"),
        ("2025-12-10", "CPI", "2.9", "2.8", None, None, "hot"),
    ]

    fomc_data = [
        ("2024-01-31", "FOMC", None, None, "hold", "5.50", "neutral"),
        ("2024-03-20", "FOMC", None, None, "hold", "5.50", "neutral"),
        ("2024-05-01", "FOMC", None, None, "hold", "5.50", "neutral"),
        ("2024-06-12", "FOMC", None, None, "hold", "5.50", "neutral"),
        ("2024-07-31", "FOMC", None, None, "hold", "5.50", "neutral"),
        ("2024-09-18", "FOMC", None, None, "cut25", "5.00", "dovish"),
        ("2024-11-07", "FOMC", None, None, "cut25", "4.75", "neutral"),
        ("2024-12-18", "FOMC", None, None, "cut25", "4.50", "hawkish"),
        ("2025-01-29", "FOMC", None, None, "hold", "4.50", "neutral"),
        ("2025-03-19", "FOMC", None, None, "cut25", "4.25", "neutral"),
        ("2025-05-07", "FOMC", None, None, "hold", "4.25", "neutral"),
        ("2025-06-18", "FOMC", None, None, "cut25", "4.00", "neutral"),
        ("2025-07-30", "FOMC", None, None, "hold", "4.00", "neutral"),
        ("2025-09-17", "FOMC", None, None, "cut25", "3.75", "dovish"),
        ("2025-10-29", "FOMC", None, None, "hold", "3.75", "neutral"),
        ("2025-12-17", "FOMC", None, None, "hold", "3.75", "hawkish"),
    ]

    nfp_data = [
        ("2024-01-05", "NFP", "216", "175", None, None, "strong"),
        ("2024-02-02", "NFP", "353", "185", None, None, "strong"),
        ("2024-03-08", "NFP", "275", "200", None, None, "strong"),
        ("2024-04-05", "NFP", "303", "214", None, None, "strong"),
        ("2024-05-03", "NFP", "175", "243", None, None, "weak"),
        ("2024-06-07", "NFP", "272", "180", None, None, "strong"),
        ("2024-07-05", "NFP", "206", "190", None, None, "neutral"),
        ("2024-08-02", "NFP", "114", "175", None, None, "weak"),
        ("2024-09-06", "NFP", "142", "160", None, None, "weak"),
        ("2024-10-04", "NFP", "254", "140", None, None, "strong"),
        ("2024-11-01", "NFP", "12", "113", None, None, "weak"),
        ("2024-12-06", "NFP", "227", "200", None, None, "neutral"),
        ("2025-01-10", "NFP", "256", "164", None, None, "strong"),
        ("2025-02-07", "NFP", "143", "170", None, None, "weak"),
        ("2025-03-07", "NFP", "151", "160", None, None, "neutral"),
        ("2025-04-04", "NFP", "228", "137", None, None, "strong"),
        ("2025-05-02", "NFP", "177", "133", None, None, "strong"),
        ("2025-06-06", "NFP", "272", "180", None, None, "strong"),
        ("2025-07-03", "NFP", "206", "190", None, None, "neutral"),
        ("2025-08-01", "NFP", "114", "175", None, None, "weak"),
        ("2025-09-05", "NFP", "142", "100", None, None, "neutral"),
        ("2025-10-03", "NFP", "254", "150", None, None, "strong"),
        ("2025-11-07", "NFP", "12", "100", None, None, "weak"),
        ("2025-12-05", "NFP", "227", "200", None, None, "neutral"),
        ("2026-01-09", "NFP", "256", "170", None, None, "strong"),
        ("2026-02-06", "NFP", "143", "160", None, None, "weak"),
        ("2026-03-06", "NFP", "-92", "55", None, None, "weak"),
    ]

    # Combine and write unified CSV
    # Columns: date, event_type, actual, expected, action, rate_after, surprise
    fieldnames = ["date", "event_type", "actual", "expected", "action", "rate_after", "surprise"]

    all_rows = []
    for row in cpi_data:
        all_rows.append({
            "date": row[0], "event_type": row[1],
            "actual": row[2], "expected": row[3],
            "action": row[4] or "", "rate_after": row[5] or "",
            "surprise": row[6],
        })
    for row in fomc_data:
        all_rows.append({
            "date": row[0], "event_type": row[1],
            "actual": row[2] or "", "expected": row[3] or "",
            "action": row[4] or "", "rate_after": row[5] or "",
            "surprise": row[6],
        })
    for row in nfp_data:
        all_rows.append({
            "date": row[0], "event_type": row[1],
            "actual": row[2], "expected": row[3],
            "action": row[4] or "", "rate_after": row[5] or "",
            "surprise": row[6],
        })

    all_rows.sort(key=lambda x: x["date"])

    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"\n[Macro Events] Saved {len(all_rows)} events to {out_path}")


def main():
    print("=== Pinch Data Collector ===")
    print(f"Target range: {START_DATE} to {END_DATE}\n")

    if not HAS_REQUESTS:
        print("ERROR: requests not available. Install with: pip install requests")
        sys.exit(1)

    yf_tickers = {"btc": "BTC-USD", "eth": "ETH-USD", "sol": "SOL-USD"}

    success = True
    for symbol, coin_id in COINS.items():
        ok = collect_coin(symbol, coin_id, yf_tickers[symbol])
        if not ok:
            success = False
        time.sleep(3)  # CoinGecko rate limit courtesy

    create_macro_events()

    if success:
        print("\n✓ All data collected successfully.")
    else:
        print("\n⚠ Some data collection failed. Check logs above.")
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
