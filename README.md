# 🪙 Pinch Crypto Trading System

> *"Rule of Acquisition #22: A wise man can hear profit in the wind."*

A comprehensive crypto and equity trading research platform with backtesting, paper trading,
live monitoring, and market data collection — operated by **Pinch** (Chief of Finance, USS Clawbot).

---

## Architecture

The system is organized into four major layers:

1. **Data Layer** — SQLite market database (`pinch_market.db`) fed by the `market_data/` collector. Stores OHLCV prices, options chains, on-chain metrics, funding rates, sentiment, ETF flows, and macro series.

2. **Research & Backtesting Layer** — Strategy implementations in `backtest/strategies/`, run via `backtest/run_*.py` scripts against historical data in `backtest/data/`. Results saved to `backtest/results/`.

3. **Live Infrastructure Layer** — Systemd-managed market monitor daemon (`live/monitor/`), kill switch and risk manager (`live/execution/`), options poller (`live/signals/`), paper trading engine (`live/paper_trading/`), and monitoring dashboard (`live/monitoring/`).

4. **Logging & State Layer** — All runtime state in `state/`, trade logs in `logs/trades/`, monitor logs in `logs/monitor/`.

See [`docs/architecture.md`](docs/architecture.md) for the full system diagram and data flow.

---

## Project Structure

```
pinch-crypto-trading/
├── backtest/                    # Strategy backtesting engine
│   ├── strategies/              # Strategy implementations (7 strategies)
│   ├── results/                 # Backtest result reports (Markdown + CSV)
│   ├── data/                    # Historical data CSVs + DB loader scripts
│   └── run_*.py                 # Individual strategy backtest runners
├── collector/                   # Legacy collector (reference only)
│   └── *.reference              # Reference config and db files
├── docs/                        # Strategy & operations documentation
│   ├── architecture.md          # System diagram and data flow
│   ├── data-dictionary.md       # Database schema documentation
│   ├── operations.md            # Runbook: health checks, deployment, trading
│   ├── strategy-plan.md         # Full strategy documentation
│   ├── risk-framework.md        # Risk management rules
│   ├── market-regime.md         # Current regime analysis
│   └── improvement-process.md   # Continuous improvement workflow
├── live/                        # Live trading infrastructure
│   ├── config/                  # Risk state JSON, account status
│   ├── execution/               # Kill switch, risk manager
│   ├── monitor/                 # Market monitor daemon + macro calendar
│   ├── monitoring/              # Dashboard, trade logger
│   ├── paper_trading/           # Grid trader, track manager, state files
│   └── signals/                 # Options poller (Deribit)
├── market_data/                 # Market data collection system
│   ├── collect.py               # Main CLI runner
│   ├── schema.sql               # SQLite schema (all tables + indexes)
│   └── collector/               # Modular collectors (crypto, stock, macro)
├── research/                    # Signal research documents
│   ├── signals/                 # 11 signal research papers
│   ├── regimes/                 # Market regime detection research
│   ├── experiments/             # Strategy experiments
│   └── exchange-evaluation.md   # Broker/exchange comparison
├── logs/                        # Trade logs, monitor logs, performance
│   ├── trades/                  # paper_trades.csv, trade_log.csv, daily_pnl.csv
│   ├── monitor/                 # Rotating market monitor logs
│   └── performance/             # Performance reports
└── state/                       # Runtime state files
    ├── monitor_state.json        # Market monitor daemon state
    └── price_history.json        # Recent price cache
```

---

## Strategies Backtested

All backtests ran on BTC/USD daily data, 2022-01-01 → 2026-03-01, $100,000 initial capital.

| Strategy | Total Return | Ann. Return | Max Drawdown | Sharpe | Win Rate | # Trades | Results File |
|---|---|---|---|---|---|---|---|
| **Buy & Hold BTC** (benchmark) | +37.85% | +8.02% | -66.89% | 0.339 | — | — | — |
| **Macro Swing** | +5.23% | +1.23% | -3.33% | 1.403 | 70.0% | 10 | [macro_swing_results.md](backtest/results/macro_swing_results.md) |
| **EMA Crossover** (10/30, no TS) | +72.26% | +13.96% | -44.69% | 0.499 | 31.8% | 22 | [ema_crossover_results.md](backtest/results/ema_crossover_results.md) |
| **EMA Crossover** (20/100, no TS) | +114.64% | +20.15% | -31.63% | 0.646 | 57.1% | 7 | [ema_crossover_results.md](backtest/results/ema_crossover_results.md) |
| **Grid Trading** (ETH) | +36.62% | — | -30.98% | — | — | — | [grid_trading_results.md](backtest/results/grid_trading_results.md) |
| **Mean Reversion** (BB) | +0.93% | — | -2.86% | — | — | — | [mean_reversion_results.md](backtest/results/mean_reversion_results.md) |
| **Max Pain Expiry** | -1.2% | — | -4.6% | -0.10 | — | — | [maxpain_strategy_results.md](backtest/results/maxpain_strategy_results.md) |
| **RSI Overlay** | +54.87% | — | -49.74% | — | — | — | [rsi_overlay_results.md](backtest/results/rsi_overlay_results.md) |
| **Candlestick Filter** | +4.55% | — | -1.68% | 1.312 | — | — | [candlestick_filter_results.md](backtest/results/candlestick_filter_results.md) |
| **Options Overlay** | +5.00% | — | -2.51% | 1.403 | — | — | [options_overlay_results.md](backtest/results/options_overlay_results.md) |
| **On-Chain Overlay** | +5.8% | — | -2.5% | 1.40 | — | — | [onchain_overlay_results.md](backtest/results/onchain_overlay_results.md) |
| **Kelly Sizing** | +7.57% | — | -4.98% | — | — | — | [kelly_sizing_results.md](backtest/results/kelly_sizing_results.md) |

> **Key insight:** Macro Swing's high Sharpe (1.40) with low drawdown (3.3%) is the production strategy. EMA(20/100) has higher raw return but 10× the drawdown. Kelly sizing adds ~2.3% return over fixed sizing.

---

## Signal Sources

| # | Signal | Source | Status | Research Paper |
|---|---|---|---|---|
| 1 | **Macro Events** (CPI, FOMC, NFP) | Manual calendar + FRED | ✅ Active | [macro-signal-definitions.md](research/signals/macro-signal-definitions.md) |
| 2 | **ETF Flows** (IBIT, FBTC, etc.) | Market data DB | ✅ Active | [etf-flow-research.md](research/signals/etf-flow-research.md) |
| 3 | **Funding Rates** | Binance perpetuals | ✅ Active | [funding-rate-research.md](research/signals/funding-rate-research.md) |
| 4 | **Kalshi / Prediction Markets** | Kalshi API | 🔬 Research | [kalshi-integration-research.md](research/signals/kalshi-integration-research.md) |
| 5 | **Kelly Criterion Sizing** | Derived from win/loss stats | ✅ Active | [kelly-criterion-research.md](research/signals/kelly-criterion-research.md) |
| 6 | **Max Pain (Options)** | Deribit | 🔬 Research | [max-pain-analysis.md](research/signals/max-pain-analysis.md) |
| 7 | **Mean Reversion** (Bollinger Bands) | Price data | ✅ Active | [mean-reversion-research.md](research/signals/mean-reversion-research.md) |
| 8 | **On-Chain Metrics** (MVRV, hash rate) | Blockchain APIs | 🔬 Research | [onchain-metrics-research.md](research/signals/onchain-metrics-research.md) |
| 9 | **Options Signals** (IV, P/C ratio) | Deribit + yfinance | 🔬 Research | [options-signals-research.md](research/signals/options-signals-research.md) |
| 10 | **Seasonality** | Historical patterns | 🔬 Research | [seasonality-research.md](research/signals/seasonality-research.md) |
| 11 | **Stop-Loss Optimization** | Backtest results | ✅ Active | [stop-loss-optimization.md](research/signals/stop-loss-optimization.md) |

---

## Market Data Infrastructure

The database lives at `/mnt/media/market_data/pinch_market.db` (SQLite, WAL mode).

**Tables:**

| Table | Description | Update Frequency |
|---|---|---|
| `prices` | OHLCV bars — crypto + stocks + ETFs | Hourly (crypto), Daily (stocks) |
| `options_chain` | Options chains — Deribit, yfinance | Daily |
| `derived_metrics` | Max pain, P/C ratio, IV rank | Daily |
| `funding_rates` | Crypto perp funding rates (Binance) | Every 8 hours |
| `onchain_metrics` | BTC/ETH on-chain data | Daily |
| `sentiment` | Fear & Greed index, Reddit sentiment | Daily |
| `etf_flows` | BTC ETF inflows/outflows | Daily |
| `liquidations` | Crypto liquidation data | Hourly |
| `long_short_ratios` | Binance L/S ratios | Hourly |
| `economic_data` | FRED macro series (DGS10, CPI, PCE) | On release |
| `prediction_markets` | Kalshi, Polymarket | Daily |
| `orderbook_snapshots` | L2 orderbook snapshots | Hourly |
| `vix_term_structure` | VIX futures term structure | Daily |
| `collection_log` | Collection health/audit log | Every run |

See [`docs/data-dictionary.md`](docs/data-dictionary.md) for full column documentation and sample queries.

**Running the collector:**

```bash
cd /mnt/media/market_data
python3 collect.py all       # Run all collectors
python3 collect.py status    # Show DB row counts and last run times
python3 collect.py backup    # Compress DB snapshot to backups/
```

**Cron schedule (recommended):**

```cron
# Hourly crypto prices
0 * * * * cd /mnt/media/market_data && python3 collect.py crypto

# Daily full collection at 6:30 AM ET
30 6 * * * cd /mnt/media/market_data && python3 collect.py all

# Weekly backup Sunday midnight
0 0 * * 0 cd /mnt/media/market_data && python3 collect.py backup
```

---

## Running Services

| Service / Timer | File | Description |
|---|---|---|
| `pinch-market-monitor.service` | `live/monitor/market-monitor.service` | Continuous price monitor daemon — polls BTC/ETH/SOL prices, fires Discord alerts on macro events and grid fills |

**Service management:**

```bash
# Install
sudo cp live/monitor/market-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pinch-market-monitor

# Status / logs
sudo systemctl status pinch-market-monitor
journalctl -u pinch-market-monitor -f

# Restart
sudo systemctl restart pinch-market-monitor
```

---

## Paper Trading

Three parallel tracks started 2026-03-11:

| Track | Name | Starting Capital | Strategy |
|---|---|---|---|
| **A** | Macro Swing v2 | $752 | Macro-driven swing trades, 50% deployed at open |
| **B** | Grid Trading | $376 | ETH grid with configurable levels |
| **C** | Full Hybrid | $752 | Combined macro + grid approach |

State files:
- `live/paper_trading/state/paper_tracks.json` — per-track P&L and trade history
- `live/paper_trading/state/grid_paper_state.json` — grid trader state

**Track manager:**

```bash
python3 live/paper_trading/track_manager.py status
python3 live/paper_trading/track_manager.py update A BUY BTC 83500 0.1
```

---

## Quick Start

**Run the monitoring dashboard:**

```bash
python3 live/monitoring/dashboard.py            # Full dashboard
python3 live/monitoring/dashboard.py --brief    # 5-line summary
python3 live/monitoring/dashboard.py --discord  # Discord-formatted
```

**Check market monitor status:**

```bash
python3 live/monitor/market_monitor.py status
```

**Query the market database:**

```bash
sqlite3 /mnt/media/market_data/pinch_market.db \
  "SELECT symbol, close, datetime(timestamp,'unixepoch') FROM prices \
   WHERE symbol='BTC' ORDER BY timestamp DESC LIMIT 5;"
```

**Run a backtest:**

```bash
cd backtest
python3 run_backtest.py           # Macro Swing (main strategy)
python3 run_ema_backtest.py       # EMA Crossover
python3 run_grid_backtest.py      # Grid Trading
python3 run_oos_validation.py     # Out-of-sample validation
```

**Emergency kill switch:**

```bash
python3 live/execution/kill_switch.py status   # Check drawdown
python3 live/execution/kill_switch.py check    # Health check
python3 live/execution/kill_switch.py kill     # FLATTEN ALL POSITIONS
```

---

## Risk Framework

| Parameter | Limit |
|---|---|
| Max position size | 30% of account per asset |
| Max drawdown trigger | 15% from high-water mark → go to cash |
| Per-trade stop-loss | 8% maximum |
| Cash reserve | Minimum 20% at all times |
| Leverage | None (spot only) |

---

## Key Files

| File | Purpose |
|---|---|
| `live/monitor/market_monitor.py` | Main daemon — price polling, Discord alerts, grid fill detection |
| `live/monitor/macro_calendar.json` | Upcoming macro events (CPI, FOMC, NFP dates) |
| `live/monitoring/dashboard.py` | P&L dashboard with live price fetches |
| `live/monitoring/trade_logger.py` | Append trades to CSV log |
| `live/execution/kill_switch.py` | Emergency position flattening via Kraken API |
| `live/execution/risk_manager.py` | Drawdown checks and risk state management |
| `live/paper_trading/track_manager.py` | Paper trade entry, exit, and P&L tracking |
| `live/paper_trading/grid_paper_trader.py` | Grid trading engine (paper mode) |
| `live/config/risk_state.json` | Current risk state (HWM, drawdown, sizing) |
| `market_data/schema.sql` | SQLite schema for all 14 tables |
| `market_data/collect.py` | Market data collection CLI |
| `backtest/run_backtest.py` | Macro Swing strategy backtest |
| `docs/strategy-plan.md` | Full strategy documentation |
| `docs/risk-framework.md` | Risk management rules |
| `docs/operations.md` | Operations runbook |

---

## Links

- [Architecture](docs/architecture.md)
- [Data Dictionary](docs/data-dictionary.md)
- [Operations Runbook](docs/operations.md)
- [Strategy Plan](docs/strategy-plan.md)
- [Risk Framework](docs/risk-framework.md)
- [Market Regime Analysis](docs/market-regime.md)
- [Improvement Process](docs/improvement-process.md)
- [Exchange Evaluation](research/exchange-evaluation.md)
- [Backtest Results](backtest/results/)
- [Signal Research](research/signals/)

---

## Project Phases

| Phase | Status | Description |
|---|---|---|
| 1. Research & Strategy Design | ✅ Complete | 11 signal research papers, 7+ strategies designed |
| 2. Backtest | ✅ Complete | 12 strategies backtested, OOS validation done |
| 3. Paper Trade | 🟡 Active | 3 tracks live since 2026-03-11 |
| 4. Exchange Setup | ✅ Complete | Kraken API integrated, kill switch live |
| 5. Go Live (Gradual) | ⬜ Pending | 25% → 50% → 100% over 3 weeks (awaiting paper results) |
| 6. Monitoring & Operations | ✅ Complete | Dashboard, trade logger, market monitor daemon |
| 7. Continuous Improvement | 🟡 Active | Research → backtest → paper → evaluate loop |

---

*Private project. Not financial advice.*
