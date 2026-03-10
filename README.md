# 🪙 Pinch Crypto Trading System

> *"Rule of Acquisition #22: A wise man can hear profit in the wind."*

An AI-driven macro swing trading system for cryptocurrency markets, operated by **Pinch** (Chief of Finance, USS Clawbot).

## Overview

This project implements a systematic crypto trading strategy that combines macroeconomic analysis with technical signals to generate alpha in BTC, ETH, and SOL markets. The system is designed to be operated by an AI agent (Pinch) with human oversight.

## Strategy

**Core Approach:** Macro-Driven Swing Trading
- Hold periods: 2-14 days
- Primary signals: CPI, FOMC, NFP, geopolitical events, ETF flows
- Secondary signals: Technical levels, momentum, mean reversion at extremes
- Universe: BTC, ETH, SOL (core); selective alts

## Project Phases

| Phase | Status | Description |
|-------|--------|-------------|
| 1. Research & Strategy Design | 🟡 In Progress | Strategy universe analysis, market regime assessment |
| 2. Backtest | ⬜ Not Started | Historical validation against 2020-2026 data |
| 3. Paper Trade | ⬜ Not Started | Real-time validation without capital at risk |
| 4. Exchange Setup | ⬜ Not Started | API integration, security, order execution |
| 5. Go Live (Gradual) | ⬜ Not Started | 25% → 50% → 100% position sizing over 3 weeks |
| 6. Monitoring & Operations | ⬜ Not Started | Daily P&L, risk management, trade logging |
| 7. Continuous Improvement | ⬜ Not Started | Research → backtest → paper → evaluate → propose |

## Project Structure

```
pinch-crypto-trading/
├── README.md
├── docs/
│   ├── strategy-plan.md          # Full strategy documentation
│   ├── risk-framework.md         # Risk management rules
│   ├── market-regime.md          # Current regime analysis
│   └── improvement-process.md    # Continuous improvement workflow
├── backtest/
│   ├── data/                     # Historical price data
│   ├── strategies/               # Strategy implementations
│   └── results/                  # Backtest output & analysis
├── paper-trade/
│   └── logs/                     # Paper trade execution logs
├── live/
│   ├── config/                   # Exchange config (NO secrets)
│   ├── execution/                # Order execution scripts
│   └── monitoring/               # Position & P&L tracking
├── research/
│   ├── signals/                  # Signal research & analysis
│   ├── regimes/                  # Market regime detection
│   └── experiments/              # Strategy experiments
└── logs/
    ├── trades/                   # Trade log (all trades, all phases)
    └── performance/              # Performance reports
```

## Risk Framework

- **Max position size:** 30% of account per asset
- **Max drawdown trigger:** 15% from high-water mark → go to cash
- **Per-trade stop-loss:** 8% maximum
- **Cash reserve:** Minimum 20% at all times
- **No leverage:** Spot trading only
- **Kill switch:** Human can flatten all positions immediately

## Links

- [Strategy Plan](docs/strategy-plan.md)
- [Risk Framework](docs/risk-framework.md)
- [Market Regime Analysis](docs/market-regime.md)
- [Improvement Process](docs/improvement-process.md)

## License

Private project. Not financial advice.
