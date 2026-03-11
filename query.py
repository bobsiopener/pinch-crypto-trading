#!/usr/bin/env python3
"""
query.py — Natural language query tool for the Pinch market database.

Usage:
    python3 query.py "BTC price"
    python3 query.py "SPY last 30 days"
    python3 query.py "fear and greed"
    python3 query.py "yield curve"
    python3 query.py "BTC vs ETH last 1 year"
    python3 query.py "status"
    python3 query.py --json "BTC price"
    python3 query.py --csv "SPY last 30 days"
    python3 query.py --limit 20 "BTC price 2024-01-01 to 2025-01-01"
    python3 query.py "sql SELECT * FROM prices WHERE symbol='BTC' LIMIT 5"

No AI — just smart keyword/pattern matching → SQL.
"""

import sqlite3
import sys
import re
import json
import csv
import io
import os
import math
from datetime import datetime, timedelta, timezone, date

DB_PATH = "/mnt/media/market_data/pinch_market.db"

# ─── Symbol aliases ────────────────────────────────────────────────────────────

SYMBOL_ALIASES = {
    'bitcoin': 'BTC', 'btc': 'BTC',
    'ethereum': 'ETH', 'eth': 'ETH',
    'solana': 'SOL', 'sol': 'SOL',
    'ripple': 'XRP', 'xrp': 'XRP',
    'cardano': 'ADA', 'ada': 'ADA',
    'dogecoin': 'DOGE', 'doge': 'DOGE',
    'bnb': 'BNB',
    'avalanche': 'AVAX', 'avax': 'AVAX',
    'chainlink': 'LINK', 'link': 'LINK',
    'polkadot': 'DOT', 'dot': 'DOT',
    'spy': 'SPY', 'sp500': 'SPY', 's&p': 'SPY', 's&p500': 'SPY',
    'nasdaq': 'QQQ', 'qqq': 'QQQ', 'ndx': 'QQQ',
    'iwm': 'IWM', 'russell': 'IWM', 'russell2000': 'IWM',
    'gold': 'GLD', 'gld': 'GLD',
    'bonds': 'TLT', 'tlt': 'TLT',
    'nvda': 'NVDA', 'nvidia': 'NVDA',
    'aapl': 'AAPL', 'apple': 'AAPL',
    'msft': 'MSFT', 'microsoft': 'MSFT',
    'amzn': 'AMZN', 'amazon': 'AMZN',
    'goog': 'GOOG', 'google': 'GOOG', 'alphabet': 'GOOG',
    'meta': 'META', 'facebook': 'META',
    'tsla': 'TSLA', 'tesla': 'TSLA',
    'amd': 'AMD',
    'mstr': 'MSTR', 'microstrategy': 'MSTR',
    'pltr': 'PLTR', 'palantir': 'PLTR',
    'anet': 'ANET', 'arista': 'ANET',
    'avgo': 'AVGO', 'broadcom': 'AVGO',
    'orcl': 'ORCL', 'oracle': 'ORCL',
    'csco': 'CSCO', 'cisco': 'CSCO',
    'wfc': 'WFC', 'wells fargo': 'WFC',
    'brk': 'BRK-B', 'berkshire': 'BRK-B', 'brk-b': 'BRK-B', 'brkb': 'BRK-B',
    'xle': 'XLE', 'energy': 'XLE',
    'vix': 'VIX',
    'oil': 'DCOILWTICO', 'wti': 'DCOILWTICO', 'crude': 'DCOILWTICO',
    'brent': 'DCOILBRENTEU',
    'treasury': 'DGS10', '10 year': 'DGS10', '10y': 'DGS10', '10yr': 'DGS10',
    '10-year': 'DGS10', '10year': 'DGS10',
    '2 year': 'DGS2', '2y': 'DGS2', '2yr': 'DGS2', '2-year': 'DGS2',
    '5 year': 'DGS5', '5y': 'DGS5', '5yr': 'DGS5', '5-year': 'DGS5',
    '30 year': 'DGS30', '30y': 'DGS30', '30yr': 'DGS30', '30-year': 'DGS30',
    'cpi': 'CPIAUCSL', 'inflation': 'CPIAUCSL',
    'pce': 'PCEPI',
    'unemployment': 'UNRATE', 'jobless': 'ICSA',
    'fed funds': 'FEDFUNDS', 'fedfunds': 'FEDFUNDS', 'ffr': 'FEDFUNDS',
    'fear': 'fear_greed_crypto', 'greed': 'fear_greed_crypto',
    'm2': 'M2SL', 'money supply': 'M2SL',
    'natural gas': 'DHHNGSP', 'natgas': 'DHHNGSP',
    'high yield': 'BAMLH0A0HYM2', 'hy spread': 'BAMLH0A0HYM2', 'junk': 'BAMLH0A0HYM2',
    'yield spread': 'T10Y2Y', 't10y2y': 'T10Y2Y',
    'consumer sentiment': 'UMCSENT', 'umcsent': 'UMCSENT',
}

FRED_SERIES = {
    'DGS10', 'DGS2', 'DGS5', 'DGS30', 'CPIAUCSL', 'PCEPI',
    'FEDFUNDS', 'UNRATE', 'ICSA', 'M2SL', 'DCOILWTICO', 'DCOILBRENTEU',
    'DHHNGSP', 'BAMLH0A0HYM2', 'T10Y2Y', 'UMCSENT', 'VIXCLS',
}

CRYPTO_SYMBOLS = {'BTC', 'ETH', 'SOL', 'XRP', 'ADA', 'DOGE', 'BNB', 'AVAX', 'LINK', 'DOT'}

# ─── DB helpers ───────────────────────────────────────────────────────────────

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def run_sql(sql, params=()):
    conn = get_conn()
    try:
        cur = conn.execute(sql, params)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description] if cur.description else []
        return cols, [list(r) for r in rows]
    finally:
        conn.close()

# ─── Parsing helpers ──────────────────────────────────────────────────────────

def now_ts():
    return int(datetime.now(timezone.utc).timestamp())

def ts_days_ago(n):
    return int((datetime.now(timezone.utc) - timedelta(days=n)).timestamp())

def ts_from_date(d_str):
    """Parse YYYY-MM-DD → unix timestamp."""
    dt = datetime.strptime(d_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp())

def ytd_start_ts():
    today = datetime.now(timezone.utc)
    start = datetime(today.year, 1, 1, tzinfo=timezone.utc)
    return int(start.timestamp())

def fmt_dt(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")

def fmt_dt_full(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")

def fmt_price(v):
    if v is None:
        return "N/A"
    if abs(v) >= 1000:
        return f"${v:,.2f}"
    elif abs(v) >= 1:
        return f"${v:.4f}"
    else:
        return f"${v:.6f}"

def fmt_num(v, decimals=2):
    if v is None:
        return "N/A"
    return f"{v:,.{decimals}f}"

def pct_change(old, new):
    if old is None or old == 0:
        return None
    return (new - old) / abs(old) * 100

def extract_symbols(q_lower):
    """Find all ticker symbols in the query."""
    found = []
    # Check multi-word aliases first (sorted by length desc)
    for alias, sym in sorted(SYMBOL_ALIASES.items(), key=lambda x: -len(x[0])):
        if alias in q_lower and sym not in found:
            found.append(sym)
    # Also look for uppercase tickers like "NVDA", "AAPL" in the original query
    words = re.findall(r'\b[A-Z]{2,5}(?:-[AB])?\b', q_lower.upper())
    for w in words:
        if w in {v for v in SYMBOL_ALIASES.values()} and w not in found:
            found.append(w)
    return found

def extract_dates(q):
    """Return (start_ts, end_ts) or (None, None)."""
    # "2024-01-01 to 2025-01-01"
    m = re.search(r'(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})', q)
    if m:
        return ts_from_date(m.group(1)), ts_from_date(m.group(2))
    return None, None

def extract_period(q_lower):
    """Return days or None. E.g. 'last 30 days' → 30."""
    m = re.search(r'last\s+(\d+)\s+(day|week|month|year)s?', q_lower)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        mul = {'day': 1, 'week': 7, 'month': 30, 'year': 365}[unit]
        return n * mul
    # shorthand: "30d", "7d", "1y", "6m"
    m = re.search(r'\b(\d+)(d|w|m|y)\b', q_lower)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        mul = {'d': 1, 'w': 7, 'm': 30, 'y': 365}[unit]
        return n * mul
    # named periods
    if 'ytd' in q_lower or 'year to date' in q_lower:
        return None  # special case
    return None

def is_ytd(q_lower):
    return 'ytd' in q_lower or 'year to date' in q_lower

# ─── Formatters ───────────────────────────────────────────────────────────────

def print_table(cols, rows, title=None):
    if title:
        print(f"\n{'─'*60}")
        print(f"  {title}")
        print(f"{'─'*60}")
    if not rows:
        print("  (no data)")
        return
    # calc widths
    widths = [len(str(c)) for c in cols]
    for row in rows:
        for i, v in enumerate(row):
            widths[i] = max(widths[i], len(str(v) if v is not None else 'N/A'))
    # header
    header = "  " + "  ".join(str(c).ljust(widths[i]) for i, c in enumerate(cols))
    sep = "  " + "  ".join("─" * w for w in widths)
    print(header)
    print(sep)
    for row in rows:
        line = "  " + "  ".join(str(v if v is not None else 'N/A').ljust(widths[i]) for i, v in enumerate(row))
        print(line)

def print_sql(sql, params=()):
    display = sql.strip()
    if params:
        # inline params for display
        for p in params:
            display = display.replace('?', repr(p), 1)
    print(f"\n  SQL: {display}\n")

# ─── Query handlers ───────────────────────────────────────────────────────────

def handle_status(args):
    conn = get_conn()
    size_bytes = os.path.getsize(DB_PATH)
    size_mb = size_bytes / (1024 * 1024)
    print(f"\n{'═'*60}")
    print(f"  📊 Pinch Market Database Status")
    print(f"  Path: {DB_PATH}")
    print(f"  Size: {size_mb:.1f} MB ({size_bytes:,} bytes)")
    print(f"{'═'*60}")

    tables = [
        ('prices', 'timestamp', 'symbol'),
        ('economic_data', 'timestamp', 'series_id'),
        ('onchain_metrics', 'timestamp', 'metric'),
        ('sentiment', 'timestamp', 'indicator'),
        ('options_chain', 'timestamp', 'symbol'),
        ('derived_metrics', 'timestamp', 'metric'),
        ('funding_rates', 'timestamp', 'symbol'),
        ('vix_term_structure', 'timestamp', 'expiry'),
        ('collection_log', 'timestamp', None),
    ]
    for tbl, ts_col, key_col in tables:
        try:
            row = conn.execute(f"""
                SELECT COUNT(*) as cnt,
                       MIN(datetime({ts_col},'unixepoch')) as min_dt,
                       MAX(datetime({ts_col},'unixepoch')) as max_dt
                FROM {tbl}
            """).fetchone()
            key_info = ""
            if key_col:
                n_keys = conn.execute(f"SELECT COUNT(DISTINCT {key_col}) FROM {tbl}").fetchone()[0]
                key_info = f" ({n_keys} unique {key_col}s)"
            print(f"  {tbl:<22} {row[0]:>8,} rows  {str(row[1])[:10]} → {str(row[2])[:10]}{key_info}")
        except Exception as e:
            print(f"  {tbl:<22} error: {e}")
    conn.close()
    print()


def handle_symbols(args):
    sql = "SELECT DISTINCT symbol, asset_class, COUNT(*) as rows, MIN(datetime(timestamp,'unixepoch')) as first, MAX(datetime(timestamp,'unixepoch')) as last FROM prices GROUP BY symbol ORDER BY asset_class, symbol"
    cols, rows = run_sql(sql)
    print_sql(sql)
    print_table(['Symbol', 'Class', 'Rows', 'First', 'Last'],
                [[r[0], r[1], f"{r[2]:,}", r[3][:10], r[4][:10]] for r in rows],
                title="Available Symbols in prices table")


def handle_series(args):
    sql = "SELECT DISTINCT series_id, COUNT(*) as rows, MIN(datetime(timestamp,'unixepoch')) as first, MAX(datetime(timestamp,'unixepoch')) as last FROM economic_data GROUP BY series_id ORDER BY series_id"
    cols, rows = run_sql(sql)
    print_sql(sql)
    print_table(['Series', 'Rows', 'First', 'Last'],
                [[r[0], f"{r[1]:,}", r[2][:10], r[3][:10]] for r in rows],
                title="FRED Economic Series")


def handle_price(symbol, start_ts=None, end_ts=None, days=None, limit=10, args=None):
    """Price query — single latest, range, or time window."""
    is_fred = symbol in FRED_SERIES
    table = 'economic_data' if is_fred else 'prices'
    sym_col = 'series_id' if is_fred else 'symbol'

    if start_ts and end_ts:
        sql = f"SELECT timestamp, {'value' if is_fred else 'open, high, low, close, volume'} FROM {table} WHERE {sym_col}=? AND timestamp >= ? AND timestamp <= ? ORDER BY timestamp"
        params = (symbol, start_ts, end_ts)
        lim = limit
    elif days:
        ts_start = ts_days_ago(days)
        sql = f"SELECT timestamp, {'value' if is_fred else 'open, high, low, close, volume'} FROM {table} WHERE {sym_col}=? AND timestamp >= ? ORDER BY timestamp"
        params = (symbol, ts_start)
        lim = limit
    elif is_ytd(args.query.lower() if args else ''):
        ts_start = ytd_start_ts()
        sql = f"SELECT timestamp, {'value' if is_fred else 'open, high, low, close, volume'} FROM {table} WHERE {sym_col}=? AND timestamp >= ? ORDER BY timestamp"
        params = (symbol, ts_start)
        lim = limit
    else:
        # Latest single value
        sql = f"SELECT timestamp, {'value' if is_fred else 'open, high, low, close, volume'} FROM {table} WHERE {sym_col}=? ORDER BY timestamp DESC LIMIT 2"
        params = (symbol,)
        lim = 2

    print_sql(sql, params)
    cols_raw, rows = run_sql(sql, params)

    if not rows:
        print(f"  No data found for {symbol}")
        return

    if is_fred:
        if len(rows) == 1 or (not start_ts and not days and not is_ytd(args.query.lower() if args else '')):
            # Latest
            latest = rows[0]
            prev = rows[1] if len(rows) > 1 else None
            chg = f" ({pct_change(prev[1], latest[1]):+.2f}% prev)" if prev and prev[1] else ""
            print(f"\n  {symbol}: {fmt_num(latest[1])} @ {fmt_dt(latest[0])}{chg}")
        else:
            display_rows = rows[-lim:] if len(rows) > lim else rows
            print_table(['Date', 'Value'],
                        [[fmt_dt(r[0]), fmt_num(r[1])] for r in display_rows],
                        title=f"{symbol} — {len(rows)} observations (showing last {len(display_rows)})")
    else:
        if start_ts or days or is_ytd(args.query.lower() if args else ''):
            display_rows = rows[-lim:] if len(rows) > lim else rows
            print_table(['Date', 'Open', 'High', 'Low', 'Close', 'Volume'],
                        [[fmt_dt(r[0]),
                          fmt_price(r[1]), fmt_price(r[2]), fmt_price(r[3]), fmt_price(r[4]),
                          fmt_num(r[5], 0) if r[5] else 'N/A']
                         for r in display_rows],
                        title=f"{symbol} prices — {len(rows)} bars (showing last {len(display_rows)})")
        else:
            # Single latest
            latest = rows[0]
            prev = rows[1] if len(rows) > 1 else None
            chg = f" ({pct_change(prev[4], latest[4]):+.2f}%)" if prev and prev[4] else ""
            print(f"\n  {symbol}: {fmt_price(latest[4])}{chg}  @ {fmt_dt_full(latest[0])}")
            print(f"  Open: {fmt_price(latest[1])}  High: {fmt_price(latest[2])}  Low: {fmt_price(latest[3])}  Vol: {fmt_num(latest[5], 0) if latest[5] else 'N/A'}")


def handle_return(symbol, days=30, args=None):
    """Return % over period."""
    ts_start = ts_days_ago(days)
    is_fred = symbol in FRED_SERIES
    if is_fred:
        sql = "SELECT timestamp, value FROM economic_data WHERE series_id=? AND timestamp >= ? ORDER BY timestamp"
    else:
        sql = "SELECT timestamp, close FROM prices WHERE symbol=? AND timestamp >= ? ORDER BY timestamp"
    params = (symbol, ts_start)
    print_sql(sql, params)
    _, rows = run_sql(sql, params)
    if len(rows) < 2:
        print(f"  Not enough data for {symbol} over {days} days")
        return
    first_close = rows[0][1]
    last_close = rows[-1][1]
    ret = pct_change(first_close, last_close)
    print(f"\n  {symbol} return over {days} days:")
    print(f"  Start ({fmt_dt(rows[0][0])}): {fmt_price(first_close)}")
    print(f"  End   ({fmt_dt(rows[-1][0])}): {fmt_price(last_close)}")
    print(f"  Return: {ret:+.2f}%")


def handle_best_worst(best=True, days=7, limit=10, args=None):
    """Rank all symbols by return over period."""
    ts_start = ts_days_ago(days)
    direction = "Best" if best else "Worst"
    order = "DESC" if best else "ASC"

    # Get first and last close for each symbol in window
    sql = f"""
    WITH first_prices AS (
        SELECT symbol, close, timestamp,
               ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY timestamp ASC) as rn
        FROM prices WHERE timestamp >= ? AND close IS NOT NULL
    ),
    last_prices AS (
        SELECT symbol, close, timestamp,
               ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY timestamp DESC) as rn
        FROM prices WHERE timestamp >= ? AND close IS NOT NULL
    )
    SELECT f.symbol,
           f.close as start_price,
           l.close as end_price,
           (l.close - f.close) / ABS(f.close) * 100 as pct_return,
           datetime(f.timestamp,'unixepoch') as start_dt,
           datetime(l.timestamp,'unixepoch') as end_dt
    FROM (SELECT * FROM first_prices WHERE rn=1) f
    JOIN (SELECT * FROM last_prices WHERE rn=1) l ON f.symbol = l.symbol
    ORDER BY pct_return {order}
    LIMIT ?
    """
    params = (ts_start, ts_start, limit)
    print_sql(sql, params)
    _, rows = run_sql(sql, params)
    if not rows:
        print(f"  No data for last {days} days")
        return
    print_table(['Symbol', 'Start', 'End', 'Return%', 'From', 'To'],
                [[r[0], fmt_price(r[1]), fmt_price(r[2]),
                  f"{r[3]:+.2f}%", str(r[4])[:10], str(r[5])[:10]]
                 for r in rows],
                title=f"{direction} Performers — last {days} days")


def handle_drawdown(symbol, args=None):
    """Max drawdown from ATH."""
    sql = "SELECT timestamp, close FROM prices WHERE symbol=? AND close IS NOT NULL ORDER BY timestamp"
    params = (symbol,)
    print_sql(sql, params)
    _, rows = run_sql(sql, params)
    if not rows:
        print(f"  No data for {symbol}")
        return
    peak = rows[0][1]
    peak_ts = rows[0][0]
    max_dd = 0.0
    trough_ts = rows[0][0]
    trough_price = rows[0][1]
    current_peak = rows[0][1]
    current_peak_ts = rows[0][0]
    for ts, close in rows[1:]:
        if close > current_peak:
            current_peak = close
            current_peak_ts = ts
        dd = (close - current_peak) / current_peak * 100
        if dd < max_dd:
            max_dd = dd
            peak = current_peak
            peak_ts = current_peak_ts
            trough_price = close
            trough_ts = ts
    ath = max(r[1] for r in rows)
    ath_ts = next(r[0] for r in rows if r[1] == ath)
    current = rows[-1][1]
    dd_from_ath = pct_change(ath, current)
    print(f"\n  {symbol} Drawdown Analysis:")
    print(f"  ATH:           {fmt_price(ath)} @ {fmt_dt(ath_ts)}")
    print(f"  Current:       {fmt_price(current)} @ {fmt_dt(rows[-1][0])}")
    print(f"  DD from ATH:   {dd_from_ath:+.2f}%")
    print(f"  Max DD (hist): {max_dd:.2f}% (peak {fmt_price(peak)} @ {fmt_dt(peak_ts)} → trough {fmt_price(trough_price)} @ {fmt_dt(trough_ts)})")


def handle_comparison(sym1, sym2, days=365, limit=10, args=None):
    """Side-by-side price comparison + correlation."""
    ts_start = ts_days_ago(days)

    def get_prices(sym):
        is_fred = sym in FRED_SERIES
        if is_fred:
            sql = "SELECT timestamp, value FROM economic_data WHERE series_id=? AND timestamp >= ? ORDER BY timestamp"
        else:
            sql = "SELECT timestamp, close FROM prices WHERE symbol=? AND timestamp >= ? ORDER BY timestamp"
        _, rows = run_sql(sql, (sym, ts_start))
        return {r[0]: r[1] for r in rows}

    p1 = get_prices(sym1)
    p2 = get_prices(sym2)

    # Align on common timestamps (or nearest day)
    all_ts = sorted(set(list(p1.keys()) + list(p2.keys())))
    combined = []
    last1, last2 = None, None
    for ts in all_ts:
        v1 = p1.get(ts, last1)
        v2 = p2.get(ts, last2)
        if v1 is not None:
            last1 = v1
        if v2 is not None:
            last2 = v2
        if v1 is not None and v2 is not None:
            combined.append((ts, v1, v2))

    if len(combined) < 2:
        print(f"  Not enough aligned data for {sym1} vs {sym2}")
        return

    # Correlation
    xs = [r[1] for r in combined]
    ys = [r[2] for r in combined]
    n = len(xs)
    mx, my = sum(xs)/n, sum(ys)/n
    cov = sum((xs[i]-mx)*(ys[i]-my) for i in range(n)) / n
    sx = math.sqrt(sum((x-mx)**2 for x in xs)/n)
    sy = math.sqrt(sum((y-my)**2 for y in ys)/n)
    corr = cov / (sx * sy) if sx > 0 and sy > 0 else 0

    # Returns
    r1 = pct_change(combined[0][1], combined[-1][1])
    r2 = pct_change(combined[0][2], combined[-1][2])

    display = combined[-limit:]
    print(f"\n  SQL: prices WHERE symbol IN ('{sym1}','{sym2}') AND timestamp >= {ts_start} aligned\n")
    print_table(['Date', sym1, sym2, f'{sym1} chg%', f'{sym2} chg%'],
                [[fmt_dt(r[0]),
                  fmt_price(r[1]), fmt_price(r[2]),
                  f"{pct_change(combined[0][1], r[1]):+.2f}%" if combined[0][1] else 'N/A',
                  f"{pct_change(combined[0][2], r[2]):+.2f}%" if combined[0][2] else 'N/A']
                 for r in display],
                title=f"{sym1} vs {sym2} — {days}d (showing last {len(display)} of {len(combined)})")
    print(f"\n  {sym1} return: {r1:+.2f}%  |  {sym2} return: {r2:+.2f}%")
    print(f"  Correlation ({len(combined)} obs): {corr:.4f}  ({'positive' if corr > 0 else 'negative'}, {'strong' if abs(corr) > 0.7 else 'moderate' if abs(corr) > 0.3 else 'weak'})")


def handle_yield_curve(args=None):
    """Latest 2Y, 5Y, 10Y, 30Y + spreads."""
    series = [('DGS2', '2Y'), ('DGS5', '5Y'), ('DGS10', '10Y'), ('DGS30', '30Y')]
    sql = """
    SELECT e.series_id, e.value, datetime(e.timestamp,'unixepoch')
    FROM economic_data e
    INNER JOIN (
        SELECT series_id, MAX(timestamp) as max_ts
        FROM economic_data
        WHERE series_id IN ('DGS2','DGS5','DGS10','DGS30')
        GROUP BY series_id
    ) latest ON e.series_id = latest.series_id AND e.timestamp = latest.max_ts
    ORDER BY e.series_id
    """
    print_sql(sql)
    _, rows = run_sql(sql)
    data = {r[0]: (r[1], r[2]) for r in rows}
    print(f"\n  Yield Curve (latest readings):")
    for sid, label in series:
        if sid in data:
            v, dt = data[sid]
            print(f"  {label} ({sid}): {v:.2f}% @ {dt[:10]}")
    # Spreads
    if 'DGS2' in data and 'DGS10' in data:
        spread = data['DGS10'][0] - data['DGS2'][0]
        print(f"\n  2Y-10Y Spread: {spread:+.2f}% ({'normal' if spread > 0 else 'INVERTED ⚠️'})")
    if 'DGS5' in data and 'DGS30' in data:
        spread2 = data['DGS30'][0] - data['DGS5'][0]
        print(f"  5Y-30Y Spread: {spread2:+.2f}%")


def handle_fear_greed(history=False, limit=10, args=None):
    """Fear & Greed index."""
    if history:
        sql = "SELECT timestamp, indicator, value, label FROM sentiment WHERE indicator='fear_greed_crypto' ORDER BY timestamp DESC LIMIT ?"
        params = (limit,)
    else:
        sql = "SELECT timestamp, indicator, value, label FROM sentiment WHERE indicator='fear_greed_crypto' ORDER BY timestamp DESC LIMIT 1"
        params = ()
    print_sql(sql, params)
    _, rows = run_sql(sql, params)
    if not rows:
        # Try general fear_greed
        sql2 = sql.replace('fear_greed_crypto', 'fear_greed')
        _, rows = run_sql(sql2, params)
    if not rows:
        print("  No fear & greed data found")
        return
    if not history:
        r = rows[0]
        emoji = '😱' if r[2] < 25 else '😨' if r[2] < 40 else '😐' if r[2] < 60 else '😄' if r[2] < 80 else '🤑'
        print(f"\n  Fear & Greed Index ({r[1]}): {r[2]:.0f} — {r[3]} {emoji}  @ {fmt_dt(r[0])}")
    else:
        print_table(['Date', 'Indicator', 'Value', 'Label'],
                    [[fmt_dt(r[0]), r[1], f"{r[2]:.0f}", r[3]] for r in rows],
                    title="Fear & Greed History")


def handle_vix(args=None):
    """Latest VIX from prices or economic_data."""
    # Try prices first (VIX symbol)
    sql = "SELECT timestamp, close FROM prices WHERE symbol='VIX' ORDER BY timestamp DESC LIMIT 1"
    print_sql(sql)
    _, rows = run_sql(sql)
    if rows:
        r = rows[0]
        print(f"\n  VIX: {r[1]:.2f}  @ {fmt_dt_full(r[0])}")
    else:
        sql2 = "SELECT timestamp, value FROM economic_data WHERE series_id='VIXCLS' ORDER BY timestamp DESC LIMIT 1"
        print_sql(sql2)
        _, rows2 = run_sql(sql2)
        if rows2:
            r = rows2[0]
            print(f"\n  VIX (VIXCLS): {r[1]:.2f}  @ {fmt_dt(r[0])}")
        else:
            print("  No VIX data found")


def handle_vix_term_structure(args=None):
    """VIX term structure."""
    sql = "SELECT expiry, vix_value, datetime(timestamp,'unixepoch') FROM vix_term_structure ORDER BY timestamp DESC, expiry"
    print_sql(sql)
    _, rows = run_sql(sql)
    if not rows:
        print("  No VIX term structure data")
        return
    print_table(['Expiry', 'VIX Value', 'As Of'],
                [[r[0], f"{r[1]:.2f}", r[2][:10]] for r in rows],
                title="VIX Term Structure")


def handle_max_pain(symbol, args=None):
    """Latest max pain for symbol from derived_metrics."""
    sql = "SELECT timestamp, metric, value, metadata FROM derived_metrics WHERE symbol=? AND metric LIKE 'max_pain%' ORDER BY timestamp DESC, metric LIMIT 20"
    params = (symbol,)
    print_sql(sql, params)
    _, rows = run_sql(sql, params)
    if not rows:
        print(f"  No max pain data for {symbol}")
        return
    print_table(['As Of', 'Expiry', 'Max Pain'],
                [[fmt_dt(r[0]),
                  r[1].replace('max_pain_', ''),
                  fmt_price(r[2])]
                 for r in rows],
                title=f"{symbol} Max Pain by Expiry")


def handle_pcr(symbol, args=None):
    """Put/call ratio from derived_metrics."""
    sql = "SELECT timestamp, metric, value FROM derived_metrics WHERE symbol=? AND metric LIKE 'pc_ratio%' ORDER BY timestamp DESC, metric LIMIT 20"
    params = (symbol,)
    print_sql(sql, params)
    _, rows = run_sql(sql, params)
    if not rows:
        print(f"  No put/call ratio data for {symbol}")
        return
    print_table(['As Of', 'Metric', 'Expiry', 'PCR'],
                [[fmt_dt(r[0]),
                  r[1].split('_')[0] + '_' + r[1].split('_')[1] + '_' + r[1].split('_')[2],
                  '_'.join(r[1].split('_')[3:]) if len(r[1].split('_')) > 3 else 'N/A',
                  fmt_num(r[2], 4)]
                 for r in rows],
                title=f"{symbol} Put/Call Ratios")


def handle_options_oi(symbol, limit=10, args=None):
    """Total OI from options_chain."""
    sql = """
    SELECT expiry, option_type,
           SUM(open_interest) as total_oi,
           AVG(implied_volatility) as avg_iv,
           COUNT(*) as contracts
    FROM options_chain
    WHERE symbol=?
    AND timestamp = (SELECT MAX(timestamp) FROM options_chain WHERE symbol=?)
    GROUP BY expiry, option_type
    ORDER BY expiry, option_type
    LIMIT ?
    """
    params = (symbol, symbol, limit)
    print_sql(sql, params)
    _, rows = run_sql(sql, params)
    if not rows:
        print(f"  No options OI data for {symbol}")
        return
    print_table(['Expiry', 'Type', 'Total OI', 'Avg IV', 'Contracts'],
                [[r[0], r[1], fmt_num(r[2], 0), f"{r[3]:.1f}%" if r[3] else 'N/A', r[4]]
                 for r in rows],
                title=f"{symbol} Options Open Interest")


def handle_onchain(symbol, metric_filter=None, limit=10, args=None):
    """On-chain metrics."""
    if metric_filter:
        sql = "SELECT timestamp, metric, value FROM onchain_metrics WHERE symbol=? AND metric LIKE ? ORDER BY timestamp DESC LIMIT ?"
        params = (symbol, f'%{metric_filter}%', limit)
    else:
        # Latest value for each metric
        sql = "SELECT metric, value, datetime(MAX(timestamp),'unixepoch') as last_dt FROM onchain_metrics WHERE symbol=? GROUP BY metric ORDER BY metric"
        params = (symbol,)
    print_sql(sql, params)
    _, rows = run_sql(sql, params)
    if not rows:
        print(f"  No on-chain data for {symbol}")
        return
    if metric_filter:
        print_table(['Date', 'Metric', 'Value'],
                    [[fmt_dt(r[0]), r[1], fmt_num(r[2])] for r in rows],
                    title=f"{symbol} On-Chain: {metric_filter}")
    else:
        print_table(['Metric', 'Latest Value', 'As Of'],
                    [[r[0], fmt_num(r[1]), str(r[2])[:10]] for r in rows],
                    title=f"{symbol} On-Chain Metrics (latest per metric)")


def handle_funding_rates(symbol=None, limit=10, args=None):
    """Crypto funding rates."""
    if symbol:
        sql = "SELECT datetime(timestamp,'unixepoch'), symbol, exchange, rate FROM funding_rates WHERE symbol=? ORDER BY timestamp DESC LIMIT ?"
        params = (symbol, limit)
    else:
        sql = "SELECT datetime(timestamp,'unixepoch'), symbol, exchange, rate FROM funding_rates ORDER BY timestamp DESC LIMIT ?"
        params = (limit,)
    print_sql(sql, params)
    _, rows = run_sql(sql, params)
    if not rows:
        print(f"  No funding rate data")
        return
    print_table(['Date', 'Symbol', 'Exchange', 'Rate'],
                [[r[0][:16], r[1], r[2], f"{r[3]*100:.6f}%"] for r in rows],
                title="Funding Rates")


def handle_oil(args=None):
    """WTI and Brent latest."""
    sql = "SELECT series_id, value, datetime(MAX(timestamp),'unixepoch') FROM economic_data WHERE series_id IN ('DCOILWTICO','DCOILBRENTEU') GROUP BY series_id"
    print_sql(sql)
    _, rows = run_sql(sql)
    if not rows:
        print("  No oil price data")
        return
    for r in rows:
        label = 'WTI Crude' if r[0] == 'DCOILWTICO' else 'Brent Crude'
        print(f"\n  {label} ({r[0]}): ${r[1]:.2f}/bbl @ {str(r[2])[:10]}")


def handle_economic(series_id, history=False, limit=10, args=None):
    """Generic economic data query."""
    if history:
        sql = "SELECT timestamp, value FROM economic_data WHERE series_id=? ORDER BY timestamp DESC LIMIT ?"
        params = (series_id, limit)
        _, rows = run_sql(sql, params)
        print_sql(sql, params)
        if rows:
            rows.reverse()
            print_table(['Date', series_id],
                        [[fmt_dt(r[0]), fmt_num(r[1])] for r in rows],
                        title=f"{series_id} History (last {len(rows)})")
    else:
        sql = "SELECT timestamp, value FROM economic_data WHERE series_id=? ORDER BY timestamp DESC LIMIT 2"
        params = (series_id,)
        print_sql(sql, params)
        _, rows = run_sql(sql, params)
        if rows:
            latest = rows[0]
            prev = rows[1] if len(rows) > 1 else None
            chg = f" (prev: {fmt_num(prev[1])})" if prev else ""
            print(f"\n  {series_id}: {fmt_num(latest[1])} @ {fmt_dt(latest[0])}{chg}")
        else:
            print(f"  No data for {series_id}")


def handle_correlation(sym1, sym2, days=30, args=None):
    """Correlation between two symbols."""
    ts_start = ts_days_ago(days)

    def get_daily(sym):
        is_fred = sym in FRED_SERIES
        if is_fred:
            sql = "SELECT date(timestamp,'unixepoch') as dt, AVG(value) FROM economic_data WHERE series_id=? AND timestamp >= ? GROUP BY dt ORDER BY dt"
        else:
            sql = "SELECT date(timestamp,'unixepoch') as dt, AVG(close) FROM prices WHERE symbol=? AND timestamp >= ? GROUP BY dt ORDER BY dt"
        _, rows = run_sql(sql, (sym, ts_start))
        return {r[0]: r[1] for r in rows}

    p1 = get_daily(sym1)
    p2 = get_daily(sym2)
    common = sorted(set(p1.keys()) & set(p2.keys()))

    sql = f"SELECT date(timestamp,'unixepoch'), AVG(close) FROM prices WHERE symbol IN ('{sym1}','{sym2}') AND timestamp >= {ts_start} GROUP BY date(timestamp,'unixepoch'), symbol"
    print_sql(sql)

    if len(common) < 5:
        print(f"  Not enough overlapping data between {sym1} and {sym2} ({len(common)} points)")
        return

    xs = [p1[d] for d in common]
    ys = [p2[d] for d in common]
    n = len(xs)
    mx, my = sum(xs)/n, sum(ys)/n
    cov = sum((xs[i]-mx)*(ys[i]-my) for i in range(n)) / n
    sx = math.sqrt(sum((x-mx)**2 for x in xs)/n)
    sy = math.sqrt(sum((y-my)**2 for y in ys)/n)
    corr = cov / (sx * sy) if sx > 0 and sy > 0 else 0

    strength = 'strong' if abs(corr) > 0.7 else 'moderate' if abs(corr) > 0.3 else 'weak'
    direction = 'positive' if corr > 0 else 'negative'

    print(f"\n  {sym1} vs {sym2} Correlation ({days}-day, {n} observations):")
    print(f"  Pearson r: {corr:.4f}  ({strength} {direction})")
    if corr > 0.7:
        print(f"  → Strongly correlated — they tend to move together")
    elif corr < -0.7:
        print(f"  → Strongly inversely correlated — they tend to move opposite")
    elif abs(corr) < 0.3:
        print(f"  → Low correlation — relatively independent movements")


def handle_raw_sql(sql_query, args=None):
    """Raw SQL passthrough."""
    print_sql(sql_query)
    try:
        cols, rows = run_sql(sql_query)
        if not rows:
            print("  (empty result)")
            return cols, rows
        print_table(cols, rows)
        return cols, rows
    except Exception as e:
        print(f"  SQL Error: {e}")
        return [], []


# ─── Output modes ─────────────────────────────────────────────────────────────

def output_json(cols, rows):
    data = [dict(zip(cols, row)) for row in rows]
    print(json.dumps(data, indent=2, default=str))

def output_csv(cols, rows):
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(cols)
    w.writerows(rows)
    print(out.getvalue())

# ─── Main query router ────────────────────────────────────────────────────────

class Args:
    def __init__(self, query, json_mode=False, csv_mode=False, limit=10):
        self.query = query
        self.json_mode = json_mode
        self.csv_mode = csv_mode
        self.limit = limit

def route(args):
    q = args.query.strip()
    ql = q.lower()
    limit = args.limit

    # ── Raw SQL passthrough ──────────────────────────────────────────────
    if ql.startswith('sql ') or ql.startswith('select ') or ql.startswith('with '):
        sql_query = q[4:] if ql.startswith('sql ') else q
        if args.json_mode or args.csv_mode:
            cols, rows = run_sql(sql_query)
            if args.json_mode:
                output_json(cols, rows)
            else:
                output_csv(cols, rows)
        else:
            handle_raw_sql(sql_query, args)
        return

    # ── Meta queries ────────────────────────────────────────────────────
    if ql in ('status', 'db status', 'database status', 'db', 'health'):
        handle_status(args)
        return
    if ql in ('symbols', 'tickers', 'available symbols', 'list symbols'):
        handle_symbols(args)
        return
    if ql in ('series', 'fred series', 'economic series', 'list series'):
        handle_series(args)
        return

    # ── VIX term structure ──────────────────────────────────────────────
    if 'vix term' in ql or 'vix curve' in ql or 'vix term structure' in ql:
        handle_vix_term_structure(args)
        return

    # ── VIX standalone ──────────────────────────────────────────────────
    if re.match(r'^vix\s*$', ql) or ql == 'vix price' or ql == 'vix index':
        handle_vix(args)
        return

    # ── Yield curve ─────────────────────────────────────────────────────
    if 'yield curve' in ql or 'yield spread' in ql:
        handle_yield_curve(args)
        return

    # ── Oil ─────────────────────────────────────────────────────────────
    if ('oil price' in ql or ql in ('oil', 'crude', 'wti', 'wti crude', 'brent')) and 'options' not in ql:
        handle_oil(args)
        return

    # ── Fear & Greed ────────────────────────────────────────────────────
    if 'fear' in ql or 'greed' in ql:
        history = 'history' in ql or 'historical' in ql or 'last' in ql
        handle_fear_greed(history=history, limit=limit, args=args)
        return

    # ── Fed funds rate ──────────────────────────────────────────────────
    if 'fed funds' in ql or 'federal funds' in ql or 'ffr' in ql:
        history = 'history' in ql or 'historical' in ql
        handle_economic('FEDFUNDS', history=history, limit=limit, args=args)
        return

    # ── CPI ─────────────────────────────────────────────────────────────
    if 'cpi' in ql or ('inflation' in ql and 'rate' not in ql):
        history = 'history' in ql or 'historical' in ql or 'trend' in ql
        handle_economic('CPIAUCSL', history=history, limit=limit, args=args)
        return

    # ── Unemployment ────────────────────────────────────────────────────
    if 'unemployment' in ql:
        history = 'history' in ql
        handle_economic('UNRATE', history=history, limit=limit, args=args)
        return

    # ── Treasury rates ──────────────────────────────────────────────────
    for alias, series in [('10 year', 'DGS10'), ('10y', 'DGS10'), ('10yr', 'DGS10'), ('10-year', 'DGS10'),
                           ('2 year', 'DGS2'), ('2y', 'DGS2'), ('2yr', 'DGS2'),
                           ('5 year', 'DGS5'), ('5y', 'DGS5'),
                           ('30 year', 'DGS30'), ('30y', 'DGS30')]:
        if alias in ql and 'treasury' not in ql.replace(alias, '').replace('treasury', ''):
            pass
        if alias in ql or ('treasury' in ql and '10' in ql and series == 'DGS10'):
            history = 'history' in ql or 'historical' in ql
            handle_economic(series, history=history, limit=limit, args=args)
            return
    if 'treasury' in ql and not any(x in ql for x in ['2y','5y','10y','30y','2 year','5 year','10 year','30 year']):
        handle_economic('DGS10', history='history' in ql, limit=limit, args=args)
        return

    # ── Best/worst performers ────────────────────────────────────────────
    if 'best performer' in ql or 'top performer' in ql:
        days = extract_period(ql) or 7
        handle_best_worst(best=True, days=days, limit=limit, args=args)
        return
    if 'worst performer' in ql or 'bottom performer' in ql:
        days = extract_period(ql) or 30
        handle_best_worst(best=False, days=days, limit=limit, args=args)
        return

    # ── Multi-symbol correlation / comparison ────────────────────────────
    syms = extract_symbols(ql)
    # Crypto/stock correlation shorthand
    if ('correlation' in ql or 'corr' in ql) and ('crypto' in ql or 'stock' in ql or 'equity' in ql):
        handle_correlation('BTC', 'SPY', days=30, args=args)
        return

    if len(syms) >= 2 and ('vs' in ql or 'versus' in ql or 'compare' in ql or 'correlation' in ql or 'corr' in ql):
        sym1, sym2 = syms[0], syms[1]
        days = extract_period(ql) or 365
        if 'correlation' in ql or 'corr' in ql:
            handle_correlation(sym1, sym2, days=days, args=args)
        else:
            handle_comparison(sym1, sym2, days=days, limit=limit, args=args)
        return

    # ── Single symbol operations ─────────────────────────────────────────
    if not syms:
        # Try to pull a FRED series directly
        upper = q.upper().split()
        for w in upper:
            if w in FRED_SERIES:
                history = 'history' in ql or 'historical' in ql
                handle_economic(w, history=history, limit=limit, args=args)
                return
        print(f"  Could not parse query: '{q}'")
        print("  Try: 'symbols', 'status', 'BTC price', 'SPY last 30 days', 'fear and greed', 'yield curve'")
        print("  Or prefix with 'sql ' for raw SQL.")
        return

    sym = syms[0]

    # ── On-chain ─────────────────────────────────────────────────────────
    if 'on chain' in ql or 'onchain' in ql or 'on-chain' in ql:
        handle_onchain(sym, args=args)
        return
    if 'hash rate' in ql or 'hashrate' in ql:
        handle_onchain(sym, metric_filter='hash_rate', limit=limit, args=args)
        return
    if 'mvrv' in ql:
        handle_onchain(sym, metric_filter='mvrv', limit=limit, args=args)
        return
    if any(m in ql for m in ['active address', 'transactions', 'mempool', 'miners']):
        metric = None
        if 'active address' in ql: metric = 'active_addresses'
        elif 'mempool' in ql: metric = 'mempool'
        elif 'miners' in ql: metric = 'miners'
        elif 'transactions' in ql or 'tx' in ql: metric = 'n_tx'
        handle_onchain(sym, metric_filter=metric, limit=limit, args=args)
        return

    # ── Max pain ─────────────────────────────────────────────────────────
    if 'max pain' in ql or 'maxpain' in ql:
        handle_max_pain(sym, args=args)
        return

    # ── Put/call ratio ────────────────────────────────────────────────────
    if 'put call' in ql or 'put/call' in ql or 'pc ratio' in ql or 'pcr' in ql:
        handle_pcr(sym, args=args)
        return

    # ── Options OI ────────────────────────────────────────────────────────
    if 'options' in ql and ('oi' in ql or 'open interest' in ql or 'openinterest' in ql):
        handle_options_oi(sym, limit=limit, args=args)
        return

    # ── Funding rates ─────────────────────────────────────────────────────
    if 'funding' in ql:
        handle_funding_rates(symbol=sym, limit=limit, args=args)
        return

    # ── Return / performance ──────────────────────────────────────────────
    if 'return' in ql or 'performance' in ql or 'gain' in ql or 'loss' in ql:
        days = extract_period(ql) or 30
        handle_return(sym, days=days, args=args)
        return

    # ── Drawdown ──────────────────────────────────────────────────────────
    if 'drawdown' in ql or 'draw down' in ql or 'from peak' in ql or 'from ath' in ql:
        handle_drawdown(sym, args=args)
        return

    # ── FRED economic data for recognized series ──────────────────────────
    if sym in FRED_SERIES:
        history = 'history' in ql or 'historical' in ql or 'trend' in ql
        start_ts, end_ts = extract_dates(q)
        days = extract_period(ql)
        if start_ts and end_ts:
            handle_price(sym, start_ts=start_ts, end_ts=end_ts, limit=limit, args=args)
        elif days:
            handle_price(sym, days=days, limit=limit, args=args)
        else:
            handle_economic(sym, history=history, limit=limit, args=args)
        return

    # ── Price / time series ────────────────────────────────────────────────
    start_ts, end_ts = extract_dates(q)
    days = extract_period(ql)
    ytd = is_ytd(ql)

    if start_ts and end_ts:
        handle_price(sym, start_ts=start_ts, end_ts=end_ts, limit=limit, args=args)
    elif days:
        handle_price(sym, days=days, limit=limit, args=args)
    elif ytd:
        handle_price(sym, limit=limit, args=args)
    else:
        # Default: latest price
        handle_price(sym, limit=limit, args=args)


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        sys.exit(0)

    json_mode = '--json' in argv
    csv_mode = '--csv' in argv
    limit = 10
    for i, a in enumerate(argv):
        if a == '--limit' and i + 1 < len(argv):
            try:
                limit = int(argv[i + 1])
            except ValueError:
                pass

    # Remove flags
    query_parts = [a for a in argv if not a.startswith('--') and not (a.isdigit() and i > 0 and argv[i-1] == '--limit')]
    # Also remove the limit value
    clean_parts = []
    skip_next = False
    for a in argv:
        if skip_next:
            skip_next = False
            continue
        if a == '--limit':
            skip_next = True
            continue
        if a in ('--json', '--csv'):
            continue
        clean_parts.append(a)

    query = ' '.join(clean_parts)
    if not query:
        print("  No query provided. Try: python3 query.py 'BTC price'")
        sys.exit(1)

    args = Args(query=query, json_mode=json_mode, csv_mode=csv_mode, limit=limit)

    if not os.path.exists(DB_PATH):
        print(f"  Error: database not found at {DB_PATH}")
        sys.exit(1)

    print(f"\n  Query: \"{query}\"")
    route(args)
    print()


if __name__ == '__main__':
    main()


# ─── Example outputs (for documentation) ─────────────────────────────────────
#
# $ python3 query.py "BTC price"
#   Query: "BTC price"
#   SQL: SELECT timestamp, open, high, low, close, volume FROM prices WHERE symbol='BTC' ORDER BY timestamp DESC LIMIT 2
#   BTC: $70,865.00 (+0.79%) @ 2026-03-11 17:05
#   Open: $70,308.00  High: $70,890.40  Low: $70,100.00  Vol: 1,234
#
# $ python3 query.py "fear and greed"
#   Query: "fear and greed"
#   SQL: SELECT timestamp, indicator, value, label FROM sentiment WHERE indicator='fear_greed_crypto' ORDER BY timestamp DESC LIMIT 1
#   Fear & Greed Index (fear_greed_crypto): 15 — Extreme Fear 😱 @ 2026-03-11
#
# $ python3 query.py "yield curve"
#   Yield Curve (latest readings):
#   2Y (DGS2):  4.05% @ 2026-03-09
#   5Y (DGS5):  4.10% @ 2026-03-09
#   10Y (DGS10): 4.12% @ 2026-03-09
#   30Y (DGS30): 4.50% @ 2026-03-09
#   2Y-10Y Spread: +0.07% (normal)
#
# $ python3 query.py "status"
#   📊 Pinch Market Database Status
#   prices              125,038 rows  1990-01-02 → 2026-03-11 (33 unique symbols)
#   economic_data        69,217 rows  2000-01-01 → 2026-03-10 (16 unique series_ids)
#   ...
