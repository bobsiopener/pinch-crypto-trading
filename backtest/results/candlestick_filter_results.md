# Candlestick Pattern Filter — Backtest Results

**Generated:** 2026-03-11 05:04 UTC  
**Period:** 2022-01-01 → 2026-03-01  
**Initial Capital:** $100,000.00  
**Confirmation Window:** Up to 3 trading days  

---

## Summary: Baseline vs Filtered

| Metric | BASELINE | FILTERED | Δ |
|--------|----------|----------|---|
| Final Value | $105,228.04 | $104,550.18 | $-677.85 |
| Total Return | 5.23% | 4.55% | -0.68% |
| Annualized Return | 1.23% | 1.07% | -0.16% |
| Max Drawdown | 3.33% | 1.68% | -1.65% |
| Sharpe Ratio | 1.403 | 1.312 | -0.090 |
| Number of Trades | 10 | 10 | — |
| Win Rate | 70.00% | 60.00% | -10.00% |
| Avg Win | 7.25% | 7.02% | -0.23% |
| Avg Loss | -8.40% | -5.13% | 3.27% |
| Profit Factor | 2.015 | 2.053 | +0.038 |

**Buy & Hold BTC:** 37.85% ($137,853.84)

---

## Entry Price Improvement Analysis

> When the filtered strategy waits for candlestick confirmation, does it get a better entry price?

| Metric | Value |
|--------|-------|
| Trades that waited (delayed entry) | 10 |
| Average entry price change vs signal day | -0.95% |
| Entered at lower price (better) | 3 trades |
| Entered at higher price (market ran) | 7 trades |

⚠️ Filtered strategy entered at a **higher** average price (market ran away)

---

## Candlestick Confirmation Stats (Filtered)

| Metric | Value |
|--------|-------|
| Trades with confirmation | 5 |
| Trades without (timeout) | 5 |
| Win Rate (confirmed) | 80.00% |
| Win Rate (timed out) | 40.00% |

### Pattern Frequencies
- `[timeout]`: 5
- `[bullish_engulfing]`: 4
- `[hammer, doji]`: 1

---

## Exit Reason Breakdown

| Exit Reason | BASELINE | FILTERED |
|-------------|----------|----------|
| stop_loss | 3 | 2 |
| time_stop | 7 | 8 |


---

## Baseline Trade Log

| # | Signal Date | Entry Date | Entry $ | Exit $ | PnL% | Exit Reason | CS Pattern |
|---|-------------|------------|---------|--------|------|-------------|------------|
| 1 | 2024-06-12 | 2024-06-12 | $68,241.19 | $62,781.89 | -8.40% | stop_loss | (baseline — no filter) |
| 2 | 2024-07-11 | 2024-07-11 | $57,344.91 | $65,777.23 | 15.28% | time_stop | (baseline — no filter) |
| 3 | 2024-08-14 | 2024-08-14 | $58,737.27 | $59,027.62 | 0.09% | time_stop | (baseline — no filter) |
| 4 | 2024-09-11 | 2024-09-11 | $57,343.17 | $63,143.14 | 9.71% | time_stop | (baseline — no filter) |
| 5 | 2025-03-12 | 2025-03-12 | $83,722.36 | $86,900.88 | 3.40% | time_stop | (baseline — no filter) |
| 6 | 2025-04-10 | 2025-04-10 | $79,626.14 | $93,943.80 | 16.59% | time_stop | (baseline — no filter) |
| 7 | 2025-05-13 | 2025-05-13 | $104,169.81 | $108,994.64 | 4.23% | time_stop | (baseline — no filter) |
| 8 | 2025-06-11 | 2025-06-11 | $108,686.62 | $99,991.70 | -8.40% | stop_loss | (baseline — no filter) |
| 9 | 2025-08-12 | 2025-08-12 | $120,172.91 | $110,559.07 | -8.40% | stop_loss | (baseline — no filter) |
| 10 | 2025-09-17 | 2025-09-17 | $116,468.51 | $118,648.93 | 1.47% | time_stop | (baseline — no filter) |

---

## Filtered Trade Log

| # | Signal Date | Entry Date | Days Waited | Entry $ | Exit $ | PnL% | Exit Reason | CS Confirmed | CS Pattern |
|---|-------------|------------|-------------|---------|--------|------|-------------|--------------|------------|
| 1 | 2024-06-12 | 2024-06-15 | 3d | $66,191.00 | $60,895.72 | -8.40% | stop_loss | ❌ NO | [timeout] |
| 2 | 2024-07-11 | 2024-07-12 | 1d | $57,899.46 | $67,912.06 | 16.32% | time_stop | ✅ YES | [bullish_engulfing] |
| 3 | 2024-08-14 | 2024-08-17 | 3d | $59,478.97 | $58,969.90 | -1.26% | time_stop | ❌ NO | [timeout] |
| 4 | 2024-09-11 | 2024-09-14 | 3d | $60,005.12 | $65,887.65 | 9.40% | time_stop | ❌ NO | [timeout] |
| 5 | 2025-03-12 | 2025-03-15 | 3d | $84,343.11 | $82,597.59 | -2.47% | time_stop | ❌ NO | [timeout] |
| 6 | 2025-04-10 | 2025-04-11 | 1d | $83,404.84 | $94,720.50 | 13.17% | time_stop | ✅ YES | [bullish_engulfing] |
| 7 | 2025-05-13 | 2025-05-16 | 3d | $103,489.29 | $103,998.57 | 0.09% | time_stop | ❌ NO | [timeout] |
| 8 | 2025-06-11 | 2025-06-13 | 2d | $106,090.97 | $107,088.43 | 0.54% | time_stop | ✅ YES | [hammer, doji] |
| 9 | 2025-08-12 | 2025-08-13 | 1d | $123,344.06 | $113,476.54 | -8.40% | stop_loss | ✅ YES | [bullish_engulfing] |
| 10 | 2025-09-17 | 2025-09-18 | 1d | $117,137.20 | $120,681.26 | 2.63% | time_stop | ✅ YES | [bullish_engulfing] |

---

## Verdict

- ⚠️ Win rate decreased by 10.00% — filter may be skipping good setups
- ➡️ Total return similar (-0.68% delta)
- ➡️ Max drawdown similar (-1.65% delta)

**Recommendation:** The baseline strategy is preferred; the candlestick filter delays entries without sufficient benefit.

---

> *Rule of Acquisition #22: A wise man can hear profit in the wind.*  
> *But a smart Ferengi waits for the candle to confirm it.*
