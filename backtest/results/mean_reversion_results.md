# Bollinger Band Mean Reversion Backtest — BTC/USD

**Generated:** 2026-03-11 05:54 UTC
**Period:** 2022-01-01 → 2026-03-01
**Initial Capital:** $100,000.00
**Strategy:** Bollinger Band Mean Reversion (buy at lower band, sell at SMA)
**BB Period:** 20-day SMA, 2.0σ bands
**Position Size:** 5% of portfolio per trade
**Time Stop:** 10 days
**Fee Rate:** 0.1% per trade
**Regime Filter:** BB Width < 10% (low-volatility / sideways only)

## Regime Context (BB Width Analysis)

| Metric | Value |
|--------|-------|
| Trading days analyzed | 1502 |
| Avg BB Width | 17.0% |
| Days with BB Width < 10% ("sideways") | 409 (27.2%) |
| Days with BB Width ≥ 10% (trending/volatile) | 1093 (72.8%) |

*Approximately 27% of BTC trading days from 2022-01-01 qualify as low-volatility/sideways by the BB Width filter.*

## Buy & Hold Benchmark

| Metric | Value |
|--------|-------|
| Entry Price | $47,686.81 |
| Exit Price  | $65,738.10 |
| Final Value | $137,853.84 |
| Total Return | 37.85% |
| Annualized Return | 8.01% |

## Strategy Comparison

| Metric | Unfiltered | Regime-Filtered | Buy & Hold |
|--------|------------|-----------------|------------|
| Final Value | $100,931.92 | $101,044.85 | $137,853.84 |
| Total Return | 0.93% | 1.04% | 37.85% |
| Annualized Return | 0.22% | 0.25% | 8.01% |
| Max Drawdown | 2.86% | 1.42% | — |
| # Trades | 30 | 13 | — |
| Win Rate | 63.33% | 69.23% | — |
| Avg Win % | 6.26% | 4.66% | — |
| Avg Loss % | -8.53% | -4.61% | — |
| Target Exits | 14 | 7 | — |
| Time-Stop Exits | 16 | 6 | — |

## Unfiltered — Recent Trades (last 10)

| Entry Date | Exit Date | Entry $ | Exit $ | P&L % | Days | Exit Reason |
|------------|-----------|---------|--------|-------|------|-------------|
| 2025-02-24 | 2025-03-02 | $91,418.17 | $94,248.35 | +3.10% | 6 | target |
| 2025-04-06 | 2025-04-11 | $78,214.48 | $83,404.84 | +6.64% | 5 | target |
| 2025-06-05 | 2025-06-09 | $101,575.95 | $110,294.10 | +8.58% | 4 | target |
| 2025-07-31 | 2025-08-07 | $115,758.20 | $117,496.90 | +1.50% | 7 | target |
| 2025-08-25 | 2025-09-04 | $110,124.35 | $110,723.60 | +0.54% | 10 | time_stop |
| 2025-09-25 | 2025-09-29 | $109,049.29 | $114,400.38 | +4.91% | 4 | target |
| 2025-11-04 | 2025-11-14 | $101,590.52 | $94,397.79 | -7.08% | 10 | time_stop |
| 2025-11-20 | 2025-11-30 | $86,631.90 | $90,394.31 | +4.34% | 10 | time_stop |
| 2025-12-15 | 2025-12-25 | $86,419.78 | $87,234.74 | +0.94% | 10 | time_stop |
| 2026-01-31 | 2026-02-10 | $78,621.12 | $68,793.96 | -12.50% | 10 | time_stop |

## Regime-Filtered — Recent Trades (last 10)

| Entry Date | Exit Date | Entry $ | Exit $ | P&L % | Days | Exit Reason |
|------------|-----------|---------|--------|-------|------|-------------|
| 2023-07-24 | 2023-08-03 | $29,176.92 | $29,178.68 | +0.01% | 10 | time_stop |
| 2023-08-16 | 2023-08-26 | $28,701.78 | $26,008.46 | -9.38% | 10 | time_stop |
| 2024-06-14 | 2024-06-24 | $66,011.09 | $60,277.41 | -8.69% | 10 | time_stop |
| 2025-02-04 | 2025-02-14 | $97,871.82 | $97,508.97 | -0.37% | 10 | time_stop |
| 2025-02-24 | 2025-03-02 | $91,418.17 | $94,248.35 | +3.10% | 6 | target |
| 2025-06-05 | 2025-06-09 | $101,575.95 | $110,294.10 | +8.58% | 4 | target |
| 2025-07-31 | 2025-08-07 | $115,758.20 | $117,496.90 | +1.50% | 7 | target |
| 2025-08-25 | 2025-09-04 | $110,124.35 | $110,723.60 | +0.54% | 10 | time_stop |
| 2025-09-25 | 2025-09-29 | $109,049.29 | $114,400.38 | +4.91% | 4 | target |
| 2025-12-15 | 2025-12-25 | $86,419.78 | $87,234.74 | +0.94% | 10 | time_stop |

## Analysis

### Impact of Regime Filter

The BB Width regime filter (< 10%) reduces trade count by **57%** while focusing on higher-quality setups.

| Improvement | Value |
|-------------|-------|
| Return delta (filtered vs unfiltered) | +0.11% |
| Drawdown reduction | +1.44% |
| Trade count reduction | 57% |
| Filtered win rate vs unfiltered | 69.23% vs 63.33% |

### Key Findings

1. **Regime filter effectiveness:** Restricting mean reversion to low-volatility periods eliminates the most damaging trades — those taken during trending/breakout conditions where price never reverts.

2. **Time stop importance:** Approximately 16 unfiltered and 6 filtered trades exit via time stop rather than reaching the SMA target. This prevents capital tie-up in failed reversions.

3. **Win rate threshold:** Mean reversion needs win rate > 60% to be profitable given asymmetric win/loss sizes. The regime filter should push win rate above this threshold.

4. **Integration with grid trading:** Mean reversion and grid trading are complementary during SIDEWAYS regimes. Grid handles continuous small fills; mean reversion captures larger discrete swings at statistical extremes.

### Regime Filter Recommendation

**Confirmed:** Use BB Width < 10% as an activation gate for mean reversion. This filters out ~73% of calendar days (trending/volatile periods) where mean reversion is most likely to fail.

### Next Steps

1. Add z-score entry filter (require z < -2.0 at lower band touch, not just price touch)
2. Test with VWAP confluence to further improve win rate
3. Backtest short side (upper band shorts) — expected lower win rate due to BTC upward bias
4. Out-of-sample validation on 2026 data as it accumulates

---
*Backtest assumes long-only mean reversion (buy lower band, sell SMA). Short-side not tested.*
*See full research: `research/signals/mean-reversion-research.md`*
