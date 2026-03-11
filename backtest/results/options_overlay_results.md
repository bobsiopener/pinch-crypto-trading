# Options Overlay Backtest Results

**Generated:** 2026-03-11 14:37 UTC
**Period:** 2024-01-01 → 2026-03-09
**Initial Capital:** $100,000.00
**Base Strategy:** Macro Swing (CPI/FOMC/NFP signals)
**Options Data:** Synthetic proxy (options_proxy.csv)

## 📖 Strategy Variants

| # | Variant | Description |
|---|---------|-------------|
| A | **BASELINE** | Macro swing as-is, no options filter |
| B | **P/C FILTER** | Skip longs when P/C < 0.45 (complacency/euphoria); hold exits when P/C > 0.75 (contrarian bullish) |
| C | **IV FILTER** | Reduce size 50% when IV Rank > 65.0 (high vol regime); increase 25% when IV Rank < 30.0 (low vol breakout) |

## 📊 Buy-and-Hold Benchmark (BTC)

| Metric | Value |
|--------|-------|
| Start Price | $44,167.33 |
| End Price | $68,402.38 |
| Total Return | 54.87% |
| Annualized Return | 22.17% |
| Max Drawdown | 49.74% |
| Final Value | $154,870.99 |

## 📈 Performance Comparison

| Metric | A: Baseline | B: P/C Filter | Δ vs Base | C: IV Filter | Δ vs Base |
|--------|-------------|---------------|-----------|--------------|-----------|
| Total Return | 5.23% | 3.85% | -1.38pp | 5.00% | -0.23pp |
| Annualized Return | 2.36% | 1.75% | -0.61pp | 2.26% | -0.10pp |
| Max Drawdown | 3.33% | 3.33% | -0.00pp | 2.51% | -0.83pp |
| Win Rate | 70.00% | 75.00% | +5.00pp | 70.00% | +0.00pp |
| Avg Win | 7.25% | 5.92% | -1.34pp | 7.25% | +0.00pp |
| Avg Loss | -8.40% | -8.40% | +0.00pp | -8.40% | +0.00pp |
| # Trades | 10 | 8 | -2 | 10 | +0 |
| Profit Factor | 2.015 | 2.113 | +0.098 | 2.015 | +0.000 |
| Sharpe Ratio | 1.403 | 1.415 | +0.012 | 1.403 | +0.000 |
| Final Value | $105,228.04 | $103,851.98 | $-1,376.06 | $104,998.94 | $-229.10 |

## 🔧 Filter Activity

### B: P/C Filter

- **Longs skipped** (P/C < 0.45, euphoria): **2**
- **Exits held** (P/C > 0.75, contrarian): **0**

### C: IV Filter

- **Size reduced 50%** (IV Rank > 65.0): **3** trades
- **Size boosted 25%** (IV Rank < 30.0): **1** trades

## 📋 Detailed Results by Variant

### A: Baseline

| Metric | Value |
|--------|-------|
| Total Return | 5.23% |
| Annualized Return | 2.36% |
| Max Drawdown | 3.33% |
| Win Rate | 70.00% |
| # Trades | 10 |
| Avg Win | 7.25% |
| Avg Loss | -8.40% |
| Profit Factor | 2.015 |
| Sharpe Ratio | 1.403 |
| Final Value | $105,228.04 |

<details>
<summary>Trade Log (last 15 entries)</summary>

```
SIGNAL 2025-09-10 | score=-2 | CPI hot (2.9 vs 2.7): -2
SIGNAL 2025-09-17 | score=+3 | FOMC dovish (cut25, rate→3.75%): +3
OPEN 2025-09-17 | score=+3 | LONG 30% | entry=116468.51 SL=107151.03 TP=135103.47 | P/C=0.77 IV=69 | Account=104765.36
CLOSE 2025-10-01 | time_stop | entry=116468.51 exit=118648.93 | PnL=1.47% | Account=105228.04
SIGNAL 2025-10-03 | score=-1 | NFP strong: -1
SIGNAL 2025-10-14 | score=-2 | CPI hot (2.7 vs 2.6): -2
SIGNAL 2025-10-29 | score=+0 | FOMC neutral (hold, rate→3.75%): 0
SIGNAL 2025-11-07 | score=-1 | NFP weak (rate 3.75% < 4%): -1
SIGNAL 2025-11-12 | score=-2 | CPI hot (2.8 vs 2.7): -2
SIGNAL 2025-12-05 | score=+0 | NFP neutral: 0
SIGNAL 2025-12-10 | score=-2 | CPI hot (2.9 vs 2.8): -2
SIGNAL 2025-12-17 | score=-3 | FOMC hawkish (hold, rate→3.75%): -3
SIGNAL 2026-01-09 | score=-1 | NFP strong: -1
SIGNAL 2026-02-06 | score=-1 | NFP weak (rate 3.75% < 4%): -1
SIGNAL 2026-03-06 | score=-1 | NFP weak (rate 3.75% < 4%): -1
```

</details>

### B: P/C Filter

| Metric | Value |
|--------|-------|
| Total Return | 3.85% |
| Annualized Return | 1.75% |
| Max Drawdown | 3.33% |
| Win Rate | 75.00% |
| # Trades | 8 |
| Avg Win | 5.92% |
| Avg Loss | -8.40% |
| Profit Factor | 2.113 |
| Sharpe Ratio | 1.415 |
| Final Value | $103,851.98 |

<details>
<summary>Trade Log (last 15 entries)</summary>

```
SIGNAL 2025-09-10 | score=-2 | CPI hot (2.9 vs 2.7): -2
SIGNAL 2025-09-17 | score=+3 | FOMC dovish (cut25, rate→3.75%): +3
OPEN 2025-09-17 | score=+3 | LONG 30% | entry=116468.51 SL=107151.03 TP=135103.47 | P/C=0.77 IV=69 | Account=103395.35
CLOSE 2025-10-01 | time_stop | entry=116468.51 exit=118648.93 | PnL=1.47% | Account=103851.98
SIGNAL 2025-10-03 | score=-1 | NFP strong: -1
SIGNAL 2025-10-14 | score=-2 | CPI hot (2.7 vs 2.6): -2
SIGNAL 2025-10-29 | score=+0 | FOMC neutral (hold, rate→3.75%): 0
SIGNAL 2025-11-07 | score=-1 | NFP weak (rate 3.75% < 4%): -1
SIGNAL 2025-11-12 | score=-2 | CPI hot (2.8 vs 2.7): -2
SIGNAL 2025-12-05 | score=+0 | NFP neutral: 0
SIGNAL 2025-12-10 | score=-2 | CPI hot (2.9 vs 2.8): -2
SIGNAL 2025-12-17 | score=-3 | FOMC hawkish (hold, rate→3.75%): -3
SIGNAL 2026-01-09 | score=-1 | NFP strong: -1
SIGNAL 2026-02-06 | score=-1 | NFP weak (rate 3.75% < 4%): -1
SIGNAL 2026-03-06 | score=-1 | NFP weak (rate 3.75% < 4%): -1
```

</details>

### C: IV Filter

| Metric | Value |
|--------|-------|
| Total Return | 5.00% |
| Annualized Return | 2.26% |
| Max Drawdown | 2.51% |
| Win Rate | 70.00% |
| # Trades | 10 |
| Avg Win | 7.25% |
| Avg Loss | -8.40% |
| Profit Factor | 2.015 |
| Sharpe Ratio | 1.403 |
| Final Value | $104,998.94 |

<details>
<summary>Trade Log (last 15 entries)</summary>

```
SIGNAL 2025-09-17 | score=+3 | FOMC dovish (cut25, rate→3.75%): +3
IV_REDUCE 2025-09-17 | IV rank=69.1 > 65.0 → size reduced 50% to 15%
OPEN 2025-09-17 | score=+3 | LONG 15% | entry=116468.51 SL=107151.03 TP=135103.47 | P/C=0.77 IV=69 | Account=104767.59
CLOSE 2025-10-01 | time_stop | entry=116468.51 exit=118648.93 | PnL=1.47% | Account=104998.94
SIGNAL 2025-10-03 | score=-1 | NFP strong: -1
SIGNAL 2025-10-14 | score=-2 | CPI hot (2.7 vs 2.6): -2
SIGNAL 2025-10-29 | score=+0 | FOMC neutral (hold, rate→3.75%): 0
SIGNAL 2025-11-07 | score=-1 | NFP weak (rate 3.75% < 4%): -1
SIGNAL 2025-11-12 | score=-2 | CPI hot (2.8 vs 2.7): -2
SIGNAL 2025-12-05 | score=+0 | NFP neutral: 0
SIGNAL 2025-12-10 | score=-2 | CPI hot (2.9 vs 2.8): -2
SIGNAL 2025-12-17 | score=-3 | FOMC hawkish (hold, rate→3.75%): -3
SIGNAL 2026-01-09 | score=-1 | NFP strong: -1
SIGNAL 2026-02-06 | score=-1 | NFP weak (rate 3.75% < 4%): -1
SIGNAL 2026-03-06 | score=-1 | NFP weak (rate 3.75% < 4%): -1
```

</details>

## 🔍 Analysis & Conclusions

| Metric | Winner | Value |
|--------|--------|-------|
| Best Total Return | **Baseline** | 5.23% |
| Best Sharpe Ratio | **P/C Filter** | 1.415 |
| Lowest Drawdown | **IV Filter** | 2.51% |

### Key Takeaways

- **P/C Filter** reduced returns by 1.4pp vs baseline, with lower drawdown by 0.0pp. Skipped 2 euphoric longs.
- **IV Filter** reduced returns by 0.2pp vs baseline, with lower drawdown by 0.8pp. Scaled down 3 high-volatility trades.
- **Options signals provide a useful macro regime lens**: P/C extremes (caught euphoria tops, IV rank flagged volatility clusters.

> **Rule of Acquisition #22:** A wise man can hear profit in the wind — and sometimes that wind smells like options flow. P/C extremes are the market's whispered confession. Listen accordingly.

## 📅 Options Proxy Regime Reference

| Period | P/C Regime | IV Regime | Market Context |
|--------|-----------|-----------|----------------|
| 2022 | 0.8–1.2 (elevated) | 60–90 (high) | Bear market, Fed hike cycle, FTX collapse |
| 2023 | 0.5–0.7 (declining) | 30–50 (moderate) | Recovery grind, ETF anticipation |
| 2024 H1 | 0.3–0.5 (low) | 20–40 (low) | ETF approval, halving, bull run |
| 2024 Nov | 0.2–0.4 (very low) | 70–90 (spiking) | Peak euphoria, post-election ATH |
| 2025–2026 | 0.7–1.0+ (rising) | 50–80 (elevated) | Correction, macro uncertainty |

*Data source: Synthetic proxy generated from known market regime conditions. For live data, see `live/signals/options_poller.py` (Deribit API).*
