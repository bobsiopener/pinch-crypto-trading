"""
export_from_db.py — Regenerate standard backtest CSV files from pinch_market.db.

Usage:
    python3 export_from_db.py btc_daily   # writes backtest/data/btc_daily.csv
    python3 export_from_db.py eth_daily   # writes backtest/data/eth_daily.csv
    python3 export_from_db.py sol_daily   # writes backtest/data/sol_daily.csv
    python3 export_from_db.py all         # exports all standard CSVs

The output format matches the existing CSV schema:
    date,open,high,low,close,volume  (lowercase, date as YYYY-MM-DD)
"""

import os
import sys
import sqlite3
from datetime import datetime

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DB_PATH = os.environ.get("PINCH_DB_PATH", "/mnt/media/market_data/pinch_market.db")
DATA_DIR = os.path.dirname(os.path.abspath(__file__))

# Standard export definitions: name → (symbol, timeframe, start_date)
STANDARD_EXPORTS = {
    "btc_daily": ("BTC", "1d", None),
    "eth_daily": ("ETH", "1d", None),
    "sol_daily": ("SOL", "1d", None),
}


# ---------------------------------------------------------------------------
# Core export
# ---------------------------------------------------------------------------

def _export_prices(symbol: str, timeframe: str = "1d", start_date: str = None) -> pd.DataFrame:
    """Load OHLCV from DB and return a DataFrame with lowercase date-indexed columns."""
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"Market DB not found: {DB_PATH}")

    params = [symbol.upper(), timeframe]
    date_clause = ""
    if start_date:
        ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp())
        date_clause = "AND timestamp >= ?"
        params.append(ts)

    sql = f"""
        SELECT date(timestamp, 'unixepoch') AS date,
               open, high, low, close, volume
        FROM prices
        WHERE symbol = ?
          AND timeframe = ?
          {date_clause}
        ORDER BY timestamp ASC
    """
    with sqlite3.connect(DB_PATH) as con:
        df = pd.read_sql_query(sql, con, params=params)

    return df


def export_csv(name: str, output_path: str = None, verbose: bool = True) -> str:
    """
    Export a named standard dataset to CSV.

    Returns the path written.
    """
    name = name.lower().rstrip(".csv")

    if name not in STANDARD_EXPORTS:
        raise ValueError(
            f"Unknown export name '{name}'. "
            f"Valid names: {', '.join(STANDARD_EXPORTS)}"
        )

    symbol, timeframe, start_date = STANDARD_EXPORTS[name]

    if verbose:
        print(f"Exporting {name} ({symbol} {timeframe}) from DB...", end=" ", flush=True)

    df = _export_prices(symbol, timeframe=timeframe, start_date=start_date)

    if df.empty:
        print(f"WARNING: no data found for {symbol} {timeframe}")
        return ""

    if output_path is None:
        output_path = os.path.join(DATA_DIR, f"{name}.csv")

    df.to_csv(output_path, index=False)

    if verbose:
        print(f"{len(df)} rows → {output_path}")

    return output_path


def export_all(verbose: bool = True) -> None:
    """Export all standard CSVs."""
    for name in STANDARD_EXPORTS:
        try:
            export_csv(name, verbose=verbose)
        except Exception as exc:
            print(f"ERROR exporting {name}: {exc}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    target = sys.argv[1].lower()

    if target == "all":
        export_all()
    else:
        try:
            export_csv(target)
        except ValueError as exc:
            print(f"Error: {exc}")
            sys.exit(1)


if __name__ == "__main__":
    main()
