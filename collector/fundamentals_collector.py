"""
Fundamentals Collector — Pinch Market Data
Weekly collection of P/E, P/B, EPS, and other fundamental metrics.
Stores in fundamentals table in the market DB.
Rule of Acquisition #74: Knowledge equals profit.

Usage:
    python3 fundamentals_collector.py
"""

import yfinance as yf
import sqlite3
import time
import os
import sys

DB_PATH = os.environ.get("PINCH_DB", "/mnt/media/market_data/pinch_market.db")

# Import symbol lists from central config
sys.path.insert(0, os.path.dirname(__file__))
import config as cfg

SYMBOLS = cfg.STOCK_SYMBOLS


def ensure_table(db):
    db.execute("""CREATE TABLE IF NOT EXISTS fundamentals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        timestamp INTEGER NOT NULL,
        pe_trailing REAL,
        pe_forward REAL,
        pb_ratio REAL,
        ps_ratio REAL,
        ev_ebitda REAL,
        market_cap REAL,
        revenue REAL,
        revenue_growth REAL,
        earnings_growth REAL,
        profit_margin REAL,
        roe REAL,
        debt_equity REAL,
        current_ratio REAL,
        dividend_yield REAL,
        payout_ratio REAL,
        fcf REAL,
        beta REAL,
        fifty_two_week_high REAL,
        fifty_two_week_low REAL,
        sector TEXT,
        industry TEXT,
        source TEXT DEFAULT 'yfinance',
        UNIQUE(symbol, timestamp)
    )""")
    db.commit()


def collect_fundamentals():
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    ensure_table(db)

    now = int(time.time())
    # Round to day boundary (midnight UTC)
    now_day = now - (now % 86400)

    collected = 0
    errors = 0

    print(f"[fund] Collecting fundamentals for {len(SYMBOLS)} symbols …")
    for sym in SYMBOLS:
        try:
            ticker = yf.Ticker(sym)
            info = ticker.info
            if not info or 'symbol' not in info:
                print(f"  {sym}: no data")
                errors += 1
                time.sleep(0.5)
                continue

            mcap = info.get('marketCap') or 0
            db.execute("""INSERT OR REPLACE INTO fundamentals
                (symbol, timestamp, pe_trailing, pe_forward, pb_ratio, ps_ratio,
                 ev_ebitda, market_cap, revenue, revenue_growth, earnings_growth,
                 profit_margin, roe, debt_equity, current_ratio, dividend_yield,
                 payout_ratio, fcf, beta, fifty_two_week_high, fifty_two_week_low,
                 sector, industry, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (sym, now_day,
                 info.get('trailingPE'),
                 info.get('forwardPE'),
                 info.get('priceToBook'),
                 info.get('priceToSalesTrailing12Months'),
                 info.get('enterpriseToEbitda'),
                 info.get('marketCap'),
                 info.get('totalRevenue'),
                 info.get('revenueGrowth'),
                 info.get('earningsGrowth'),
                 info.get('profitMargins'),
                 info.get('returnOnEquity'),
                 info.get('debtToEquity'),
                 info.get('currentRatio'),
                 info.get('dividendYield'),
                 info.get('payoutRatio'),
                 info.get('freeCashflow'),
                 info.get('beta'),
                 info.get('fiftyTwoWeekHigh'),
                 info.get('fiftyTwoWeekLow'),
                 info.get('sector'),
                 info.get('industry'),
                 'yfinance'))
            collected += 1
            pe = info.get('trailingPE', 'N/A')
            print(f"  {sym}: PE={pe}, MCap=${mcap/1e9:.1f}B")
            time.sleep(0.5)  # Rate limit
        except Exception as e:
            print(f"  {sym}: ERROR {e}")
            errors += 1
            time.sleep(0.5)

    db.commit()

    # Log to collection_log if it exists
    try:
        db.execute(
            "INSERT INTO collection_log (timestamp, collector, status, records_inserted, duration_ms, error_msg) "
            "VALUES (?,?,?,?,?,?)",
            (int(time.time()), 'fundamentals', 'success', collected, 0, None)
        )
        db.commit()
    except Exception:
        pass

    db.close()
    print(f"\n[fund] Done: {collected} collected, {errors} errors")
    return collected


if __name__ == '__main__':
    collect_fundamentals()
