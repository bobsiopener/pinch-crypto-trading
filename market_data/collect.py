#!/usr/bin/env python3
"""
Pinch Market Data Collector — Main Runner
Rule of Acquisition #22: A wise man can hear profit in the wind.

Usage:
    python3 collect.py all       — run all collectors
    python3 collect.py crypto    — crypto prices + options + funding
    python3 collect.py stocks    — stock prices (yfinance handled separately)
    python3 collect.py macro     — FRED + VIX + sentiment
    python3 collect.py status    — show DB stats
    python3 collect.py backup    — backup DB

Only stdlib used here (urllib, sqlite3, json, time, datetime, gzip, os, sys).
Stock collector with yfinance lives in collector/stocks.py (separate).
"""

import sys
import os
import json
import time
import gzip
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone

# Ensure collector package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collector.db import MarketDB
from collector import config

# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def now_ts():
    """Current time as unix seconds (UTC)."""
    return int(time.time())


def fetch_json(url, retries=config.MAX_RETRIES, delay=config.RETRY_DELAY,
               timeout=config.REQUEST_TIMEOUT):
    """
    Fetch JSON from URL with retry logic.
    Returns parsed JSON or raises on final failure.
    """
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'PinchBot/1.0'})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            last_err = e
            if attempt < retries:
                print(f"  ⚠ Attempt {attempt}/{retries} failed: {e} — retrying in {delay}s")
                time.sleep(delay)
    raise last_err


def day_ts(date_str):
    """Convert 'YYYY-MM-DD' string to unix timestamp (midnight UTC)."""
    dt = datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


# ---------------------------------------------------------------------------
# Crypto collector
# ---------------------------------------------------------------------------

def collect_crypto(db):
    """Collect crypto prices from Kraken + Binance, funding rates from Binance."""
    print("\n💰 [CRYPTO] Starting crypto price collection...")
    start = time.time()
    total = 0

    # --- Kraken daily OHLCV ---
    print("  📊 Kraken OHLCV...")
    rows = []
    for symbol, pair in config.KRAKEN_PAIRS.items():
        try:
            url = f"{config.KRAKEN_BASE}/OHLC?pair={pair}&interval=1440"
            data = fetch_json(url)
            if data.get('error'):
                print(f"    ⚠ Kraken error for {symbol}: {data['error']}")
                continue
            result = data.get('result', {})
            ohlc_list = result.get(pair) or result.get(list(result.keys())[0], [])
            for bar in ohlc_list[-30:]:  # last 30 daily bars
                ts, o, h, l, c, vwap, vol, count = (bar + [None]*8)[:8]
                rows.append({
                    'timestamp': int(ts),
                    'symbol': symbol,
                    'asset_class': 'crypto',
                    'source': 'kraken',
                    'timeframe': '1d',
                    'open': float(o),
                    'high': float(h),
                    'low': float(l),
                    'close': float(c),
                    'volume': float(vol),
                })
        except Exception as e:
            print(f"    ✗ Kraken {symbol}: {e}")

    n = db.insert_many('prices', rows)
    total += n
    print(f"    ✓ Inserted {n} Kraken price bars")

    # --- Binance spot prices (current) ---
    print("  📊 Binance spot prices...")
    rows = []
    ts = now_ts()
    # Round to nearest hour for consistent timestamps
    ts = (ts // 3600) * 3600
    try:
        url = f"{config.BINANCE_BASE}/ticker/price"
        tickers = fetch_json(url)
        ticker_map = {t['symbol']: float(t['price']) for t in tickers}
        for symbol, pair in config.BINANCE_PAIRS.items():
            price = ticker_map.get(pair)
            if price:
                rows.append({
                    'timestamp': ts,
                    'symbol': symbol,
                    'asset_class': 'crypto',
                    'source': 'binance',
                    'timeframe': '1h',
                    'open': price,
                    'high': price,
                    'low': price,
                    'close': price,
                    'volume': None,
                })
    except Exception as e:
        print(f"    ✗ Binance spot: {e}")

    n = db.insert_many('prices', rows)
    total += n
    print(f"    ✓ Inserted {n} Binance spot prices")

    # --- Binance funding rates ---
    print("  💸 Binance funding rates...")
    rows = []
    try:
        url = "https://fapi.binance.com/fapi/v1/fundingRate?limit=1"
        # Get latest for each perp
        for symbol, pair in config.BINANCE_PAIRS.items():
            try:
                furl = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={pair}PERP&limit=1"
                # Try without PERP suffix first
                furl2 = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={pair}&limit=1"
                try:
                    data = fetch_json(furl2, retries=2)
                except Exception:
                    continue
                if data and isinstance(data, list):
                    for entry in data:
                        rows.append({
                            'timestamp': int(int(entry['fundingTime']) / 1000),
                            'symbol': symbol,
                            'exchange': 'binance',
                            'rate': float(entry['fundingRate']),
                        })
            except Exception as e:
                pass  # Funding not available for all pairs
    except Exception as e:
        print(f"    ✗ Binance funding: {e}")

    if rows:
        n = db.insert_many('funding_rates', rows)
        total += n
        print(f"    ✓ Inserted {n} funding rate records")
    else:
        print("    ℹ No funding rate data collected")

    # --- CoinGecko market data (supplemental) ---
    print("  🦎 CoinGecko market data...")
    try:
        ids = ','.join(config.COINGECKO_IDS.values())
        url = (f"{config.COINGECKO_BASE}/simple/price"
               f"?ids={ids}&vs_currencies=usd"
               f"&include_market_cap=true&include_24hr_vol=true&include_24hr_change=true")
        data = fetch_json(url)
        rows = []
        ts = (now_ts() // 3600) * 3600
        for symbol, cg_id in config.COINGECKO_IDS.items():
            if cg_id in data:
                d = data[cg_id]
                price = d.get('usd')
                if price:
                    rows.append({
                        'timestamp': ts,
                        'symbol': symbol,
                        'asset_class': 'crypto',
                        'source': 'coingecko',
                        'timeframe': '1h',
                        'open': price,
                        'high': price,
                        'low': price,
                        'close': price,
                        'volume': d.get('usd_24h_vol'),
                    })
                    # Also store market cap as a derived metric
                    mc = d.get('usd_market_cap')
                    if mc:
                        db.insert_metric(ts, symbol, 'coingecko', 'market_cap', mc)
                        total += 1
        n = db.insert_many('prices', rows)
        total += n
        print(f"    ✓ Inserted {n} CoinGecko prices")
    except Exception as e:
        print(f"    ✗ CoinGecko: {e}")

    elapsed = int((time.time() - start) * 1000)
    db.log_collection('crypto', 'success', total, elapsed)
    print(f"  ✅ Crypto done — {total} records in {elapsed}ms")
    return total


# ---------------------------------------------------------------------------
# Macro collector
# ---------------------------------------------------------------------------

def collect_macro(db):
    """Collect FRED economic data, VIX, and sentiment (Fear & Greed)."""
    print("\n📈 [MACRO] Starting macro/sentiment collection...")
    start = time.time()
    total = 0

    # --- Fear & Greed (Crypto) via alternative.me ---
    print("  😱 Crypto Fear & Greed Index...")
    try:
        data = fetch_json(f"{config.ALTERNATIVE_ME}?limit=7")
        rows = []
        for entry in data.get('data', []):
            ts = int(entry['timestamp'])
            rows.append({
                'timestamp': ts,
                'indicator': 'fear_greed_crypto',
                'source': 'alternative.me',
                'value': float(entry['value']),
                'label': entry.get('value_classification'),
                'metadata': None,
            })
        n = db.insert_many('sentiment', rows)
        total += n
        print(f"    ✓ Inserted {n} Fear & Greed records")
    except Exception as e:
        print(f"    ✗ Fear & Greed: {e}")

    # --- FRED economic data ---
    print("  🏛️ FRED economic data...")
    fred_api_key = os.environ.get('FRED_API_KEY', '')
    if not fred_api_key:
        print("    ⚠ FRED_API_KEY not set — skipping FRED data")
        print("    ℹ Set FRED_API_KEY env var to enable (free at fred.stlouisfed.org)")
    else:
        fred_rows = []
        for series_id, description in config.FRED_SERIES.items():
            try:
                params = urllib.parse.urlencode({
                    'series_id': series_id,
                    'api_key': fred_api_key,
                    'file_type': 'json',
                    'sort_order': 'desc',
                    'limit': 30,
                })
                url = f"{config.FRED_BASE}?{params}"
                data = fetch_json(url)
                for obs in data.get('observations', []):
                    val_str = obs.get('value', '.')
                    if val_str == '.':
                        continue  # missing data
                    try:
                        value = float(val_str)
                    except ValueError:
                        continue
                    ts = day_ts(obs['date'])
                    fred_rows.append({
                        'timestamp': ts,
                        'series_id': series_id,
                        'source': 'fred',
                        'value': value,
                    })
                print(f"    ✓ {series_id}: {description}")
            except Exception as e:
                print(f"    ✗ FRED {series_id}: {e}")

        if fred_rows:
            n = db.insert_many('economic_data', fred_rows)
            total += n
            print(f"    ✓ Inserted {n} FRED economic records")

    # --- VIX via CBOE (public data) ---
    print("  📉 VIX data...")
    try:
        # CBOE publishes VIX history as CSV
        vix_url = 'https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv'
        req = urllib.request.Request(vix_url, headers={'User-Agent': 'PinchBot/1.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            lines = resp.read().decode('utf-8').strip().splitlines()

        rows = []
        # CSV: DATE,OPEN,HIGH,LOW,CLOSE
        for line in lines[-30:]:  # last 30 trading days
            parts = line.split(',')
            if len(parts) < 5 or parts[0] == 'DATE':
                continue
            try:
                date_str = parts[0].strip()
                # Try MM/DD/YYYY format
                try:
                    dt = datetime.strptime(date_str, '%m/%d/%Y')
                except ValueError:
                    dt = datetime.strptime(date_str, '%Y-%m-%d')
                ts = int(dt.replace(tzinfo=timezone.utc).timestamp())
                o, h, l, c = [float(x) for x in parts[1:5]]
                rows.append({
                    'timestamp': ts,
                    'symbol': 'VIX',
                    'asset_class': 'index',
                    'source': 'cboe',
                    'timeframe': '1d',
                    'open': o,
                    'high': h,
                    'low': l,
                    'close': c,
                    'volume': None,
                })
            except Exception:
                continue

        n = db.insert_many('prices', rows)
        total += n
        print(f"    ✓ Inserted {n} VIX price records")
    except Exception as e:
        print(f"    ✗ VIX: {e}")

    # --- Bitcoin on-chain (Blockchain.info) ---
    print("  ⛓️ BTC on-chain metrics...")
    onchain_endpoints = {
        'hash_rate':         f"{config.BLOCKCHAIN_INFO}/q/hashrate",
        'total_bitcoins':    f"{config.BLOCKCHAIN_INFO}/q/totalbc",
        'market_cap_usd':    f"{config.BLOCKCHAIN_INFO}/q/marketcap",
        'trade_volume_usd':  f"{config.BLOCKCHAIN_INFO}/q/tradeVolume",
        'mempool_size':      f"{config.MEMPOOL_SPACE}/mempool",
    }
    ts = (now_ts() // 86400) * 86400  # round to day

    for metric, url in onchain_endpoints.items():
        try:
            if metric == 'mempool_size':
                data = fetch_json(url)
                value = data.get('count', 0)
            else:
                req = urllib.request.Request(url, headers={'User-Agent': 'PinchBot/1.0'})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    value = float(resp.read().decode('utf-8').strip())
            db.insert_onchain(ts, 'BTC', metric, 'blockchain.info', value)
            total += 1
            print(f"    ✓ BTC {metric}: {value:,.2f}")
        except Exception as e:
            print(f"    ✗ BTC {metric}: {e}")

    elapsed = int((time.time() - start) * 1000)
    db.log_collection('macro', 'success', total, elapsed)
    print(f"  ✅ Macro done — {total} records in {elapsed}ms")
    return total


# ---------------------------------------------------------------------------
# Stocks collector (lightweight — yfinance version is stocks.py)
# ---------------------------------------------------------------------------

def collect_stocks(db):
    """
    Collect stock prices using yfinance if available,
    otherwise print instructions and skip.
    """
    print("\n📉 [STOCKS] Starting stock collection...")
    try:
        import yfinance as yf
        print("  ✓ yfinance available")
    except ImportError:
        print("  ⚠ yfinance not installed.")
        print("    Install with: pip3 install yfinance")
        print("    Or run the full stock collector: python3 collector/stocks.py")
        db.log_collection('stocks', 'error', 0, 0,
                          'yfinance not installed; run collector/stocks.py')
        return 0

    start = time.time()
    total = 0
    rows = []

    all_symbols = config.STOCK_SYMBOLS

    print(f"  📊 Fetching {len(all_symbols)} symbols from Yahoo Finance...")
    for symbol in all_symbols:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='30d', interval='1d')
            if hist.empty:
                print(f"    ⚠ No data for {symbol}")
                continue

            # Determine asset class
            if symbol in ('SPY', 'QQQ', 'IWM', 'GLD', 'TLT', 'XLE'):
                ac = 'etf'
            else:
                ac = 'stock'

            for dt, row in hist.iterrows():
                ts = int(dt.timestamp())
                rows.append({
                    'timestamp': ts,
                    'symbol': symbol,
                    'asset_class': ac,
                    'source': 'yahoo',
                    'timeframe': '1d',
                    'open': float(row['Open']),
                    'high': float(row['High']),
                    'low': float(row['Low']),
                    'close': float(row['Close']),
                    'volume': float(row['Volume']),
                })
        except Exception as e:
            print(f"    ✗ {symbol}: {e}")

    if rows:
        n = db.insert_many('prices', rows)
        total += n
        print(f"  ✓ Inserted {n} stock price bars")

    elapsed = int((time.time() - start) * 1000)
    db.log_collection('stocks', 'success', total, elapsed)
    print(f"  ✅ Stocks done — {total} records in {elapsed}ms")
    return total


# ---------------------------------------------------------------------------
# Status display
# ---------------------------------------------------------------------------

def show_status(db):
    """Print DB stats — row counts, size, last collection times."""
    stats = db.stats()

    print("\n" + "=" * 60)
    print("💰 PINCH MARKET DATA — DATABASE STATUS")
    print("=" * 60)

    # DB size
    size_bytes = stats['db_size_bytes']
    size_mb = size_bytes / (1024 * 1024)
    print(f"\n📦 Database: {db.db_path}")
    print(f"   Size: {size_mb:.2f} MB ({size_bytes:,} bytes)")

    # Row counts
    print("\n📊 Table Row Counts:")
    counts = stats['row_counts']
    max_name = max(len(t) for t in counts)
    for table, count in sorted(counts.items(), key=lambda x: -x[1]):
        bar_len = min(40, count // max(1, max(counts.values()) // 40))
        bar = '█' * bar_len
        print(f"   {table:<{max_name}}  {count:>10,}  {bar}")

    # Last collections
    print("\n🕐 Last Collection Times:")
    last = stats['last_collections']
    if last:
        for collector, info in sorted(last.items()):
            ts = info['last_ts']
            status = info['status']
            if ts:
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                ago = int(time.time()) - ts
                if ago < 3600:
                    ago_str = f"{ago // 60}m ago"
                elif ago < 86400:
                    ago_str = f"{ago // 3600}h ago"
                else:
                    ago_str = f"{ago // 86400}d ago"
                icon = '✅' if status == 'success' else ('⚠️' if status == 'partial' else '❌')
                print(f"   {icon} {collector:<15} {dt.strftime('%Y-%m-%d %H:%M UTC')}  ({ago_str})  [{status}]")
    else:
        print("   No collections logged yet.")

    print("\n" + "=" * 60)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == 'status':
        with MarketDB() as db:
            show_status(db)
        return

    if cmd == 'backup':
        print("💾 Creating database backup...")
        with MarketDB() as db:
            path = db.backup()
        size = os.path.getsize(path) / (1024 * 1024)
        print(f"✅ Backup saved: {path} ({size:.2f} MB)")
        return

    if cmd not in ('all', 'crypto', 'stocks', 'macro'):
        print(f"Unknown command: {cmd}")
        print("Valid commands: all, crypto, stocks, macro, status, backup")
        sys.exit(1)

    print(f"🚀 Pinch Market Collector — {cmd.upper()}")
    print(f"   Started: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")

    with MarketDB() as db:
        grand_total = 0

        if cmd in ('all', 'crypto'):
            try:
                grand_total += collect_crypto(db)
            except Exception as e:
                print(f"❌ Crypto collector failed: {e}")
                db.log_collection('crypto', 'error', 0, 0, str(e))

        if cmd in ('all', 'macro'):
            try:
                grand_total += collect_macro(db)
            except Exception as e:
                print(f"❌ Macro collector failed: {e}")
                db.log_collection('macro', 'error', 0, 0, str(e))

        if cmd in ('all', 'stocks'):
            try:
                grand_total += collect_stocks(db)
            except Exception as e:
                print(f"❌ Stocks collector failed: {e}")
                db.log_collection('stocks', 'error', 0, 0, str(e))

        print(f"\n🏁 Collection complete — {grand_total} total records inserted")
        print(f"   Rule of Acquisition #22: A wise man can hear profit in the wind.")
        show_status(db)


if __name__ == '__main__':
    main()
