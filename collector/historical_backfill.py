#!/usr/bin/env python3
"""
Pinch Market Data — Historical Backfill
Rule of Acquisition #74: Knowledge equals profit.

Downloads ALL available free historical data and stores in pinch_market.db.
Safe to run multiple times — uses INSERT OR IGNORE throughout.

Usage:
    python3 historical_backfill.py all         # run everything
    python3 historical_backfill.py stocks      # stock prices only
    python3 historical_backfill.py crypto      # crypto prices (yfinance + kraken)
    python3 historical_backfill.py fred        # FRED economic data
    python3 historical_backfill.py onchain     # BTC on-chain metrics
    python3 historical_backfill.py sentiment   # Fear & Greed index
    python3 historical_backfill.py status      # show backfill status
"""

import sys
import os
import time
import datetime
import requests

# Add parent dir for imports
sys.path.insert(0, os.path.dirname(__file__))
from db import MarketDB
import config as cfg

# ---------------------------------------------------------------------------
# Symbol definitions — sourced from config.py for automatic updates
# ---------------------------------------------------------------------------

# Classify equities from config: symbols with '-' are typically ETF shares
# (BRK-B), everything in ETF_BASE_LIST is an ETF, rest are stocks
ETF_BASE_LIST = {'SPY', 'QQQ', 'IWM', 'GLD', 'TLT', 'XLE',
                 'XLK', 'XLF', 'XLV', 'XBI', 'ARKK', 'SMH',
                 'EEM', 'FXI', 'EWJ', 'HYG', 'LQD', 'SHY',
                 'SLV', 'USO', 'UNG', 'COPX'}

def _classify_equity(symbol):
    if symbol in ETF_BASE_LIST:
        return 'etf'
    return 'stock'

ALL_EQUITY_SYMBOLS = cfg.STOCK_SYMBOLS  # includes both stocks and ETFs

# yfinance crypto tickers — special-case mappings for coins not listed as SYMBOL-USD
CRYPTO_YF_OVERRIDES = {
    'ARB': 'ARB11841-USD',  # Arbitrum token ID on yfinance
}

def _crypto_yf_ticker(symbol):
    return CRYPTO_YF_OVERRIDES.get(symbol, f'{symbol}-USD')

CRYPTO_YF = [_crypto_yf_ticker(s) for s in cfg.CRYPTO_SYMBOLS]

# Kraken pair -> our clean symbol
KRAKEN_PAIRS = {
    'XBTUSD':   'BTC',
    'XETHZUSD': 'ETH',
    'SOLUSD':   'SOL',
}

# Use FRED series from config (authoritative list)
FRED_SERIES = cfg.FRED_SERIES

BLOCKCHAIN_CHARTS = {
    'hash-rate':                       'hash_rate',
    'n-transactions':                  'n_transactions',
    'difficulty':                      'difficulty',
    'market-cap':                      'market_cap',
    'estimated-transaction-volume-usd':'tx_volume_usd',
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now():
    return datetime.datetime.utcnow().strftime('%H:%M:%S')


def _yf_symbol_to_clean(yf_sym):
    """'BTC-USD' -> 'BTC', 'ARB11841-USD' -> 'ARB' (reverse override lookup)"""
    # Reverse-lookup from CRYPTO_YF_OVERRIDES
    for sym, ticker in CRYPTO_YF_OVERRIDES.items():
        if ticker == yf_sym:
            return sym
    return yf_sym.split('-')[0]


def _date_to_ts(date_str):
    """'2023-01-15' -> unix int"""
    dt = datetime.datetime.strptime(date_str, '%Y-%m-%d')
    return int(dt.replace(tzinfo=datetime.timezone.utc).timestamp())


def _http_get(url, params=None, timeout=30, retries=3, backoff=2):
    """GET with retry/backoff. Returns response or raises."""
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
# 1 & 5. Stock / ETF / Index prices (yfinance)
# ---------------------------------------------------------------------------

def backfill_stocks(db: MarketDB):
    """Download daily stock/ETF/VIX prices via yfinance."""
    try:
        import yfinance as yf
    except ImportError:
        print("ERROR: yfinance not installed. Run: pip install yfinance")
        return

    # Build full list: equities + VIX index
    jobs = []
    for sym in ALL_EQUITY_SYMBOLS:
        jobs.append((sym, _classify_equity(sym), '2010-01-01'))
    jobs.append(('^VIX', 'index', '1990-01-01'))

    total_inserted = 0
    for yf_sym, asset_class, start_date in jobs:
        clean_sym = yf_sym.lstrip('^')  # ^VIX -> VIX
        t0 = time.time()
        print(f"[{_now()}] Backfilling {yf_sym} daily... ", end='', flush=True)
        try:
            df = yf.download(yf_sym, start=start_date, interval='1d',
                             auto_adjust=True, progress=False)
            if df.empty:
                print("no data.")
                db.log_collection(f'backfill_stocks_{clean_sym}', 'warning', 0, 0,
                                  'empty response')
                continue

            rows = []
            for idx, row in df.iterrows():
                try:
                    ts = int(idx.timestamp())
                except Exception:
                    ts = int(idx.value // 1_000_000_000)

                # yfinance may return multi-level columns with auto_adjust
                def _val(col):
                    if hasattr(df.columns, 'levels'):
                        # MultiIndex
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
                    import math
                    if isinstance(v, float) and math.isnan(v):
                        return None
                    return float(v)

                rows.append({
                    'timestamp':   ts,
                    'symbol':      clean_sym,
                    'asset_class': asset_class,
                    'source':      'yahoo',
                    'timeframe':   '1d',
                    'open':        _val('Open'),
                    'high':        _val('High'),
                    'low':         _val('Low'),
                    'close':       _val('Close'),
                    'volume':      _val('Volume'),
                })

            inserted = db.insert_many('prices', rows)
            elapsed = time.time() - t0
            end_date = df.index[-1].strftime('%Y-%m-%d') if not df.empty else '?'
            print(f"{start_date} to {end_date}... {inserted:,} rows ({elapsed:.1f}s)")
            db.log_collection(f'backfill_stocks_{clean_sym}', 'ok', inserted,
                              int(elapsed * 1000))
            total_inserted += inserted
        except Exception as e:
            elapsed = time.time() - t0
            print(f"ERROR: {e}")
            db.log_collection(f'backfill_stocks_{clean_sym}', 'error', 0,
                              int(elapsed * 1000), str(e))

    print(f"\n  ✓ Stock/ETF/Index backfill complete. Total rows: {total_inserted:,}\n")
    return total_inserted


# ---------------------------------------------------------------------------
# 2. Crypto prices (yfinance)
# ---------------------------------------------------------------------------

def backfill_crypto_yf(db: MarketDB):
    """Download daily crypto prices via yfinance."""
    try:
        import yfinance as yf
    except ImportError:
        print("ERROR: yfinance not installed.")
        return

    total_inserted = 0
    for yf_sym in CRYPTO_YF:
        clean_sym = _yf_symbol_to_clean(yf_sym)
        t0 = time.time()
        print(f"[{_now()}] Backfilling {yf_sym} daily (crypto)... ", end='', flush=True)
        try:
            df = yf.download(yf_sym, start='2014-01-01', interval='1d',
                             auto_adjust=True, progress=False)
            if df.empty:
                print("no data.")
                db.log_collection(f'backfill_crypto_yf_{clean_sym}', 'warning', 0, 0,
                                  'empty response')
                continue

            rows = []
            for idx, row in df.iterrows():
                try:
                    ts = int(idx.timestamp())
                except Exception:
                    ts = int(idx.value // 1_000_000_000)

                def _val(col):
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
                    import math
                    if isinstance(v, float) and math.isnan(v):
                        return None
                    return float(v)

                rows.append({
                    'timestamp':   ts,
                    'symbol':      clean_sym,
                    'asset_class': 'crypto',
                    'source':      'yahoo',
                    'timeframe':   '1d',
                    'open':        _val('Open'),
                    'high':        _val('High'),
                    'low':         _val('Low'),
                    'close':       _val('Close'),
                    'volume':      _val('Volume'),
                })

            inserted = db.insert_many('prices', rows)
            elapsed = time.time() - t0
            end_date = df.index[-1].strftime('%Y-%m-%d') if not df.empty else '?'
            print(f"2014-01-01 to {end_date}... {inserted:,} rows ({elapsed:.1f}s)")
            db.log_collection(f'backfill_crypto_yf_{clean_sym}', 'ok', inserted,
                              int(elapsed * 1000))
            total_inserted += inserted
        except Exception as e:
            elapsed = time.time() - t0
            print(f"ERROR: {e}")
            db.log_collection(f'backfill_crypto_yf_{clean_sym}', 'error', 0,
                              int(elapsed * 1000), str(e))

    print(f"\n  ✓ Crypto yfinance backfill complete. Total rows: {total_inserted:,}\n")
    return total_inserted


# ---------------------------------------------------------------------------
# 3. Crypto prices — Kraken 1h OHLCV
# ---------------------------------------------------------------------------

def backfill_kraken(db: MarketDB):
    """
    Paginate Kraken's public OHLC endpoint to get 1-hour candles back as far
    as possible. Each call returns up to 720 candles; paginate via 'last'.
    Rate limit: 1 request/second (conservative).
    """
    KRAKEN_OHLC = 'https://api.kraken.com/0/public/OHLC'
    CANDLES_PER_PAGE = 720

    total_inserted = 0

    for pair, symbol in KRAKEN_PAIRS.items():
        print(f"[{_now()}] Backfilling {pair} 1h (Kraken)...")
        t0 = time.time()
        since = 0
        page = 0
        all_rows = []
        first_ts = None
        last_ts = None

        try:
            while True:
                page += 1
                r = _http_get(KRAKEN_OHLC,
                              params={'pair': pair, 'interval': 60, 'since': since},
                              timeout=30)
                data = r.json()

                if data.get('error'):
                    print(f"  Kraken error: {data['error']}")
                    break

                result = data.get('result', {})
                # The OHLC data key may be the pair name or a variant
                ohlc_key = pair
                if ohlc_key not in result:
                    # try to find it
                    ohlc_key = next((k for k in result if k != 'last'), None)
                if not ohlc_key:
                    print(f"  No OHLC key in response. Keys: {list(result.keys())}")
                    break

                candles = result[ohlc_key]
                new_last = result.get('last', 0)

                if not candles:
                    break

                for c in candles:
                    # [time, open, high, low, close, vwap, volume, count]
                    ts   = int(c[0])
                    o    = float(c[1])
                    h    = float(c[2])
                    lo   = float(c[3])
                    cl   = float(c[4])
                    vol  = float(c[6])
                    all_rows.append({
                        'timestamp':   ts,
                        'symbol':      symbol,
                        'asset_class': 'crypto',
                        'source':      'kraken',
                        'timeframe':   '1h',
                        'open':        o,
                        'high':        h,
                        'low':         lo,
                        'close':       cl,
                        'volume':      vol,
                    })
                    if first_ts is None or ts < first_ts:
                        first_ts = ts
                    if last_ts is None or ts > last_ts:
                        last_ts = ts

                candles_so_far = len(all_rows)
                est_pages = max(page, int(page * CANDLES_PER_PAGE / max(candles_so_far, 1) * 40))
                print(f"  {pair} 1h: page {page}/~{est_pages}, "
                      f"{candles_so_far:,} candles so far...", flush=True)

                # If we got fewer than a full page, we're done
                if len(candles) < CANDLES_PER_PAGE:
                    break

                # If last didn't advance, we're done
                if new_last <= since:
                    break

                since = new_last
                time.sleep(1.0)  # respect rate limit

            # Bulk insert
            if all_rows:
                inserted = db.insert_many('prices', all_rows)
                elapsed = time.time() - t0
                start_str = datetime.datetime.utcfromtimestamp(first_ts).strftime('%Y-%m-%d') if first_ts else '?'
                end_str   = datetime.datetime.utcfromtimestamp(last_ts).strftime('%Y-%m-%d') if last_ts else '?'
                print(f"  ✓ {pair}: {start_str} to {end_str} → {inserted:,} rows inserted ({elapsed:.1f}s)")
                db.log_collection(f'backfill_kraken_{symbol}', 'ok', inserted,
                                  int(elapsed * 1000))
                total_inserted += inserted
            else:
                print(f"  {pair}: no data returned")
                db.log_collection(f'backfill_kraken_{symbol}', 'warning', 0, 0, 'no data')

        except Exception as e:
            elapsed = time.time() - t0
            print(f"  ERROR on {pair}: {e}")
            db.log_collection(f'backfill_kraken_{symbol}', 'error', 0,
                              int(elapsed * 1000), str(e))

    print(f"\n  ✓ Kraken 1h backfill complete. Total rows: {total_inserted:,}\n")
    return total_inserted


# ---------------------------------------------------------------------------
# 4. FRED Economic Data
# ---------------------------------------------------------------------------

def backfill_fred(db: MarketDB):
    """Download FRED economic series (requires FRED_API_KEY env var)."""
    api_key = os.environ.get('FRED_API_KEY', '')
    if not api_key:
        print("  [FRED] FRED_API_KEY not set — skipping FRED backfill.")
        print("  Set it with: export FRED_API_KEY=your_key")
        return 0

    FRED_URL = 'https://api.stlouisfed.org/fred/series/observations'
    total_inserted = 0

    for series_id, description in FRED_SERIES.items():
        t0 = time.time()
        print(f"[{_now()}] Backfilling FRED {series_id} ({description})... ",
              end='', flush=True)
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
                date_str = obs.get('date')
                val_str  = obs.get('value', '.')
                if val_str == '.' or not val_str:
                    continue  # missing value
                try:
                    value = float(val_str)
                    ts    = _date_to_ts(date_str)
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
            if rows:
                start = observations[0]['date']
                end   = observations[-1]['date']
            else:
                start = end = '?'
            print(f"{start} to {end}... {inserted:,} rows ({elapsed:.1f}s)")
            db.log_collection(f'backfill_fred_{series_id}', 'ok', inserted,
                              int(elapsed * 1000))
            total_inserted += inserted
            time.sleep(0.2)  # gentle rate limit

        except Exception as e:
            elapsed = time.time() - t0
            print(f"ERROR: {e}")
            db.log_collection(f'backfill_fred_{series_id}', 'error', 0,
                              int(elapsed * 1000), str(e))

    print(f"\n  ✓ FRED backfill complete. Total rows: {total_inserted:,}\n")
    return total_inserted


# ---------------------------------------------------------------------------
# 6. BTC On-Chain (blockchain.info)
# ---------------------------------------------------------------------------

def backfill_onchain(db: MarketDB):
    """Download BTC on-chain metrics from blockchain.info."""
    BASE = 'https://api.blockchain.info/charts'
    total_inserted = 0

    for chart_name, metric_key in BLOCKCHAIN_CHARTS.items():
        t0 = time.time()
        print(f"[{_now()}] Backfilling blockchain.info {chart_name}... ",
              end='', flush=True)
        try:
            r = _http_get(f'{BASE}/{chart_name}',
                          params={'timespan': 'all', 'format': 'json'},
                          timeout=60)
            data = r.json()
            values = data.get('values', [])

            rows = []
            for point in values:
                ts  = int(point['x'])
                val = float(point['y'])
                rows.append({
                    'timestamp': ts,
                    'symbol':    'BTC',
                    'metric':    metric_key,
                    'source':    'blockchain_info',
                    'value':     val,
                    'metadata':  None,
                })

            inserted = db.insert_many('onchain_metrics', rows)
            elapsed = time.time() - t0
            if values:
                start = datetime.datetime.utcfromtimestamp(values[0]['x']).strftime('%Y-%m-%d')
                end   = datetime.datetime.utcfromtimestamp(values[-1]['x']).strftime('%Y-%m-%d')
            else:
                start = end = '?'
            print(f"{start} to {end}... {inserted:,} rows ({elapsed:.1f}s)")
            db.log_collection(f'backfill_onchain_{metric_key}', 'ok', inserted,
                              int(elapsed * 1000))
            total_inserted += inserted
            time.sleep(1.0)  # be nice to blockchain.info

        except Exception as e:
            elapsed = time.time() - t0
            print(f"ERROR: {e}")
            db.log_collection(f'backfill_onchain_{metric_key}', 'error', 0,
                              int(elapsed * 1000), str(e))

    print(f"\n  ✓ On-chain backfill complete. Total rows: {total_inserted:,}\n")
    return total_inserted


# ---------------------------------------------------------------------------
# 7. Crypto Fear & Greed (alternative.me)
# ---------------------------------------------------------------------------

def backfill_sentiment(db: MarketDB):
    """Download all historical Fear & Greed data from alternative.me."""
    URL = 'https://api.alternative.me/fng/'
    t0  = time.time()
    print(f"[{_now()}] Backfilling Fear & Greed index (all history)... ",
          end='', flush=True)
    try:
        r    = _http_get(URL, params={'limit': 0}, timeout=60)
        data = r.json()
        entries = data.get('data', [])

        rows = []
        for entry in entries:
            ts    = int(entry['timestamp'])
            value = float(entry['value'])
            label = entry.get('value_classification', '')
            rows.append({
                'timestamp': ts,
                'indicator': 'fear_greed',
                'source':    'alternative_me',
                'value':     value,
                'label':     label,
                'metadata':  None,
            })

        inserted = db.insert_many('sentiment', rows)
        elapsed  = time.time() - t0
        if rows:
            dates = sorted(r['timestamp'] for r in rows)
            start = datetime.datetime.utcfromtimestamp(dates[0]).strftime('%Y-%m-%d')
            end   = datetime.datetime.utcfromtimestamp(dates[-1]).strftime('%Y-%m-%d')
        else:
            start = end = '?'
        print(f"{start} to {end}... {inserted:,} rows ({elapsed:.1f}s)")
        db.log_collection('backfill_sentiment_fng', 'ok', inserted,
                          int(elapsed * 1000))
        print(f"\n  ✓ Sentiment backfill complete. Total rows: {inserted:,}\n")
        return inserted

    except Exception as e:
        elapsed = time.time() - t0
        print(f"ERROR: {e}")
        db.log_collection('backfill_sentiment_fng', 'error', 0,
                          int(elapsed * 1000), str(e))
        return 0


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def show_status(db: MarketDB):
    """Show date ranges and row counts per table/symbol."""
    print("\n" + "=" * 70)
    print("  BACKFILL STATUS")
    print("=" * 70)

    # Prices table — per symbol/timeframe
    print("\n📈 PRICES TABLE")
    rows = db.query("""
        SELECT symbol, asset_class, source, timeframe,
               COUNT(*) as rows,
               MIN(timestamp) as first_ts,
               MAX(timestamp) as last_ts
        FROM prices
        GROUP BY symbol, asset_class, source, timeframe
        ORDER BY asset_class, symbol, timeframe
    """)
    if rows:
        print(f"  {'Symbol':<10} {'Class':<8} {'Source':<8} {'TF':<4} "
              f"{'Rows':>8}  {'First':<12} {'Last':<12}")
        print(f"  {'-'*10} {'-'*8} {'-'*8} {'-'*4} {'-'*8}  {'-'*12} {'-'*12}")
        for r in rows:
            first = datetime.datetime.utcfromtimestamp(r['first_ts']).strftime('%Y-%m-%d') if r['first_ts'] else '?'
            last  = datetime.datetime.utcfromtimestamp(r['last_ts']).strftime('%Y-%m-%d') if r['last_ts'] else '?'
            print(f"  {r['symbol']:<10} {r['asset_class']:<8} {r['source']:<8} "
                  f"{r['timeframe']:<4} {r['rows']:>8,}  {first:<12} {last:<12}")
    else:
        print("  (no data)")

    # Economic data
    print("\n📊 ECONOMIC DATA TABLE")
    rows = db.query("""
        SELECT series_id, COUNT(*) as rows,
               MIN(timestamp) as first_ts,
               MAX(timestamp) as last_ts
        FROM economic_data
        GROUP BY series_id
        ORDER BY series_id
    """)
    if rows:
        print(f"  {'Series':<28} {'Rows':>8}  {'First':<12} {'Last':<12}")
        print(f"  {'-'*28} {'-'*8}  {'-'*12} {'-'*12}")
        for r in rows:
            first = datetime.datetime.utcfromtimestamp(r['first_ts']).strftime('%Y-%m-%d') if r['first_ts'] else '?'
            last  = datetime.datetime.utcfromtimestamp(r['last_ts']).strftime('%Y-%m-%d') if r['last_ts'] else '?'
            print(f"  {r['series_id']:<28} {r['rows']:>8,}  {first:<12} {last:<12}")
    else:
        print("  (no data)")

    # On-chain
    print("\n⛓️  ON-CHAIN METRICS TABLE")
    rows = db.query("""
        SELECT metric, COUNT(*) as rows,
               MIN(timestamp) as first_ts,
               MAX(timestamp) as last_ts
        FROM onchain_metrics
        GROUP BY metric
        ORDER BY metric
    """)
    if rows:
        print(f"  {'Metric':<32} {'Rows':>8}  {'First':<12} {'Last':<12}")
        print(f"  {'-'*32} {'-'*8}  {'-'*12} {'-'*12}")
        for r in rows:
            first = datetime.datetime.utcfromtimestamp(r['first_ts']).strftime('%Y-%m-%d') if r['first_ts'] else '?'
            last  = datetime.datetime.utcfromtimestamp(r['last_ts']).strftime('%Y-%m-%d') if r['last_ts'] else '?'
            print(f"  {r['metric']:<32} {r['rows']:>8,}  {first:<12} {last:<12}")
    else:
        print("  (no data)")

    # Sentiment
    print("\n😱 SENTIMENT TABLE")
    rows = db.query("""
        SELECT indicator, source, COUNT(*) as rows,
               MIN(timestamp) as first_ts,
               MAX(timestamp) as last_ts
        FROM sentiment
        GROUP BY indicator, source
        ORDER BY indicator
    """)
    if rows:
        print(f"  {'Indicator':<20} {'Source':<16} {'Rows':>8}  {'First':<12} {'Last':<12}")
        print(f"  {'-'*20} {'-'*16} {'-'*8}  {'-'*12} {'-'*12}")
        for r in rows:
            first = datetime.datetime.utcfromtimestamp(r['first_ts']).strftime('%Y-%m-%d') if r['first_ts'] else '?'
            last  = datetime.datetime.utcfromtimestamp(r['last_ts']).strftime('%Y-%m-%d') if r['last_ts'] else '?'
            print(f"  {r['indicator']:<20} {r['source']:<16} {r['rows']:>8,}  {first:<12} {last:<12}")
    else:
        print("  (no data)")

    # DB size
    from db import DB_PATH
    size = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
    print(f"\n💾 DB size: {size / 1024 / 1024:.1f} MB")
    print("=" * 70 + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else 'help'

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║       Pinch Historical Backfill — Rule of Acquisition #74   ║
║              "Knowledge equals profit."                      ║
╚══════════════════════════════════════════════════════════════╝
  Command: {cmd}
  Time:    {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
""")

    if cmd == 'help':
        print(__doc__)
        return

    db = MarketDB()
    grand_total = 0

    try:
        if cmd == 'status':
            show_status(db)

        elif cmd == 'stocks':
            grand_total += backfill_stocks(db) or 0

        elif cmd == 'crypto':
            grand_total += backfill_crypto_yf(db) or 0
            grand_total += backfill_kraken(db) or 0

        elif cmd == 'fred':
            grand_total += backfill_fred(db) or 0

        elif cmd == 'onchain':
            grand_total += backfill_onchain(db) or 0

        elif cmd == 'sentiment':
            grand_total += backfill_sentiment(db) or 0

        elif cmd == 'all':
            print("━" * 60)
            print("PHASE 1: Stock & ETF & VIX prices (yfinance)")
            print("━" * 60)
            grand_total += backfill_stocks(db) or 0

            print("━" * 60)
            print("PHASE 2: Crypto daily prices (yfinance)")
            print("━" * 60)
            grand_total += backfill_crypto_yf(db) or 0

            print("━" * 60)
            print("PHASE 3: Crypto 1h OHLCV (Kraken — may take 10-20 min)")
            print("━" * 60)
            grand_total += backfill_kraken(db) or 0

            print("━" * 60)
            print("PHASE 4: FRED Economic Data")
            print("━" * 60)
            grand_total += backfill_fred(db) or 0

            print("━" * 60)
            print("PHASE 5: BTC On-Chain (blockchain.info)")
            print("━" * 60)
            grand_total += backfill_onchain(db) or 0

            print("━" * 60)
            print("PHASE 6: Crypto Fear & Greed (alternative.me)")
            print("━" * 60)
            grand_total += backfill_sentiment(db) or 0

            print("\n" + "═" * 60)
            print(f"  ALL PHASES COMPLETE  —  {grand_total:,} total rows inserted")
            print("═" * 60)
            show_status(db)

        else:
            print(f"Unknown command: {cmd}")
            print(__doc__)

    finally:
        db.close()


if __name__ == '__main__':
    main()
