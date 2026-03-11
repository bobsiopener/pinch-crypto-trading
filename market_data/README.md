# Pinch Market Data — Collection System

> Rule of Acquisition #74: Knowledge equals profit.

A comprehensive SQLite-backed market data collector for crypto, stocks, macro/FRED, and sentiment data.

## Database: `pinch_market.db`

Stored at `/mnt/media/market_data/pinch_market.db`

### Tables

| Table | Description |
|-------|-------------|
| `prices` | OHLCV bars — crypto (Kraken, Binance, CoinGecko), stocks (Yahoo), VIX |
| `options_chain` | Options data — Deribit (BTC/ETH), Binance, yfinance |
| `derived_metrics` | Max pain, P/C ratio, IV rank, market cap |
| `funding_rates` | Crypto perp funding rates (Binance) |
| `onchain_metrics` | BTC/ETH on-chain data (hash rate, mempool, etc.) |
| `sentiment` | Fear & Greed index, Reddit sentiment |
| `etf_flows` | BTC ETF inflows/outflows (IBIT, FBTC, etc.) |
| `liquidations` | Crypto liquidation data |
| `long_short_ratios` | Binance L/S ratios |
| `economic_data` | FRED macro series (DGS10, CPI, PCE, etc.) |
| `prediction_markets` | Kalshi, Polymarket |
| `orderbook_snapshots` | L2 orderbook snapshots |
| `vix_term_structure` | VIX futures term structure |
| `collection_log` | Health/audit log for every collection run |

## Usage

```bash
cd /mnt/media/market_data

# Run all collectors
python3 collect.py all

# Individual collectors
python3 collect.py crypto     # Kraken + Binance + CoinGecko + funding rates
python3 collect.py macro      # FRED + VIX + Fear & Greed + BTC on-chain
python3 collect.py stocks     # Yahoo Finance (requires yfinance)

# Utilities
python3 collect.py status     # DB stats: row counts, size, last runs
python3 collect.py backup     # Compress DB to backups/pinch_market_YYYYMMDD.db.gz
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `FRED_API_KEY` | Optional | Free API key from [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html) — enables 21 macro series |

## Cron Example

```cron
# Daily collection at 6:30 AM ET
30 6 * * * cd /mnt/media/market_data && python3 collect.py all >> logs/collect.log 2>&1

# Hourly crypto prices
0 * * * * cd /mnt/media/market_data && python3 collect.py crypto >> logs/collect.log 2>&1

# Weekly backup Sunday midnight
0 0 * * 0 cd /mnt/media/market_data && python3 collect.py backup
```

## Directory Layout

```
/mnt/media/market_data/
├── schema.sql           — SQLite schema (all tables + indexes)
├── collect.py           — Main CLI runner
├── pinch_market.db      — Live database (WAL mode)
├── collector/
│   ├── __init__.py
│   ├── config.py        — Symbols, endpoints, API keys
│   └── db.py            — MarketDB class (insert helpers, bulk, backup)
├── backups/             — Gzipped DB snapshots
└── raw/                 — Raw API response cache (future use)
```

## Design Notes

- **INSERT OR IGNORE** everywhere — safe to re-run collectors without duplicates
- **WAL mode** — supports concurrent reads during writes
- **stdlib only** for core framework (urllib, sqlite3, gzip, json)
- yfinance used only in stocks collector (separate install)
