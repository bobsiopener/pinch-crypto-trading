#!/usr/bin/env python3
"""
One-off backfill for newly added symbols.
Rule of Acquisition #74: Knowledge equals profit.

Backfills:
  - New crypto: SHIB, PEPE, WIF, UNI, AAVE, MKR, ARB, OP, MATIC
  - New stocks/ETFs: XLK, XLF, XLV, XBI, ARKK, SMH, EEM, FXI, EWJ,
                     HYG, LQD, SHY, SLV, USO, UNG, COPX
  - Missing FRED series from config.py
"""

import sys
import os
import time
import datetime
import math
import requests

sys.path.insert(0, '/mnt/media/market_data/collector')
from db import MarketDB
import config as cfg

DB_PATH = '/mnt/media/market_data/pinch_market.db'

# ---------------------------------------------------------------------------
# New symbols to backfill
# ---------------------------------------------------------------------------

# yfinance ticker -> (clean symbol, asset_class, start_date)
NEW_CRYPTO = [
    ('SHIB-USD',     'SHIB',  'crypto', '2017-01-01'),
    ('PEPE-USD',     'PEPE',  'crypto', '2017-01-01'),
    ('WIF-USD',      'WIF',   'crypto', '2017-01-01'),
    ('UNI-USD',      'UNI',   'crypto', '2017-01-01'),
    ('AAVE-USD',     'AAVE',  'crypto', '2017-01-01'),
    ('MKR-USD',      'MKR',   'crypto', '2017-01-01'),
    ('ARB11841-USD', 'ARB',   'crypto', '2017-01-01'),
    ('OP-USD',       'OP',    'crypto', '2017-01-01'),
    ('MATIC-USD',    'MATIC', 'crypto', '2017-01-01'),
]

NEW_STOCKS = [
    ('XLK',  'XLK',  'etf',   '2010-01-01'),
    ('XLF',  'XLF',  'etf',   '2010-01-01'),
    ('XLV',  'XLV',  'etf',   '2010-01-01'),
    ('XBI',  'XBI',  'etf',   '2010-01-01'),
    ('ARKK', 'ARKK', 'etf',   '2010-01-01'),
    ('SMH',  'SMH',  'etf',   '2010-01-01'),
    ('EEM',  'EEM',  'etf',   '2010-01-01'),
    ('FXI',  'FXI',  'etf',   '2010-01-01'),
    ('EWJ',  'EWJ',  'etf',   '2010-01-01'),
    ('HYG',  'HYG',  'etf',   '2010-01-01'),
    ('LQD',  'LQD',  'etf',   '2010-01-01'),
    ('SHY',  'SHY',  'etf',   '2010-01-01'),
    ('SLV',  'SLV',  'etf',   '2010-01-01'),
    ('USO',  'USO',  'etf',   '2010-01-01'),
    ('UNG',  'UNG',  'etf',   '2010-01-01'),
    ('COPX', 'COPX', 'etf',   '2010-01-01'),
]

# FRED series not yet in DB (from config.py)
MISSING_FRED = {
    'DTWEXBGS':          'Dollar Index (Broad)',
    'GDPC1':             'Real GDP',
    'GOLDPMGBD228NLBM':  'Gold Price (London PM Fix)',
    'TEDRATE':           'TED Spread',
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now():
    return datetime.datetime.utcnow().strftime('%H:%M:%S')


def _val(df, row, col, yf_sym):
    """Extract a float value from yfinance row, handling MultiIndex."""
    if hasattr(df.columns, 'levels'):
        try:
            v = row[(col, yf_sym)]
        except KeyError:
            try:
                v = row[col]
            except Exception:
                return None
    else:
        v = row.get(col)
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    return float(v)


def _date_to_ts(date_str):
    dt = datetime.datetime.strptime(date_str, '%Y-%m-%d')
    return int(dt.replace(tzinfo=datetime.timezone.utc).timestamp())


def _http_get(url, params=None, timeout=30, retries=3, backoff=2):
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            if r.status_code == 429:
                wait = int(r.headers.get('Retry-After', 60))
                print(f"  [rate limit] sleeping {wait}s...")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            if attempt < retries - 1:
                time.sleep(backoff * (attempt + 1))
            else:
                raise


# ---------------------------------------------------------------------------
# Backfill via yfinance
# ---------------------------------------------------------------------------

def backfill_yf(db, jobs):
    """jobs: list of (yf_ticker, clean_symbol, asset_class, start_date)"""
    try:
        import yfinance as yf
    except ImportError:
        print("ERROR: yfinance not installed.")
        return 0

    total = 0
    for yf_sym, clean_sym, asset_class, start_date in jobs:
        t0 = time.time()
        print(f"[{_now()}] Backfilling {yf_sym} ({asset_class})... ", end='', flush=True)
        try:
            df = yf.download(yf_sym, start=start_date, interval='1d',
                             auto_adjust=True, progress=False)
            if df.empty:
                print("no data.")
                db.log_collection(f'backfill_new_{clean_sym}', 'warning', 0, 0, 'empty')
                continue

            rows = []
            for idx, row in df.iterrows():
                try:
                    ts = int(idx.timestamp())
                except Exception:
                    ts = int(idx.value // 1_000_000_000)

                rows.append({
                    'timestamp':   ts,
                    'symbol':      clean_sym,
                    'asset_class': asset_class,
                    'source':      'yahoo',
                    'timeframe':   '1d',
                    'open':        _val(df, row, 'Open',   yf_sym),
                    'high':        _val(df, row, 'High',   yf_sym),
                    'low':         _val(df, row, 'Low',    yf_sym),
                    'close':       _val(df, row, 'Close',  yf_sym),
                    'volume':      _val(df, row, 'Volume', yf_sym),
                })

            inserted = db.insert_many('prices', rows)
            elapsed = time.time() - t0
            end_date = df.index[-1].strftime('%Y-%m-%d')
            print(f"{start_date} → {end_date}  {inserted:,} rows ({elapsed:.1f}s)")
            db.log_collection(f'backfill_new_{clean_sym}', 'ok', inserted,
                              int(elapsed * 1000))
            total += inserted
        except Exception as e:
            elapsed = time.time() - t0
            print(f"ERROR: {e}")
            db.log_collection(f'backfill_new_{clean_sym}', 'error', 0,
                              int(elapsed * 1000), str(e))

    return total


# ---------------------------------------------------------------------------
# Backfill missing FRED series
# ---------------------------------------------------------------------------

def backfill_fred_missing(db):
    api_key = os.environ.get('FRED_API_KEY', '')
    if not api_key:
        key_file = '/home/bob/.openclaw/workspace-pinch/.secrets/fred_api_key.txt'
        if os.path.exists(key_file):
            api_key = open(key_file).read().strip()
    if not api_key:
        print("  [FRED] No API key found — skipping missing FRED series.")
        return 0

    FRED_URL = cfg.FRED_BASE
    total = 0

    for series_id, description in MISSING_FRED.items():
        t0 = time.time()
        print(f"[{_now()}] FRED {series_id} ({description})... ", end='', flush=True)
        try:
            r = _http_get(FRED_URL, params={
                'series_id':         series_id,
                'api_key':           api_key,
                'file_type':         'json',
                'observation_start': '2000-01-01',
                'limit':             100000,
            })
            data = r.json()
            observations = data.get('observations', [])

            rows = []
            for obs in observations:
                val_str = obs.get('value', '.')
                if val_str == '.' or not val_str:
                    continue
                try:
                    value = float(val_str)
                    ts    = _date_to_ts(obs['date'])
                except (ValueError, TypeError):
                    continue
                rows.append({
                    'timestamp': ts,
                    'series_id': series_id,
                    'source':    'fred',
                    'value':     value,
                })

            inserted = db.insert_many('economic_data', rows)
            elapsed = time.time() - t0
            start = observations[0]['date'] if observations else '?'
            end   = observations[-1]['date'] if observations else '?'
            print(f"{start} → {end}  {inserted:,} rows ({elapsed:.1f}s)")
            db.log_collection(f'backfill_fred_{series_id}', 'ok', inserted,
                              int(elapsed * 1000))
            total += inserted
            time.sleep(0.2)
        except Exception as e:
            elapsed = time.time() - t0
            print(f"ERROR: {e}")
            db.log_collection(f'backfill_fred_{series_id}', 'error', 0,
                              int(elapsed * 1000), str(e))

    return total


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    print(f"""
╔══════════════════════════════════════════════════════════╗
║   Pinch — One-off New Symbol Backfill                   ║
║   Rule of Acquisition #74: Knowledge equals profit.     ║
╚══════════════════════════════════════════════════════════╝
  Time: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
""")

    db = MarketDB(DB_PATH)
    grand_total = 0

    print("━" * 60)
    print("NEW CRYPTO SYMBOLS (yfinance daily)")
    print("━" * 60)
    grand_total += backfill_yf(db, NEW_CRYPTO)

    print("\n" + "━" * 60)
    print("NEW STOCK/ETF SYMBOLS (yfinance daily)")
    print("━" * 60)
    grand_total += backfill_yf(db, NEW_STOCKS)

    print("\n" + "━" * 60)
    print("MISSING FRED SERIES")
    print("━" * 60)
    grand_total += backfill_fred_missing(db)

    print(f"\n  ✓ One-off backfill complete. Total new rows: {grand_total:,}")
    db.close()
