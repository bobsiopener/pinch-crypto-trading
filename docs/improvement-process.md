# Continuous Improvement Process

This document defines the ongoing research and improvement cycle that runs in parallel with live trading. The goal is to systematically discover, validate, and integrate strategy improvements without disrupting live operations.

## Philosophy

> *"Rule of Acquisition #9: Opportunity plus instinct equals profit. But opportunity plus data equals more profit."*

Live trading generates real-world data. That data feeds back into research. Research produces improvements. Improvements are validated before deployment. This is the feedback loop that compounds our edge over time.

## The Improvement Cycle

```
┌─────────────────────────────────────────────────────────┐
│                    LIVE TRADING                          │
│    (generates trade data, P&L, market observations)     │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│              1. IDENTIFY OPPORTUNITY                     │
│    - Performance review reveals weakness                 │
│    - New signal source discovered                        │
│    - Market regime shift requires adaptation             │
│    - External research suggests improvement              │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│              2. RESEARCH & INVESTIGATE                    │
│    - Literature review (academic, practitioner)          │
│    - Data collection and signal analysis                 │
│    - Statistical significance testing                    │
│    - Document findings in research/ directory            │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│              3. BACKTEST                                  │
│    - Implement strategy modification in code             │
│    - Run against historical data (2020-2026)             │
│    - Compare to current strategy performance             │
│    - Out-of-sample validation (train on 2020-2024,       │
│      test on 2025-2026)                                  │
│    - Document results in backtest/results/               │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
                   Pass backtest?
                   │           │
                   No          Yes
                   │           │
                   ▼           ▼
              Archive    ┌─────────────────────────────────┐
              findings   │     4. PAPER TRADE                │
                         │    - Run improvement alongside    │
                         │      live strategy for 2-4 weeks  │
                         │    - Compare real-time execution   │
                         │    - Measure slippage, latency     │
                         │    - Log in paper-trade/logs/      │
                         └──────────────┬──────────────────┘
                                        │
                                        ▼
                                   Pass paper?
                                   │           │
                                   No          Yes
                                   │           │
                                   ▼           ▼
                              Archive    ┌─────────────────┐
                              findings   │  5. EVALUATE     │
                                         │  - Compare vs.   │
                                         │    live results   │
                                         │  - Risk-adjusted  │
                                         │    returns        │
                                         │  - Drawdown       │
                                         │    comparison     │
                                         │  - Statistical    │
                                         │    significance   │
                                         └────────┬────────┘
                                                  │
                                                  ▼
                                             Better?
                                             │       │
                                             No      Yes
                                             │       │
                                             ▼       ▼
                                        Archive  ┌──────────────┐
                                                 │ 6. PROPOSE   │
                                                 │ - Write up   │
                                                 │   findings   │
                                                 │ - Create PR  │
                                                 │ - Bob reviews │
                                                 │ - If approved │
                                                 │   → integrate │
                                                 └──────┬───────┘
                                                        │
                                                        ▼
                                              ┌──────────────────┐
                                              │  7. INTEGRATE     │
                                              │  - Merge to main  │
                                              │  - Update live     │
                                              │    trading rules   │
                                              │  - Monitor for     │
                                              │    2 weeks post    │
                                              │  - Confirm no      │
                                              │    regression      │
                                              └──────────────────┘
                                                        │
                                                        ▼
                                              (Back to LIVE TRADING)
```

## Research Areas

### Signal Research
Investigate new signals that could improve entry/exit timing:

| Research Area | Description | Priority |
|--------------|-------------|----------|
| On-chain metrics | Whale movements, exchange inflows/outflows, MVRV ratio | High |
| Funding rate signals | Futures funding rate as contrarian indicator | High |
| Options skew | Put/call ratio, implied volatility term structure | Medium |
| Sentiment analysis | Crypto Twitter sentiment, Fear & Greed | Medium |
| Cross-asset signals | DXY, gold, yield curve as leading indicators for BTC | High |
| Kalshi integration | Prediction market odds as probability-weighted signal | Medium |
| ETF flow momentum | 5-day rolling ETF flow as trend confirmation | High |
| Liquidation data | Leverage flush signals (cascading liquidations) | Medium |

### Regime Detection Research
Improve ability to identify and react to market regime changes:

| Research Area | Description | Priority |
|--------------|-------------|----------|
| Hidden Markov Models | Statistical regime detection from price/volume data | Medium |
| Correlation regime | Dynamic BTC-equity correlation as regime signal | High |
| Volatility regime | Realized vs. implied vol ratio for regime shifts | Medium |
| Macro regime scoring | Formalize the Operation Latinum Rush framework into code | High |

### Execution Research
Reduce trading costs and improve fill quality:

| Research Area | Description | Priority |
|--------------|-------------|----------|
| Optimal order type | Limit vs. TWAP vs. iceberg for different sizes | Medium |
| Time-of-day effects | When does BTC have best liquidity/lowest spreads? | Low |
| Slippage analysis | Actual fill vs. signal price over time | High |
| Fee optimization | Maker vs. taker, exchange fee tiers | Medium |

### Risk Research
Improve risk management and drawdown prevention:

| Research Area | Description | Priority |
|--------------|-------------|----------|
| Dynamic position sizing | Kelly criterion, volatility-adjusted sizing | High |
| Correlation-based limits | Adjust max exposure when BTC-equity correlation spikes | Medium |
| Stop-loss optimization | Fixed % vs. ATR-based vs. support-level stops | High |
| Drawdown prediction | Early warning signals for large drawdowns | Medium |

## Improvement Tracking

### GitHub Issue Labels

| Label | Meaning |
|-------|---------|
| `research` | New research investigation |
| `backtest` | Ready for / in backtest phase |
| `paper-trade` | In paper trading validation |
| `evaluate` | Under evaluation vs. live strategy |
| `proposed` | Ready for Bob's review |
| `approved` | Approved, awaiting integration |
| `integrated` | Merged into live strategy |
| `archived` | Did not pass validation — kept for reference |

### Improvement Log

Every improvement attempt is tracked:

```markdown
## Improvement: [Name]
- **Issue:** #XX
- **Hypothesis:** [What we think will improve]
- **Backtest result:** [Win rate, return, Sharpe, drawdown vs. baseline]
- **Paper trade result:** [Real-time performance over X days]
- **Decision:** Integrate / Archive
- **Reason:** [Why]
```

## Schedule

| Cadence | Activity |
|---------|----------|
| Daily | Review trade execution for improvement signals |
| Weekly | Pick 1-2 research items to investigate |
| Bi-weekly | Run backtests on any promising research |
| Monthly | Full strategy performance review + improvement proposals |
| Quarterly | Major strategy review — consider adding/removing strategy types |

## Rules

1. **Never change the live strategy without going through the full cycle** (research → backtest → paper → evaluate → propose → approve → integrate)
2. **Improvements must be statistically significant** — not just "it worked this one time"
3. **Document everything** — negative results are as valuable as positive ones
4. **One change at a time** — if you change 3 things and performance improves, you don't know which one worked
5. **Regression testing** — after any integration, monitor for 2 weeks to confirm no degradation
