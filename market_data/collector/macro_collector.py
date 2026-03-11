"""
Macro & Economic Data Collector — Pinch Market Data
Collects FRED series, VIX term structure, and put/call ratio.
Rule of Acquisition #22: A wise man can hear profit in the wind.

Usage:
    python3 macro_collector.py all
    python3 macro_collector.py fred
    python3 macro_collector.py vix
    python3 macro_collector.py pcr
"""

import sqlite3
import os
import sys
import time
import json
import logging
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

import yfinance as yf

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DB_PATH = os.environ.get("PINCH_DB", "/mnt/media/market_data/pinch_market.db")

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

FRED_SERIES = {
    'DGS2':               '2-Year Treasury',
    'DGS5':               '5-Year Treasury',
    'DGS10':              '10-Year Treasury',
    'DGS30':              '30-Year Treasury',
    'T10Y2Y':             '10Y-2Y Spread',
    'VIXCLS':             'VIX',
    'UNRATE':             'Unemployment Rate',
    'CPIAUCSL':           'CPI All Items',
    'PCEPI':              'PCE Price Index',
    'FEDFUNDS':           'Fed Funds Rate',
    'M2SL':               'M2 Money Supply',
    'ICSA':               'Initial Jobless Claims',
    'UMCSENT':            'Consumer Sentiment',
    'DCOILWTICO':         'WTI Crude Oil',
    'DCOILBRENTEU':       'Brent Crude',
    'GOLDPMGBD228NLBM':   'Gold London PM Fix',
    'DHHNGSP':            'Natural Gas Henry Hub',
    'BAMLH0A0HYM2':       'HY OAS Spread',
}

VIX_TICKERS = ['^VIX', '^VIX3M', '^VIX6M']

DELAY_BETWEEN = 0.5   # seconds between FRED requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_conn() -> sqlite3.Connection:
    db_path = os.path.abspath(DB_PATH)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    _ensure_tables(conn)
    return conn


def _ensure_tables(conn: sqlite3.Connection):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS economic_data (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp   INTEGER NOT NULL,
        series_id   TEXT NOT NULL,
        source      TEXT NOT NULL DEFAULT 'fred',
        value       REAL,
        UNIQUE(timestamp, series_id, source)
    );
    CREATE INDEX IF NOT EXISTS idx_econ_series ON economic_data(series_id, timestamp);

    CREATE TABLE IF NOT EXISTS vix_term_structure (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp       INTEGER NOT NULL,
        expiry          TEXT NOT NULL,
        vix_value       REAL,
        days_to_expiry  INTEGER,
        UNIQUE(timestamp, expiry)
    );

    CREATE TABLE IF NOT EXISTS derived_metrics (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp   INTEGER NOT NULL,
        symbol      TEXT NOT NULL,
        source      TEXT NOT NULL,
        metric      TEXT NOT NULL,
        value       REAL,
        metadata    TEXT,
        UNIQUE(timestamp, symbol, source, metric)
    );
    CREATE INDEX IF NOT EXISTS idx_derived_symbol_metric ON derived_metrics(symbol, metric, timestamp);

    CREATE TABLE IF NOT EXISTS collection_log (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp       INTEGER NOT NULL,
        collector       TEXT NOT NULL,
        status          TEXT NOT NULL,
        records_inserted INTEGER,
        duration_ms     INTEGER,
        error_msg       TEXT
    );
    """)
    conn.commit()


def _insert_many_ignore(conn: sqlite3.Connection, table: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    cols = list(rows[0].keys())
    ph   = ",".join(["?"] * len(cols))
    sql  = f"INSERT OR IGNORE INTO {table} ({','.join(cols)}) VALUES ({ph})"
    data = [[r.get(c) for c in cols] for r in rows]
    conn.executemany(sql, data)
    conn.commit()
    return len(rows)


def _log(conn: sqlite3.Connection, collector: str, status: str,
         records: int = 0, duration_ms: int = 0, error: str = ""):
    try:
        conn.execute(
            "INSERT INTO collection_log (timestamp, collector, status, records_inserted, duration_ms, error_msg) "
            "VALUES (?,?,?,?,?,?)",
            (int(time.time()), collector, status, records, duration_ms, error or None)
        )
        conn.commit()
    except Exception as e:
        log.warning(f"Failed to write collection_log: {e}")


def _fetch_url(url: str, timeout: int = 20) -> dict:
    req = urllib.request.Request(url, headers={'User-Agent': 'Pinch/1.0'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


# ---------------------------------------------------------------------------
# FRED
# ---------------------------------------------------------------------------

def collect_fred() -> int:
    api_key = os.environ.get("FRED_API_KEY", "").strip()
    if not api_key:
        print("[fred] No FRED_API_KEY set.")
        print("       Get a free key at https://fred.stlouisfed.org/docs/api/api_key.html")
        print("       Then: export FRED_API_KEY=your_key_here")
        return 0

    conn  = get_conn()
    t0    = time.time()
    total = 0

    print(f"[fred] Fetching {len(FRED_SERIES)} series …")
    for series_id, desc in FRED_SERIES.items():
        try:
            params = urllib.parse.urlencode({
                'series_id':  series_id,
                'api_key':    api_key,
                'file_type':  'json',
                'sort_order': 'desc',
                'limit':      5,
            })
            data = _fetch_url(f"{FRED_BASE}?{params}")
            obs  = data.get('observations', [])

            rows = []
            for o in obs:
                if o.get('value') in ('.', '', None):
                    continue
                try:
                    val = float(o['value'])
                except (ValueError, TypeError):
                    continue
                # FRED dates are YYYY-MM-DD; convert to unix timestamp (midnight UTC)
                try:
                    dt = datetime.strptime(o['date'], '%Y-%m-%d').replace(tzinfo=timezone.utc)
                    ts = int(dt.timestamp())
                except Exception:
                    ts = int(time.time())
                rows.append({
                    'timestamp': ts,
                    'series_id': series_id,
                    'source':    'fred',
                    'value':     val,
                })

            n = _insert_many_ignore(conn, 'economic_data', rows)
            total += n
            latest_val = rows[0]['value'] if rows else None
            print(f"  {series_id} ({desc}): latest={latest_val}  +{n} row(s)")
        except Exception as e:
            log.error(f"  {series_id}: ERROR {e}")
        time.sleep(DELAY_BETWEEN)

    ms = int((time.time() - t0) * 1000)
    _log(conn, 'macro_fred', 'success', total, ms)
    print(f"[fred] Done — {total} rows in {ms}ms")
    conn.close()
    return total


# ---------------------------------------------------------------------------
# VIX Term Structure
# ---------------------------------------------------------------------------

def collect_vix() -> int:
    conn  = get_conn()
    t0    = time.time()
    total = 0
    now   = int(time.time())
    today = datetime.now(timezone.utc).date()

    print(f"[vix] Fetching VIX term structure …")
    for ticker in VIX_TICKERS:
        try:
            tk   = yf.Ticker(ticker)
            hist = tk.history(period='2d')
            if hist.empty:
                print(f"  {ticker}: no data")
                continue

            close = float(hist['Close'].iloc[-1])

            # Determine expiry label from ticker
            if ticker == '^VIX':
                label = 'spot'
                dte   = 30
            elif ticker == '^VIX3M':
                label = '3m'
                dte   = 90
            elif ticker == '^VIX6M':
                label = '6m'
                dte   = 180
            else:
                label = ticker.lstrip('^').lower()
                dte   = None

            row = {
                'timestamp':      now,
                'expiry':         label,
                'vix_value':      close,
                'days_to_expiry': dte,
            }
            n = _insert_many_ignore(conn, 'vix_term_structure', [row])
            total += n
            print(f"  {ticker}: {close:.2f}  +{n} row(s)")

            # Also store in derived_metrics for easy querying
            conn.execute(
                "INSERT OR IGNORE INTO derived_metrics "
                "(timestamp, symbol, source, metric, value) VALUES (?,?,?,?,?)",
                (now, 'VIX', 'yahoo', f'vix_{label}', close)
            )
            conn.commit()
        except Exception as e:
            log.error(f"  {ticker}: ERROR {e}")
        time.sleep(1)

    ms = int((time.time() - t0) * 1000)
    _log(conn, 'macro_vix', 'success', total, ms)
    print(f"[vix] Done — {total} rows in {ms}ms")
    conn.close()
    return total


# ---------------------------------------------------------------------------
# Put/Call Ratio
# ---------------------------------------------------------------------------

def collect_cboe_pcr() -> int:
    """
    Attempt CBOE equity P/C ratio via their public data endpoint.
    Falls back to computing an aggregate from the options_chain table.
    """
    conn  = get_conn()
    t0    = time.time()
    total = 0
    now   = int(time.time())

    # --- Attempt 1: CBOE public data (they publish CSV) ---
    cboe_url = "https://www.cboe.com/us/options/market_statistics/daily/"
    equity_pcr = None
    try:
        # CBOE doesn't have a clean JSON API; try their historical data endpoint
        csv_url = "https://www.cboe.com/trading/volatility/volatility-indexes/volatility-history/cboe-equity-put-call-ratio-epcr/"
        # Their actual data endpoint:
        data_url = "https://cdn.cboe.com/api/global/us_options_market/market_statistics/option_put_call_ratios.json"
        data = _fetch_url(data_url, timeout=15)
        # Parse whatever structure they return
        if isinstance(data, dict):
            for k, v in data.items():
                if 'equity' in k.lower() or 'eqty' in k.lower():
                    try:
                        equity_pcr = float(v)
                        print(f"  CBOE equity P/C: {equity_pcr} (live)")
                        break
                    except (ValueError, TypeError):
                        pass
    except Exception as e:
        log.info(f"  CBOE live fetch failed ({e}); falling back to DB calculation")

    # --- Attempt 2: Compute from our own options_chain table ---
    if equity_pcr is None:
        try:
            row = conn.execute("""
                SELECT
                    SUM(CASE WHEN option_type='P' THEN volume ELSE 0 END) AS pvol,
                    SUM(CASE WHEN option_type='C' THEN volume ELSE 0 END) AS cvol,
                    SUM(CASE WHEN option_type='P' THEN open_interest ELSE 0 END) AS poi,
                    SUM(CASE WHEN option_type='C' THEN open_interest ELSE 0 END) AS coi
                FROM options_chain
                WHERE source='yahoo'
                  AND timestamp >= ?
            """, (now - 86400,)).fetchone()

            if row and row[1] and row[1] > 0:
                pcr_vol = round(row[0] / row[1], 4)
                pcr_oi  = round(row[2] / row[3], 4) if row[3] and row[3] > 0 else None
                print(f"  Computed P/C ratio (vol): {pcr_vol}  (oi): {pcr_oi}")

                metrics = [
                    {'timestamp': now, 'symbol': 'MARKET', 'source': 'yahoo_calc',
                     'metric': 'pc_ratio_vol', 'value': pcr_vol, 'metadata': json.dumps({'basis': 'stock_options_chain'})},
                ]
                if pcr_oi is not None:
                    metrics.append(
                        {'timestamp': now, 'symbol': 'MARKET', 'source': 'yahoo_calc',
                         'metric': 'pc_ratio_oi', 'value': pcr_oi, 'metadata': json.dumps({'basis': 'stock_options_chain'})}
                    )
                n = _insert_many_ignore(conn, 'derived_metrics', metrics)
                total += n
            else:
                print("  No options_chain data available yet for P/C calculation.")
        except Exception as e:
            log.error(f"  P/C DB calculation failed: {e}")
    else:
        # Store CBOE result
        row = {'timestamp': now, 'symbol': 'MARKET', 'source': 'cboe',
               'metric': 'pc_ratio_equity', 'value': equity_pcr, 'metadata': None}
        n = _insert_many_ignore(conn, 'derived_metrics', [row])
        total += n

    ms = int((time.time() - t0) * 1000)
    _log(conn, 'macro_pcr', 'success', total, ms)
    print(f"[pcr] Done — {total} rows in {ms}ms")
    conn.close()
    return total


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

def collect_all_macro() -> int:
    f = collect_fred()
    v = collect_vix()
    p = collect_cboe_pcr()
    return f + v + p


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else 'all'
    if cmd == 'fred':
        collect_fred()
    elif cmd == 'vix':
        collect_vix()
    elif cmd in ('pcr', 'cboe'):
        collect_cboe_pcr()
    elif cmd == 'all':
        collect_all_macro()
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: python3 macro_collector.py [all|fred|vix|pcr]")
        sys.exit(1)
