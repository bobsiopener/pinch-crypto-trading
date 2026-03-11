"""
Pinch Market Data — Database Helper
Rule of Acquisition #74: Knowledge equals profit.

All inserts use INSERT OR IGNORE for idempotent runs.
WAL mode enabled for better concurrent reads.
"""

import sqlite3
import os
import json
import time
import gzip
import shutil
from datetime import datetime

DB_PATH = '/mnt/media/market_data/pinch_market.db'
SCHEMA_PATH = '/mnt/media/market_data/schema.sql'
BACKUP_DIR = '/mnt/media/market_data/backups'


class MarketDB:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")   # better concurrent reads
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
        self.conn.execute("PRAGMA temp_store=MEMORY")
        self._init_schema()

    def _init_schema(self):
        """Initialize database schema from SQL file."""
        with open(SCHEMA_PATH) as f:
            self.conn.executescript(f.read())
        self.conn.commit()

    # -------------------------------------------------------------------------
    # Single-row inserts
    # -------------------------------------------------------------------------

    def insert_price(self, timestamp, symbol, asset_class, source, timeframe,
                     o=None, h=None, l=None, c=None, vol=None):
        """Insert one OHLCV price record."""
        sql = """
            INSERT OR IGNORE INTO prices
                (timestamp, symbol, asset_class, source, timeframe, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        self.conn.execute(sql, (timestamp, symbol, asset_class, source, timeframe,
                                o, h, l, c, vol))
        self.conn.commit()

    def insert_option(self, timestamp, symbol, asset_class, source, expiry,
                      strike, option_type, **kwargs):
        """Insert one options chain record."""
        fields = ['timestamp', 'symbol', 'asset_class', 'source', 'expiry',
                  'strike', 'option_type']
        values = [timestamp, symbol, asset_class, source, expiry, strike, option_type]

        optional = ['open_interest', 'volume', 'bid', 'ask', 'last_price',
                    'mark_price', 'implied_volatility', 'delta', 'gamma',
                    'theta', 'vega', 'underlying_price']
        for f in optional:
            if f in kwargs:
                fields.append(f)
                values.append(kwargs[f])

        placeholders = ', '.join(['?'] * len(values))
        col_names = ', '.join(fields)
        sql = f"INSERT OR IGNORE INTO options_chain ({col_names}) VALUES ({placeholders})"
        self.conn.execute(sql, values)
        self.conn.commit()

    def insert_metric(self, timestamp, symbol, source, metric, value, metadata=None):
        """Insert one derived metric."""
        meta_str = json.dumps(metadata) if metadata is not None else None
        sql = """
            INSERT OR IGNORE INTO derived_metrics
                (timestamp, symbol, source, metric, value, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        self.conn.execute(sql, (timestamp, symbol, source, metric, value, meta_str))
        self.conn.commit()

    def insert_funding_rate(self, timestamp, symbol, exchange, rate):
        """Insert one funding rate record."""
        sql = """
            INSERT OR IGNORE INTO funding_rates
                (timestamp, symbol, exchange, rate)
            VALUES (?, ?, ?, ?)
        """
        self.conn.execute(sql, (timestamp, symbol, exchange, rate))
        self.conn.commit()

    def insert_onchain(self, timestamp, symbol, metric, source, value, metadata=None):
        """Insert one on-chain metric."""
        meta_str = json.dumps(metadata) if metadata is not None else None
        sql = """
            INSERT OR IGNORE INTO onchain_metrics
                (timestamp, symbol, metric, source, value, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        self.conn.execute(sql, (timestamp, symbol, metric, source, value, meta_str))
        self.conn.commit()

    def insert_sentiment(self, timestamp, indicator, source, value,
                         label=None, metadata=None):
        """Insert one sentiment record."""
        meta_str = json.dumps(metadata) if metadata is not None else None
        sql = """
            INSERT OR IGNORE INTO sentiment
                (timestamp, indicator, source, value, label, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        self.conn.execute(sql, (timestamp, indicator, source, value, label, meta_str))
        self.conn.commit()

    def insert_economic(self, timestamp, series_id, value, source='fred'):
        """Insert one economic data point."""
        sql = """
            INSERT OR IGNORE INTO economic_data
                (timestamp, series_id, source, value)
            VALUES (?, ?, ?, ?)
        """
        self.conn.execute(sql, (timestamp, series_id, source, value))
        self.conn.commit()

    # -------------------------------------------------------------------------
    # Bulk inserts
    # -------------------------------------------------------------------------

    # Column definitions per table for insert_many
    _TABLE_COLS = {
        'prices': ['timestamp', 'symbol', 'asset_class', 'source', 'timeframe',
                   'open', 'high', 'low', 'close', 'volume'],
        'options_chain': ['timestamp', 'symbol', 'asset_class', 'source', 'expiry',
                          'strike', 'option_type', 'open_interest', 'volume',
                          'bid', 'ask', 'last_price', 'mark_price',
                          'implied_volatility', 'delta', 'gamma', 'theta',
                          'vega', 'underlying_price'],
        'derived_metrics': ['timestamp', 'symbol', 'source', 'metric', 'value', 'metadata'],
        'funding_rates': ['timestamp', 'symbol', 'exchange', 'rate'],
        'onchain_metrics': ['timestamp', 'symbol', 'metric', 'source', 'value', 'metadata'],
        'sentiment': ['timestamp', 'indicator', 'source', 'value', 'label', 'metadata'],
        'etf_flows': ['timestamp', 'symbol', 'source', 'flow_usd', 'aum', 'metadata'],
        'liquidations': ['timestamp', 'symbol', 'exchange', 'side', 'amount_usd', 'price'],
        'long_short_ratios': ['timestamp', 'symbol', 'exchange', 'long_pct', 'short_pct', 'ratio'],
        'economic_data': ['timestamp', 'series_id', 'source', 'value'],
        'prediction_markets': ['timestamp', 'market', 'event_ticker', 'event_name',
                               'yes_price', 'no_price', 'volume'],
        'orderbook_snapshots': ['timestamp', 'symbol', 'exchange', 'bid_depth_json',
                                'ask_depth_json', 'spread_pct', 'mid_price'],
        'vix_term_structure': ['timestamp', 'expiry', 'vix_value', 'days_to_expiry'],
    }

    def insert_many(self, table, rows):
        """
        Bulk insert rows into table using INSERT OR IGNORE.

        rows: list of dicts OR list of tuples (must match column order).
        Returns number of rows inserted (approximate — ignores go uncounted).
        """
        if not rows:
            return 0

        cols = self._TABLE_COLS.get(table)
        if cols is None:
            raise ValueError(f"Unknown table: {table}")

        placeholders = ', '.join(['?'] * len(cols))
        col_names = ', '.join(cols)
        sql = f"INSERT OR IGNORE INTO {table} ({col_names}) VALUES ({placeholders})"

        # Normalise to tuple list
        if isinstance(rows[0], dict):
            data = [tuple(r.get(c) for c in cols) for r in rows]
        else:
            data = [tuple(r) for r in rows]

        self.conn.executemany(sql, data)
        self.conn.commit()
        return len(data)

    # -------------------------------------------------------------------------
    # Collection logging
    # -------------------------------------------------------------------------

    def log_collection(self, collector, status, records=0,
                       duration_ms=0, error=None):
        """Record a collection run in collection_log."""
        sql = """
            INSERT INTO collection_log
                (timestamp, collector, status, records_inserted, duration_ms, error_msg)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        self.conn.execute(sql, (int(time.time()), collector, status,
                                records, duration_ms, error))
        self.conn.commit()

    # -------------------------------------------------------------------------
    # Query helpers
    # -------------------------------------------------------------------------

    def query(self, sql, params=None):
        """Execute a SELECT and return list of Row objects."""
        cur = self.conn.execute(sql, params or [])
        return cur.fetchall()

    def get_latest(self, table, symbol, n=1):
        """Return the n most recent rows for a symbol (requires 'symbol' column)."""
        sql = f"SELECT * FROM {table} WHERE symbol = ? ORDER BY timestamp DESC LIMIT ?"
        return self.query(sql, [symbol, n])

    def stats(self):
        """Return dict of row counts per table and DB file size."""
        tables = [
            'prices', 'options_chain', 'derived_metrics', 'funding_rates',
            'onchain_metrics', 'sentiment', 'etf_flows', 'liquidations',
            'long_short_ratios', 'economic_data', 'prediction_markets',
            'orderbook_snapshots', 'vix_term_structure', 'collection_log',
        ]
        counts = {}
        for t in tables:
            try:
                row = self.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()
                counts[t] = row[0]
            except Exception:
                counts[t] = -1

        db_size = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0

        # Last collection per collector
        last_collections = {}
        try:
            rows = self.query("""
                SELECT collector, MAX(timestamp) as last_ts, status
                FROM collection_log
                GROUP BY collector
                ORDER BY collector
            """)
            for r in rows:
                last_collections[r['collector']] = {
                    'last_ts': r['last_ts'],
                    'status': r['status'],
                }
        except Exception:
            pass

        return {
            'row_counts': counts,
            'db_size_bytes': db_size,
            'last_collections': last_collections,
        }

    # -------------------------------------------------------------------------
    # Backup
    # -------------------------------------------------------------------------

    def backup(self):
        """
        Copy database to backups/ as gzipped file named
        pinch_market_YYYYMMDD.db.gz.
        Returns path to backup file.
        """
        os.makedirs(BACKUP_DIR, exist_ok=True)
        date_str = datetime.utcnow().strftime('%Y%m%d')
        backup_path = os.path.join(BACKUP_DIR, f'pinch_market_{date_str}.db.gz')

        # Use SQLite's backup API to get a consistent snapshot
        tmp_path = backup_path.replace('.gz', '.tmp')
        backup_conn = sqlite3.connect(tmp_path)
        self.conn.backup(backup_conn)
        backup_conn.close()

        with open(tmp_path, 'rb') as f_in:
            with gzip.open(backup_path, 'wb', compresslevel=6) as f_out:
                shutil.copyfileobj(f_in, f_out)

        os.remove(tmp_path)
        return backup_path

    # -------------------------------------------------------------------------
    # Housekeeping
    # -------------------------------------------------------------------------

    def close(self):
        """Close the database connection."""
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
