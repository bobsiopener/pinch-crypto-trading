"""
db_loader.py — Load market data from pinch_market.db for backtesting.

DB path: /mnt/media/market_data/pinch_market.db

Schema (all timestamps are Unix epoch integers):
  prices         : id, timestamp, symbol, asset_class, source, timeframe, open, high, low, close, volume
  economic_data  : id, timestamp, series_id, source, value
  onchain_metrics: id, timestamp, symbol, metric, source, value, metadata
  sentiment      : id, timestamp, indicator, source, value, label, metadata
  options_chain  : id, timestamp, symbol, asset_class, source, expiry, strike, option_type,
                   open_interest, volume, bid, ask, last_price, mark_price, implied_volatility,
                   delta, gamma, theta, vega, underlying_price
  derived_metrics: id, timestamp, symbol, source, metric, value, metadata
"""

import sqlite3
import os
import sys
from datetime import datetime, date
from typing import Optional, List, Dict, Union

import pandas as pd

DB_PATH = os.environ.get("PINCH_DB_PATH", "/mnt/media/market_data/pinch_market.db")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _conn() -> sqlite3.Connection:
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"Market DB not found: {DB_PATH}")
    return sqlite3.connect(DB_PATH)


def _to_ts(d) -> Optional[int]:
    """Convert date/str to Unix timestamp (seconds). Returns None if d is None."""
    if d is None:
        return None
    if isinstance(d, (int, float)):
        return int(d)
    if isinstance(d, datetime):
        return int(d.timestamp())
    if isinstance(d, date):
        return int(datetime(d.year, d.month, d.day).timestamp())
    if isinstance(d, str):
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d"):
            try:
                return int(datetime.strptime(d, fmt).timestamp())
            except ValueError:
                continue
    raise ValueError(f"Cannot convert to timestamp: {d!r}")


def _build_date_clause(col: str, start_date, end_date, params: list) -> str:
    """Return SQL fragment ' AND col >= ? AND col <= ?' and append to params."""
    clauses = []
    start_ts = _to_ts(start_date)
    end_ts = _to_ts(end_date)
    if start_ts is not None:
        clauses.append(f"{col} >= ?")
        params.append(start_ts)
    if end_ts is not None:
        # inclusive end: push to end of that day
        if isinstance(end_date, str) and len(end_date) == 10:
            end_ts += 86399
        clauses.append(f"{col} <= ?")
        params.append(end_ts)
    return (" AND " + " AND ".join(clauses)) if clauses else ""


# ---------------------------------------------------------------------------
# Price data
# ---------------------------------------------------------------------------

def get_price_history(
    symbol: str,
    start_date=None,
    end_date=None,
    timeframe: str = "1d",
    source: Optional[str] = None,
) -> pd.DataFrame:
    """
    Returns OHLCV DataFrame (columns: Date, Open, High, Low, Close, Volume)
    for the given symbol from the market database.

    Example:
        df = get_price_history('BTC', '2022-01-01', '2026-03-01')
    """
    params: list = [symbol.upper(), timeframe]
    date_clause = _build_date_clause("timestamp", start_date, end_date, params)
    source_clause = ""
    if source:
        source_clause = " AND source = ?"
        params.append(source)

    sql = f"""
        SELECT datetime(timestamp, 'unixepoch') AS Date,
               open  AS Open,
               high  AS High,
               low   AS Low,
               close AS Close,
               volume AS Volume
        FROM prices
        WHERE symbol = ?
          AND timeframe = ?
          {date_clause}
          {source_clause}
        ORDER BY timestamp ASC
    """
    with _conn() as con:
        df = pd.read_sql_query(sql, con, params=params)

    if df.empty:
        return df

    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date")
    return df


def get_multiple_prices(
    symbols: List[str],
    start_date=None,
    end_date=None,
    timeframe: str = "1d",
) -> Dict[str, pd.DataFrame]:
    """
    Returns {symbol: DataFrame} for multiple symbols.
    Useful for correlation analysis, pairs trading backtests.
    """
    return {
        sym: get_price_history(sym, start_date=start_date, end_date=end_date, timeframe=timeframe)
        for sym in symbols
    }


# ---------------------------------------------------------------------------
# Economic / FRED data
# ---------------------------------------------------------------------------

def get_economic_series(
    series_id: str,
    start_date=None,
    end_date=None,
) -> pd.DataFrame:
    """
    Returns DataFrame (columns: Date, Value) from FRED economic data.

    Example:
        df = get_economic_series('DGS10', '2020-01-01')
    """
    params: list = [series_id.upper()]
    date_clause = _build_date_clause("timestamp", start_date, end_date, params)

    sql = f"""
        SELECT datetime(timestamp, 'unixepoch') AS Date,
               value AS Value
        FROM economic_data
        WHERE series_id = ?
          {date_clause}
        ORDER BY timestamp ASC
    """
    with _conn() as con:
        df = pd.read_sql_query(sql, con, params=params)

    if df.empty:
        return df

    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date")
    return df


def get_multiple_economic(
    series_ids: List[str],
    start_date=None,
    end_date=None,
) -> Dict[str, pd.DataFrame]:
    """
    Returns {series_id: DataFrame} for multiple FRED series.
    """
    return {
        sid: get_economic_series(sid, start_date=start_date, end_date=end_date)
        for sid in series_ids
    }


# ---------------------------------------------------------------------------
# On-chain metrics
# ---------------------------------------------------------------------------

def get_onchain_metric(
    symbol: str,
    metric: str,
    start_date=None,
    end_date=None,
) -> pd.DataFrame:
    """
    Returns DataFrame (columns: Date, Value) for on-chain metrics.

    Example:
        df = get_onchain_metric('BTC', 'hash_rate')
    """
    params: list = [symbol.upper(), metric]
    date_clause = _build_date_clause("timestamp", start_date, end_date, params)

    sql = f"""
        SELECT datetime(timestamp, 'unixepoch') AS Date,
               value AS Value
        FROM onchain_metrics
        WHERE symbol = ?
          AND metric = ?
          {date_clause}
        ORDER BY timestamp ASC
    """
    with _conn() as con:
        df = pd.read_sql_query(sql, con, params=params)

    if df.empty:
        return df

    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date")
    return df


# ---------------------------------------------------------------------------
# Sentiment
# ---------------------------------------------------------------------------

def get_sentiment(
    indicator: str,
    start_date=None,
    end_date=None,
) -> pd.DataFrame:
    """
    Returns DataFrame (columns: Date, Value, Label).

    Example:
        df = get_sentiment('fear_greed_crypto')
    """
    params: list = [indicator]
    date_clause = _build_date_clause("timestamp", start_date, end_date, params)

    sql = f"""
        SELECT datetime(timestamp, 'unixepoch') AS Date,
               value AS Value,
               label AS Label
        FROM sentiment
        WHERE indicator = ?
          {date_clause}
        ORDER BY timestamp ASC
    """
    with _conn() as con:
        df = pd.read_sql_query(sql, con, params=params)

    if df.empty:
        return df

    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date")
    return df


# ---------------------------------------------------------------------------
# Options chain
# ---------------------------------------------------------------------------

def get_options_snapshot(
    symbol: str,
    timestamp=None,
) -> pd.DataFrame:
    """
    Returns DataFrame of options chain for a symbol at a given time.
    If timestamp is None, returns the latest available snapshot.

    Columns: expiry, strike, option_type, open_interest, volume, bid, ask,
             last_price, mark_price, implied_volatility, delta, gamma, theta,
             vega, underlying_price, snapshot_time
    """
    sym = symbol.upper()

    with _conn() as con:
        if timestamp is None:
            # Find the most recent timestamp for this symbol
            row = con.execute(
                "SELECT MAX(timestamp) FROM options_chain WHERE symbol = ?", (sym,)
            ).fetchone()
            if row[0] is None:
                return pd.DataFrame()
            snap_ts = row[0]
        else:
            snap_ts = _to_ts(timestamp)

        params = [sym, snap_ts]
        sql = """
            SELECT expiry, strike, option_type,
                   open_interest, volume, bid, ask,
                   last_price, mark_price, implied_volatility,
                   delta, gamma, theta, vega, underlying_price,
                   datetime(timestamp, 'unixepoch') AS snapshot_time
            FROM options_chain
            WHERE symbol = ?
              AND timestamp = ?
            ORDER BY expiry, strike, option_type
        """
        df = pd.read_sql_query(sql, con, params=params)

    return df


# ---------------------------------------------------------------------------
# Derived metrics
# ---------------------------------------------------------------------------

def get_derived_metric(
    symbol: str,
    metric: str,
    start_date=None,
    end_date=None,
) -> pd.DataFrame:
    """
    Returns DataFrame (columns: Date, Value) for derived metrics
    such as max_pain, pc_ratio.

    Example:
        df = get_derived_metric('BTC', 'max_pain_2026-03-20')
    """
    params: list = [symbol.upper(), metric]
    date_clause = _build_date_clause("timestamp", start_date, end_date, params)

    sql = f"""
        SELECT datetime(timestamp, 'unixepoch') AS Date,
               value AS Value,
               metadata
        FROM derived_metrics
        WHERE symbol = ?
          AND metric = ?
          {date_clause}
        ORDER BY timestamp ASC
    """
    with _conn() as con:
        df = pd.read_sql_query(sql, con, params=params)

    if df.empty:
        return df

    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date")
    return df


# ---------------------------------------------------------------------------
# Correlation matrix
# ---------------------------------------------------------------------------

def get_correlation_matrix(
    symbols: List[str],
    start_date=None,
    end_date=None,
    window: int = 30,
) -> pd.DataFrame:
    """
    Returns rolling correlation matrix (last window days) between multiple assets.
    Uses daily close prices.
    """
    prices = get_multiple_prices(symbols, start_date=start_date, end_date=end_date)

    close_df = pd.DataFrame({
        sym: df["Close"] for sym, df in prices.items() if not df.empty
    })

    if close_df.empty or len(close_df) < 2:
        return close_df

    # Use tail(window) for the correlation window
    return close_df.tail(window).corr()


# ---------------------------------------------------------------------------
# Discovery / metadata
# ---------------------------------------------------------------------------

def list_available_symbols(asset_class: Optional[str] = None) -> List[str]:
    """
    Returns list of available symbols, optionally filtered by asset_class.
    asset_class options: 'crypto', 'stock', 'etf', 'index'
    """
    params: list = []
    clause = ""
    if asset_class:
        clause = "WHERE asset_class = ?"
        params.append(asset_class.lower())

    sql = f"SELECT DISTINCT symbol FROM prices {clause} ORDER BY symbol"
    with _conn() as con:
        rows = con.execute(sql, params).fetchall()
    return [r[0] for r in rows]


def list_available_series() -> pd.DataFrame:
    """
    Returns DataFrame of available FRED series with record counts and date ranges.
    Columns: series_id, count, min_date, max_date
    """
    sql = """
        SELECT series_id,
               COUNT(*) AS count,
               datetime(MIN(timestamp), 'unixepoch') AS min_date,
               datetime(MAX(timestamp), 'unixepoch') AS max_date
        FROM economic_data
        GROUP BY series_id
        ORDER BY series_id
    """
    with _conn() as con:
        df = pd.read_sql_query(sql, con)
    return df


def data_summary() -> pd.DataFrame:
    """
    Returns summary of all available price data:
    symbol, asset_class, timeframe, record_count, min_date, max_date
    """
    sql = """
        SELECT symbol, asset_class, timeframe,
               COUNT(*) AS record_count,
               datetime(MIN(timestamp), 'unixepoch') AS min_date,
               datetime(MAX(timestamp), 'unixepoch') AS max_date
        FROM prices
        GROUP BY symbol, asset_class, timeframe
        ORDER BY asset_class, symbol, timeframe
    """
    with _conn() as con:
        df = pd.read_sql_query(sql, con)
    return df


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _ascii_chart(prices: pd.Series, width: int = 72, height: int = 20) -> str:
    """Render a simple ASCII price chart."""
    if prices.empty:
        return "(no data)"

    vals = prices.dropna().values
    if len(vals) == 0:
        return "(no data)"

    lo, hi = vals.min(), vals.max()
    rng = hi - lo or 1.0

    # Downsample to width columns
    n = len(vals)
    step = max(1, n // width)
    sampled = [vals[i] for i in range(0, n, step)][:width]

    rows = []
    for r in range(height - 1, -1, -1):
        threshold = lo + (r / (height - 1)) * rng
        line = ""
        for v in sampled:
            line += "█" if v >= threshold else " "
        rows.append(line)

    # X-axis
    rows.append("─" * len(sampled))

    # Y-axis labels
    label_hi = f"${hi:,.0f}"
    label_lo = f"${lo:,.0f}"
    chart_lines = []
    for i, row in enumerate(rows[:-1]):
        if i == 0:
            chart_lines.append(f"{label_hi:>12} │{row}")
        elif i == height - 1:
            chart_lines.append(f"{label_lo:>12} │{row}")
        else:
            chart_lines.append(f"{'':>12} │{row}")
    chart_lines.append(f"{'':>12} └{rows[-1]}")

    return "\n".join(chart_lines)


def _cli():
    args = sys.argv[1:]
    if not args:
        print("Usage:")
        print("  python3 db_loader.py symbols [asset_class]")
        print("  python3 db_loader.py series")
        print("  python3 db_loader.py summary")
        print("  python3 db_loader.py plot SYMBOL [start_date] [end_date]")
        sys.exit(0)

    cmd = args[0].lower()

    if cmd == "symbols":
        ac = args[1] if len(args) > 1 else None
        syms = list_available_symbols(ac)
        print(f"\nAvailable symbols{' (' + ac + ')' if ac else ''}: {len(syms)}")
        for s in syms:
            print(f"  {s}")

    elif cmd == "series":
        df = list_available_series()
        print(f"\nAvailable FRED series: {len(df)}")
        print(df.to_string(index=False))

    elif cmd == "summary":
        df = data_summary()
        print("\nMarket data summary:")
        print(df.to_string(index=False))

    elif cmd == "plot":
        if len(args) < 2:
            print("Usage: python3 db_loader.py plot SYMBOL [start_date] [end_date]")
            sys.exit(1)
        symbol = args[1].upper()
        start = args[2] if len(args) > 2 else None
        end = args[3] if len(args) > 3 else None
        df = get_price_history(symbol, start_date=start, end_date=end)
        if df.empty:
            print(f"No data found for {symbol}")
            sys.exit(1)
        print(f"\n{symbol} Close Price  [{df.index[0].date()} → {df.index[-1].date()}]  ({len(df)} bars)")
        print(_ascii_chart(df["Close"]))
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    _cli()
