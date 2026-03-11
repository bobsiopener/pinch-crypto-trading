# Pinch Trading System — Architecture

> *"Rule of Acquisition #74: Knowledge equals profit."*

---

## System Diagram

```
╔══════════════════════════════════════════════════════════════════════════╗
║                     PINCH CRYPTO TRADING SYSTEM                          ║
╚══════════════════════════════════════════════════════════════════════════╝

┌─────────────────────────────────────────────────────────────────────────┐
│                           DATA SOURCES                                   │
│                                                                          │
│  CoinGecko  Kraken  Binance  Deribit  Yahoo  FRED  Kalshi  Blockchain   │
└───────┬──────────┬──────┬──────────┬──────┬──────┬───────┬─────────────┘
        │          │      │          │      │      │       │
        ▼          ▼      ▼          ▼      ▼      ▼       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    MARKET DATA COLLECTOR                                  │
│                    /mnt/media/market_data/                               │
│                                                                          │
│  collect.py  ──►  collector/crypto_collector.py  (BTC/ETH/SOL OHLCV)   │
│                   collector/stock_collector.py   (SPY/QQQ/AAPL/etc)    │
│                   collector/macro_collector.py   (FRED series)          │
│                   collector/db.py                (MarketDB insert)      │
│                                                                          │
│  Cron: hourly crypto │ 6:30AM daily full │ Sunday backup                │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│              SQLite DATABASE: pinch_market.db                            │
│              /mnt/media/market_data/pinch_market.db                     │
│                                                                          │
│  prices │ options_chain │ derived_metrics │ funding_rates │ onchain      │
│  sentiment │ etf_flows │ liquidations │ long_short_ratios │ economic     │
│  prediction_markets │ orderbook_snapshots │ vix_term_structure           │
│  collection_log                                                          │
└──────────┬──────────────────────────────────────────────────────────────┘
           │
     ┌─────┴───────────────────────────────────────┐
     │                                             │
     ▼                                             ▼
┌──────────────────────────┐          ┌────────────────────────────────┐
│   BACKTESTING ENGINE     │          │   LIVE INFRASTRUCTURE          │
│   /backtest/             │          │   /live/                       │
│                          │          │                                │
│  data/ ──► strategies/   │          │  monitor/market_monitor.py     │
│    macro_swing.py        │          │    └── polls prices every 60s  │
│    ema_crossover.py      │          │    └── fires Discord alerts     │
│    grid_trading.py       │          │    └── tracks macro events      │
│    maxpain_expiry.py     │          │    └── detects grid fills       │
│    mean_reversion.py     │          │                                │
│    rsi_overlay.py        │          │  signals/options_poller.py     │
│    candlestick_filter.py │          │    └── Deribit IV + max pain    │
│    kelly_sizing.py       │          │                                │
│                          │          │  paper_trading/                │
│  run_*.py ──► results/   │          │    track_manager.py            │
│    12 result reports     │          │    grid_paper_trader.py        │
│    oos_validation.md     │          │    state/paper_tracks.json     │
└──────────────────────────┘          │    state/grid_paper_state.json │
                                      │                                │
                                      │  execution/                    │
                                      │    kill_switch.py ──► Kraken   │
                                      │    risk_manager.py             │
                                      │                                │
                                      │  monitoring/                   │
                                      │    dashboard.py                │
                                      │    trade_logger.py             │
                                      └───────────────┬────────────────┘
                                                      │
                                                      ▼
                                      ┌────────────────────────────────┐
                                      │   STATE & LOGS                 │
                                      │                                │
                                      │  state/monitor_state.json      │
                                      │  state/price_history.json      │
                                      │  live/config/risk_state.json   │
                                      │  logs/trades/paper_trades.csv  │
                                      │  logs/trades/daily_pnl.csv     │
                                      │  logs/monitor/monitor.log      │
                                      └───────────────┬────────────────┘
                                                      │
                                                      ▼
                                      ┌────────────────────────────────┐
                                      │   DISCORD (#investments)       │
                                      │                                │
                                      │  openclaw CLI → send alerts    │
                                      │  Dashboard output              │
                                      │  Trade notifications           │
                                      └────────────────────────────────┘
```

---

## Data Flow

### 1. Collection → Database

```
External APIs
    │
    ├── CoinGecko (free) → BTC/ETH/SOL daily OHLCV
    ├── Kraken (free) → BTC/ETH/SOL OHLCV + orderbook
    ├── Binance (free) → funding rates, L/S ratios, liquidations
    ├── Deribit (free) → options chains, IV, max pain
    ├── Yahoo Finance (yfinance) → stocks, ETFs, VIX
    ├── FRED (free API key) → 21 macro series
    └── Blockchain APIs → on-chain metrics (hash rate, MVRV)
         │
         ▼
    market_data/collector/ → INSERT OR IGNORE into pinch_market.db
         │
         ▼
    collection_log → health audit (status, records, duration)
```

### 2. Database → Backtests

```
pinch_market.db (or CSV fallback in backtest/data/)
    │
    ├── backtest/data/btc_daily.csv   (BTC 2022-2026)
    ├── backtest/data/eth_daily.csv   (ETH 2022-2026)
    ├── backtest/data/sol_daily.csv   (SOL 2022-2026)
    ├── backtest/data/macro_events.csv (CPI/FOMC/NFP history)
    ├── backtest/data/options_proxy.csv (IV proxy)
    └── backtest/data/maxpain_proxy.csv
         │
         ▼
    backtest/strategies/*.py → trade simulation
         │
         ▼
    backtest/results/*.md → performance reports
```

### 3. Signals → Paper Trades → Monitoring

```
market_monitor.py (daemon, 60s loop)
    │
    ├── Fetch BTC/ETH/SOL prices (CoinGecko free API)
    ├── Check macro_calendar.json for upcoming events
    ├── Check for price threshold alerts (>3% move)
    ├── Check grid fill conditions
    │
    ▼
live/signals/options_poller.py
    ├── Poll Deribit for current IV, max pain
    └── Store to market DB or state file
         │
         ▼
live/paper_trading/track_manager.py + grid_paper_trader.py
    ├── Evaluate signals against 3 paper tracks
    ├── Execute paper trades (no real money)
    └── Write to logs/trades/paper_trades.csv
         │
         ▼
live/monitoring/dashboard.py
    ├── Read paper_tracks.json, risk_state.json
    ├── Fetch live prices
    └── Render P&L summary → Discord or terminal
```

---

## Component Descriptions

### `market_data/` — Data Collection System

The primary data ingestion layer. The `collect.py` CLI orchestrates modular collectors:

- **`crypto_collector.py`** — Pulls OHLCV from CoinGecko + Kraken + Binance. Also fetches funding rates and liquidation data.
- **`stock_collector.py`** — Pulls equity/ETF data via yfinance. Covers SPY, QQQ, AAPL, NVDA, MSFT, BTC ETFs (IBIT, FBTC), VIX.
- **`macro_collector.py`** — FRED API for 21 macro series: 10-year yield, CPI, PCE, unemployment rate, M2 money supply, etc.
- **`db.py`** — `MarketDB` class providing safe bulk insert, backup, and status queries.

All collectors use `INSERT OR IGNORE` — safe to re-run without creating duplicates.

### `backtest/` — Strategy Backtesting Engine

Historical strategy simulation. Each strategy in `strategies/` is a standalone Python class implementing `generate_signals(df)` and `run(df)`. Backtest runners in `run_*.py` load data, instantiate the strategy, run it, and write Markdown results to `results/`.

The primary production strategy is **Macro Swing** (run_backtest.py), which scores macro events (CPI, FOMC, NFP) and enters/exits BTC positions based on signal strength.

### `live/monitor/` — Market Monitor Daemon

A systemd service (`market-monitor.service`) running `market_monitor.py` in a continuous loop:

- Polls CoinGecko every 60 seconds for BTC/ETH/SOL prices
- Sends Discord alerts on: >3% price moves, macro events within 24h, grid fill conditions
- Tracks state in `state/monitor_state.json` and `state/price_history.json`
- Rotates logs nightly in `logs/monitor/`

Controlled via:
```bash
python3 live/monitor/market_monitor.py run          # start daemon
python3 live/monitor/market_monitor.py status       # show state
python3 live/monitor/market_monitor.py test-alert   # test Discord
python3 live/monitor/market_monitor.py add-event "2026-03-25" "08:30" "CPI March" "high"
```

### `live/execution/` — Risk & Kill Switch

- **`kill_switch.py`** — Connects to Kraken API, cancels all orders, market-sells all positions. Logs to `logs/trades/kill_switch_log.csv`. Triggered by "go flat" / "kill switch" command.
- **`risk_manager.py`** — Tracks high-water mark, current drawdown, alert thresholds. Updates `live/config/risk_state.json`.

### `live/paper_trading/` — Paper Trading Engine

Three parallel paper tracks (A, B, C) implemented in `track_manager.py`:

- **Track A — Macro Swing v2:** Uses macro signal scoring (same logic as backtested strategy). $752 starting capital, 50% deployed.
- **Track B — Grid Trading:** ETH grid with configurable range and levels. $376 starting capital.
- **Track C — Full Hybrid:** Combines macro entries with grid for range-bound periods. $752 starting capital.

State is persisted in `live/paper_trading/state/paper_tracks.json`.

### `live/monitoring/` — Dashboard & Trade Logger

- **`dashboard.py`** — Terminal/Discord-ready P&L dashboard. Reads paper tracks, risk state, live prices. Supports `--brief`, `--json`, `--discord` flags.
- **`trade_logger.py`** — Appends paper and live trade records to CSV.

### `live/signals/` — Options Poller

`options_poller.py` fetches IV rank, max pain level, and put/call ratio from Deribit. Used as a filter/overlay signal on top of macro entries.

---

## API Dependencies & Rate Limits

| API | Usage | Rate Limit | Key Required |
|---|---|---|---|
| CoinGecko (free) | BTC/ETH/SOL OHLCV, live prices | ~50 calls/min | No |
| Kraken (public) | OHLCV, orderbook | 1 call/sec | No (public endpoints) |
| Kraken (private) | Order execution, kill switch | 15 operations/sec tier | Yes (`~/.secrets/kraken_trader.py`) |
| Binance (public) | Funding rates, L/S ratios, liquidations | 1200 calls/min | No |
| Deribit (public) | Options chains, IV, max pain | 20 calls/sec | No |
| Yahoo Finance (yfinance) | Stocks, ETFs, VIX | ~2000 calls/hour (unofficial) | No |
| FRED | Macro series | 120 calls/min | Optional (free key at fred.stlouisfed.org) |
| Discord (via openclaw) | Alerts, dashboard output | Bot rate limits apply | Via openclaw config |

---

## File Locations & State Management

| File/Directory | Purpose | Updated By |
|---|---|---|
| `/mnt/media/market_data/pinch_market.db` | Main market database | `market_data/collect.py` (cron) |
| `/mnt/media/market_data/backups/` | Gzipped DB snapshots | `collect.py backup` (weekly cron) |
| `state/monitor_state.json` | Monitor daemon state (last prices, last alert times) | `market_monitor.py` |
| `state/price_history.json` | Recent price cache (last N data points per symbol) | `market_monitor.py` |
| `live/config/risk_state.json` | High-water mark, current drawdown, trading halt flag | `risk_manager.py` |
| `live/monitor/macro_calendar.json` | Upcoming macro events | Manual / `market_monitor.py add-event` |
| `live/paper_trading/state/paper_tracks.json` | Paper trade P&L per track | `track_manager.py` |
| `live/paper_trading/state/grid_paper_state.json` | Grid trader state (levels, fills) | `grid_paper_trader.py` |
| `logs/trades/paper_trades.csv` | All paper trade entries/exits | `trade_logger.py` |
| `logs/trades/trade_log.csv` | Live trade log (for future use) | `trade_logger.py` |
| `logs/trades/daily_pnl.csv` | Daily P&L snapshots | `dashboard.py` |
| `logs/monitor/monitor.log` | Market monitor daemon log (7-day rotation) | `market_monitor.py` |

---

## Secrets & Security

Secrets are stored **outside the repo** at `/home/bob/.openclaw/workspace-pinch/.secrets/`:

- `kraken_trader.py` — Kraken API key + secret, trade execution helpers

The `.gitignore` excludes all `*.key`, `*.secret`, `.env`, and `.secrets/` paths.
No secrets are committed to the repository.
