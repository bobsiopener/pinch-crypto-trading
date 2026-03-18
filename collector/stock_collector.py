"""
Stock & Options Collector — Pinch Market Data
Collects daily OHLCV and options chains via yfinance.
Rule of Acquisition #74: Knowledge equals profit.

Usage:
    python3 stock_collector.py all
    python3 stock_collector.py prices
    python3 stock_collector.py options
"""

import sqlite3
import os
import sys
import time
import json
import logging

import yfinance as yf

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DB_PATH = os.environ.get("PINCH_DB", "/mnt/media/market_data/pinch_market.db")

# Import symbol lists from central config (auto-picks up new additions)
sys.path.insert(0, os.path.dirname(__file__))
import config as cfg

STOCK_SYMBOLS  = cfg.STOCK_SYMBOLS
STOCK_OPTIONS  = cfg.STOCK_OPTIONS

# ETFs / commodity trackers → 'etf'; everything else → 'stock'
ETF_SET = {
    'SPY', 'QQQ', 'IWM', 'GLD', 'TLT', 'XLE',
    'XLK', 'XLF', 'XLV', 'XBI', 'ARKK', 'SMH',
    'EEM', 'FXI', 'EWJ', 'HYG', 'LQD', 'SHY',
    'SLV', 'USO', 'UNG', 'COPX',
}

MAX_EXPIRATIONS = 4   # only fetch the next N expiries per symbol
DELAY_BETWEEN   = 1   # seconds between symbols

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
    """Create tables from main schema if they don't already exist."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS prices (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp   INTEGER NOT NULL,
        symbol      TEXT NOT NULL,
        asset_class TEXT NOT NULL,
        source      TEXT NOT NULL,
        timeframe   TEXT NOT NULL DEFAULT '1d',
        open        REAL,
        high        REAL,
        low         REAL,
        close       REAL,
        volume      REAL,
        UNIQUE(timestamp, symbol, source, timeframe)
    );
    CREATE INDEX IF NOT EXISTS idx_prices_symbol_ts ON prices(symbol, timestamp);

    CREATE TABLE IF NOT EXISTS options_chain (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp       INTEGER NOT NULL,
        symbol          TEXT NOT NULL,
        asset_class     TEXT NOT NULL,
        source          TEXT NOT NULL,
        expiry          TEXT NOT NULL,
        strike          REAL NOT NULL,
        option_type     TEXT NOT NULL,
        open_interest   REAL,
        volume          REAL,
        bid             REAL,
        ask             REAL,
        last_price      REAL,
        mark_price      REAL,
        implied_volatility REAL,
        delta           REAL,
        gamma           REAL,
        theta           REAL,
        vega            REAL,
        underlying_price REAL,
        UNIQUE(timestamp, symbol, source, expiry, strike, option_type)
    );
    CREATE INDEX IF NOT EXISTS idx_options_symbol_ts ON options_chain(symbol, timestamp);
    CREATE INDEX IF NOT EXISTS idx_options_expiry    ON options_chain(symbol, expiry, strike);

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


# ---------------------------------------------------------------------------
# Max Pain
# ---------------------------------------------------------------------------

def calculate_max_pain(calls_df, puts_df) -> float | None:
    """Return the strike price that minimises total dollar pain."""
    try:
        import pandas as pd
        strikes = sorted(set(calls_df['strike'].dropna().tolist() + puts_df['strike'].dropna().tolist()))
        if not strikes:
            return None

        call_oi = {row['strike']: row.get('openInterest', 0) or 0 for _, row in calls_df.iterrows()}
        put_oi  = {row['strike']: row.get('openInterest', 0) or 0 for _, row in puts_df.iterrows()}

        min_pain   = float('inf')
        max_pain_s = None
        for settlement in strikes:
            pain = 0.0
            for s in strikes:
                call_loss = max(0.0, settlement - s) * call_oi.get(s, 0)
                put_loss  = max(0.0, s - settlement) * put_oi.get(s, 0)
                pain += call_loss + put_loss
            if pain < min_pain:
                min_pain   = pain
                max_pain_s = settlement
        return max_pain_s
    except Exception as e:
        log.warning(f"max_pain calc failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Collectors
# ---------------------------------------------------------------------------

def collect_stock_prices() -> int:
    """Collect daily OHLCV for all STOCK_SYMBOLS."""
    conn  = get_conn()
    t0    = time.time()
    total = 0
    now   = int(time.time())

    print(f"[prices] Collecting {len(STOCK_SYMBOLS)} symbols …")
    for symbol in STOCK_SYMBOLS:
        try:
            tk   = yf.Ticker(symbol)
            hist = tk.history(period='2d')   # 2d to ensure we get today's bar
            if hist.empty:
                print(f"  {symbol}: no data")
                time.sleep(DELAY_BETWEEN)
                continue

            row = hist.iloc[-1]
            ts  = int(row.name.timestamp()) if hasattr(row.name, 'timestamp') else now
            asset_class = 'etf' if symbol in ETF_SET else 'stock'

            rec = {
                'timestamp': ts,
                'symbol':    symbol,
                'asset_class': asset_class,
                'source':    'yahoo',
                'timeframe': '1d',
                'open':   float(row.get('Open',  0) or 0),
                'high':   float(row.get('High',  0) or 0),
                'low':    float(row.get('Low',   0) or 0),
                'close':  float(row.get('Close', 0) or 0),
                'volume': float(row.get('Volume',0) or 0),
            }
            n = _insert_many_ignore(conn, 'prices', [rec])
            total += n
            print(f"  {symbol}: close={rec['close']:.2f}  +{n} row(s)")
        except Exception as e:
            log.error(f"  {symbol}: ERROR {e}")
        time.sleep(DELAY_BETWEEN)

    # VIX index — special handling (not a stock, uses ^VIX ticker)
    try:
        vix = yf.Ticker('^VIX')
        hist = vix.history(period='5d')
        if not hist.empty:
            for date, row in hist.iterrows():
                ts = int(date.timestamp())
                conn.execute("""INSERT OR IGNORE INTO prices
                    (symbol, asset_class, timeframe, timestamp, open, high, low, close, volume, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    ('VIX', 'index', '1d', ts,
                     float(row.get('Open', 0) or 0),
                     float(row.get('High', 0) or 0),
                     float(row.get('Low', 0) or 0),
                     float(row.get('Close', 0) or 0),
                     float(row.get('Volume', 0) or 0),
                     'yahoo'))
            conn.commit()
            total += len(hist)
            print(f"  VIX: {len(hist)} days updated")
        else:
            print("  VIX: no data")
    except Exception as e:
        print(f"  VIX failed: {e}")

    ms = int((time.time() - t0) * 1000)
    _log(conn, 'stock_prices', 'success', total, ms)
    print(f"[prices] Done — {total} rows in {ms}ms")
    conn.close()
    return total


def collect_stock_options() -> int:
    """Collect options chains (next 4 expirations) and compute max pain."""
    conn  = get_conn()
    t0    = time.time()
    total = 0
    now   = int(time.time())

    print(f"[options] Collecting {len(STOCK_OPTIONS)} symbols …")
    for symbol in STOCK_OPTIONS:
        try:
            tk = yf.Ticker(symbol)
            try:
                expirations = tk.options
            except Exception as e:
                print(f"  {symbol}: cannot fetch expirations: {e}")
                time.sleep(DELAY_BETWEEN)
                continue

            if not expirations:
                print(f"  {symbol}: no expirations")
                time.sleep(DELAY_BETWEEN)
                continue

            # Underlying price for context
            try:
                underlying_price = tk.fast_info.get('last_price') or tk.fast_info.get('regularMarketPrice')
                if not underlying_price:
                    h = tk.history(period='1d')
                    underlying_price = float(h['Close'].iloc[-1]) if not h.empty else None
            except Exception:
                underlying_price = None

            expirations = list(expirations)[:MAX_EXPIRATIONS]
            sym_rows = 0

            for expiry in expirations:
                try:
                    chain = tk.option_chain(expiry)
                    calls = chain.calls
                    puts  = chain.puts

                    # Max pain
                    mp = calculate_max_pain(calls, puts)
                    if mp is not None:
                        conn.execute(
                            "INSERT OR IGNORE INTO derived_metrics "
                            "(timestamp, symbol, source, metric, value, metadata) VALUES (?,?,?,?,?,?)",
                            (now, symbol, 'yahoo', f'max_pain_{expiry}', mp,
                             json.dumps({'expiry': expiry, 'underlying_price': underlying_price}))
                        )

                    # P/C ratios
                    c_vol = float(calls['volume'].sum()   or 0)
                    p_vol = float(puts['volume'].sum()    or 0)
                    c_oi  = float(calls['openInterest'].sum() or 0)
                    p_oi  = float(puts['openInterest'].sum()  or 0)
                    if c_vol > 0:
                        conn.execute(
                            "INSERT OR IGNORE INTO derived_metrics "
                            "(timestamp, symbol, source, metric, value, metadata) VALUES (?,?,?,?,?,?)",
                            (now, symbol, 'yahoo', f'pc_ratio_vol_{expiry}', round(p_vol / c_vol, 4),
                             json.dumps({'expiry': expiry}))
                        )
                    if c_oi > 0:
                        conn.execute(
                            "INSERT OR IGNORE INTO derived_metrics "
                            "(timestamp, symbol, source, metric, value, metadata) VALUES (?,?,?,?,?,?)",
                            (now, symbol, 'yahoo', f'pc_ratio_oi_{expiry}', round(p_oi / c_oi, 4),
                             json.dumps({'expiry': expiry}))
                        )
                    conn.commit()

                    # Build options_chain rows
                    rows = []
                    for _, r in calls.iterrows():
                        rows.append({
                            'timestamp': now,
                            'symbol':    symbol,
                            'asset_class': 'etf' if symbol in ETF_SET else 'stock',
                            'source':    'yahoo',
                            'expiry':    expiry,
                            'strike':    float(r.get('strike', 0) or 0),
                            'option_type': 'C',
                            'open_interest':   float(r.get('openInterest', 0) or 0),
                            'volume':          float(r.get('volume', 0) or 0),
                            'bid':             float(r.get('bid', 0) or 0),
                            'ask':             float(r.get('ask', 0) or 0),
                            'last_price':      float(r.get('lastPrice', 0) or 0),
                            'mark_price':      None,
                            'implied_volatility': float(r.get('impliedVolatility', 0) or 0),
                            'delta': None, 'gamma': None, 'theta': None, 'vega': None,
                            'underlying_price': underlying_price,
                        })
                    for _, r in puts.iterrows():
                        rows.append({
                            'timestamp': now,
                            'symbol':    symbol,
                            'asset_class': 'etf' if symbol in ETF_SET else 'stock',
                            'source':    'yahoo',
                            'expiry':    expiry,
                            'strike':    float(r.get('strike', 0) or 0),
                            'option_type': 'P',
                            'open_interest':   float(r.get('openInterest', 0) or 0),
                            'volume':          float(r.get('volume', 0) or 0),
                            'bid':             float(r.get('bid', 0) or 0),
                            'ask':             float(r.get('ask', 0) or 0),
                            'last_price':      float(r.get('lastPrice', 0) or 0),
                            'mark_price':      None,
                            'implied_volatility': float(r.get('impliedVolatility', 0) or 0),
                            'delta': None, 'gamma': None, 'theta': None, 'vega': None,
                            'underlying_price': underlying_price,
                        })

                    n = _insert_many_ignore(conn, 'options_chain', rows)
                    sym_rows += n
                    print(f"  {symbol} {expiry}: {len(calls)}C/{len(puts)}P → max_pain={mp}  +{n} rows")
                    time.sleep(0.3)  # gentle between expirations

                except Exception as e:
                    log.error(f"  {symbol} {expiry}: ERROR {e}")

            total += sym_rows
        except Exception as e:
            log.error(f"  {symbol}: FATAL {e}")
        time.sleep(DELAY_BETWEEN)

    ms = int((time.time() - t0) * 1000)
    _log(conn, 'stock_options', 'success', total, ms)
    print(f"[options] Done — {total} rows in {ms}ms")
    conn.close()
    return total


def collect_all_stocks() -> int:
    p = collect_stock_prices()
    o = collect_stock_options()
    return p + o


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else 'all'
    if cmd == 'prices':
        collect_stock_prices()
    elif cmd == 'options':
        collect_stock_options()
    elif cmd == 'all':
        collect_all_stocks()
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: python3 stock_collector.py [all|prices|options]")
        sys.exit(1)
