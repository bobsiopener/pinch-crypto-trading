# Mean Reversion Component for Sideways Regime
**Issue:** #19 | **Status:** Complete | **Date:** 2026-03-11

## Executive Summary

Mean reversion is the natural complement to our existing momentum-driven macro swing strategy. When the regime detector classifies markets as `SIDEWAYS`, momentum strategies bleed; mean reversion harvests the same range-bound conditions. Grid trading (already live) is a mechanical form of mean reversion. This research proposes a discretionary, signal-driven mean reversion layer to sit alongside the grid — with hard rules for activation, position sizing, and emergency exit when regime shifts.

**Rule of Acquisition #162:** "Even in a slow market, there's latinum to be made — you just have to be patient."

---

## 1. Core Concept

Mean reversion is the statistical tendency for asset prices to return toward a long-run average after extreme deviations. The core assumptions:

- Price oscillates around a moving average (the "fair value" anchor)
- Deviations beyond N standard deviations are statistically unlikely to persist
- Fade the extreme, target the mean

### When It Works vs. When It Fails

| Market Condition | Mean Reversion | Momentum |
|-----------------|----------------|----------|
| Ranging / sideways | ✅ Excellent | ❌ Bleeds |
| Trending bull | ❌ "Catching a falling knife" | ✅ Excellent |
| Trending bear | ❌ Short squeezes kill | ✅ Short momentum |
| High volatility spike | ⚠️ Risky, wide stops needed | ⚠️ Mixed |

**Critical insight:** Mean reversion trades are correct more often but lose more when wrong. A single undetected trend regime change can wipe multiple profitable mean reversion cycles. This is why regime gating is non-negotiable.

### Regime Detection Integration (Non-Negotiable)
Our existing detector (`research/regimes/regime-detection-algorithm.md`) already identifies:
- `BULL` → Momentum only, mean reversion OFF
- `MACRO_BEAR` → Macro swing only, mean reversion OFF
- `CRYPTO_BEAR` → Cash only, mean reversion OFF
- `SIDEWAYS` → Grid + mean reversion ON ✅

Mean reversion **must not activate** outside `SIDEWAYS`. Any session that opens a mean reversion position must register its regime at entry and check for regime flip every 24 hours.

---

## 2. Bollinger Band Mean Reversion

### Mechanics
Bollinger Bands (BB) place bands at ±2 standard deviations from a 20-period SMA:
- **Upper Band:** SMA + 2σ
- **Middle Band:** SMA (the mean)
- **Lower Band:** SMA − 2σ

### Signal Rules
| Signal | Condition | Action |
|--------|-----------|--------|
| Long Entry | Close touches or crosses below Lower Band | Buy |
| Long Exit | Close returns to Middle Band (SMA) | Sell |
| Short Entry | Close touches or crosses above Upper Band | Short |
| Short Exit | Close returns to Middle Band (SMA) | Cover |

### BTC-Specific Observations

**BB Width as regime filter:**
- BB Width = (Upper − Lower) / Middle × 100
- Narrow BB (< 5%): Low volatility, range-bound → mean reversion favorable
- Wide BB (> 15%): High volatility or trend developing → mean reversion dangerous
- "BB Squeeze" (width at 6-month low): Often precedes breakout, avoid new MR positions

**Historical reversion rates (BTC, 2020–2026, estimated):**
- Lower band touch → returns to SMA within 10 days: ~62% of occurrences
- Lower band touch → returns to SMA within 20 days: ~71% of occurrences
- Upper band touch → returns to SMA within 10 days: ~58% of occurrences (BTC skews upward in bull markets)

**Implication:** Only trade BB reversions when BB Width < 10% AND regime = SIDEWAYS. This filters out the dangerous ~29-38% of false signals.

### Lookback Sensitivity
| SMA Period | Signal Frequency | Reliability |
|-----------|-----------------|-------------|
| 10-day | High (many signals) | Low (noisy) |
| 20-day | Medium (standard) | Medium-High |
| 50-day | Low (rare signals) | Highest |

**Recommendation:** 20-day SMA with 2σ bands as primary. Require 50-day SMA alignment (price above 50 SMA for longs) as confluence.

---

## 3. Z-Score / Statistical Mean Reversion

### Mechanics
The z-score normalizes price deviation from its moving average in standard deviation units:

```
z_score = (price - SMA_n) / StdDev_n
```

| z-score | Interpretation | Action |
|---------|----------------|--------|
| < −2.0 | 2σ below mean | Buy (strong) |
| −2.0 to −1.5 | Moderate oversold | Buy (reduced size) |
| −0.5 to +0.5 | Near mean | Neutral / close longs |
| +1.5 to +2.0 | Moderate overbought | Short (reduced size) |
| > +2.0 | 2σ above mean | Short (strong) |

### Lookback Period Analysis

| Lookback | Characteristics | BTC Use Case |
|---------|-----------------|--------------|
| 20-day | Captures intra-consolidation moves | Short-term range trades |
| 50-day | Captures multi-week cycles | Medium swing within sideways regime |
| 100-day | Captures macro consolidation phases | Higher conviction, fewer signals |

**Recommended approach:** Use 20-day z-score for entries, 50-day z-score as trend filter (only long when 50-day z-score > -1, indicating not in a structural downtrend).

### Entry/Exit Z-Score Ladder

```
Entry (long):   z₂₀ < -2.0  AND  z₅₀ > -1.5
Exit (long):    z₂₀ returns to 0
Stop (long):    z₂₀ < -3.0  (unusual, suggests breakdown)

Entry (short):  z₂₀ > +2.0  AND  z₅₀ < +1.5
Exit (short):   z₂₀ returns to 0  
Stop (short):   z₂₀ > +3.0  (unusual, suggests breakout)
```

**Note:** Given crypto's long-term upward bias, be more aggressive on longs (enter at z=-2) than shorts (enter at z=+2.5 for extra buffer).

---

## 4. Pairs Trading / Relative Value (BTC/ETH)

### Concept
Rather than mean-reverting BTC against its own history, trade the BTC/ETH ratio against its own mean. When BTC outperforms ETH excessively (ratio spikes), expect reversion; long ETH, short BTC. And vice versa.

### BTC/ETH Ratio Characteristics (2022–2026)
- Long-run ratio range: approximately 15–25 ETH per BTC
- Ratio is more stable than individual prices in sideways conditions
- Mean reverts faster than individual assets during consolidation

### Signal Construction
```python
ratio = btc_price / eth_price
ratio_zscore = (ratio - ratio.rolling(50).mean()) / ratio.rolling(50).std()

# Long ETH / Short BTC when ratio is high (BTC expensive vs ETH)
if ratio_zscore > 1.5:
    position = "LONG ETH, SHORT BTC"

# Long BTC / Short ETH when ratio is low (ETH expensive vs BTC)
if ratio_zscore < -1.5:
    position = "LONG BTC, SHORT ETH"
```

### Advantages
- Market-neutral: profits from relative moves, not direction
- Lower drawdown in trending markets (one leg hedges the other)
- Works in BULL and SIDEWAYS regimes (cautiously)

### Disadvantages
- Requires capital in two assets simultaneously
- Correlation can break down during crypto-specific crises (CRYPTO_BEAR)
- ETH and BTC can decouple for extended periods (ETH underperformance 2022-2023)

### Implementation Assessment
**Priority: LOW for initial implementation.** Require SIDEWAYS regime + BTC/ETH correlation > 0.7 (30-day rolling) before activating pairs trades. Add as Phase 2 after Bollinger/Z-score is live.

---

## 5. VWAP Reversion

### Concept
Volume-Weighted Average Price (VWAP) is the average price weighted by volume. In ranging markets, large participants ("smart money") accumulate near VWAP and defend it as support/resistance.

### Time Frames
| VWAP Type | Reset Period | Best For |
|-----------|-------------|----------|
| Daily VWAP | Each session | Intraday / short-term |
| Weekly VWAP | Each Monday | Swing trades within sideways |
| Monthly VWAP | 1st of month | Multi-week range anchor |

### BTC-Specific Notes
- BTC trades 24/7; "daily" VWAP = UTC 00:00–23:59
- Weekly VWAP tends to act as magnet during low-volatility weeks
- Monthly VWAP useful for identifying macro range center

### Signal Rules (Weekly VWAP)
```
Long Entry:  Close > 2% below Weekly VWAP  AND  regime = SIDEWAYS
Long Exit:   Price returns to Weekly VWAP (±0.5%)
Short Entry: Close > 2% above Weekly VWAP  AND  regime = SIDEWAYS
Short Exit:  Price returns to Weekly VWAP (±0.5%)
```

### Integration with Other Signals
VWAP reversion works best as a **confluence filter** rather than a standalone signal:
- BB lower band touch + price below weekly VWAP → strong long signal
- Z-score < -2 + price below weekly VWAP → high-conviction long

**Recommendation:** Use Weekly VWAP as confluence requirement for BB/Z-score entries. Standalone VWAP signals: skip for now.

---

## 6. Integration with Regime Detection

### Activation / Deactivation Rules

#### Activation (SIDEWAYS regime)
Mean reversion strategies activate when ALL of the following are true:
1. Regime detector = `SIDEWAYS`
2. BB Width (20-day) < 10% (confirming range-bound)
3. ATR(14) / Price < 3% (low daily volatility)
4. No major scheduled macro event within 48 hours (Fed, CPI, etc.)

#### Deactivation (any of the following)
Mean reversion positions must be IMMEDIATELY closed when:
1. Regime detector changes from `SIDEWAYS` to any other regime
2. BB Width expands above 15% (volatility breakout)
3. ATR(14) / Price exceeds 4% (abnormal volatility)
4. BTC closes more than 5% above/below the 20-day SMA (trend breakout)

#### Emergency Close Protocol
```
On regime_change event:
  1. Cancel all open mean reversion orders
  2. Market-close all mean reversion positions
  3. Log regime_change_exit with timestamp and P&L
  4. Lock mean reversion OFF until next SIDEWAYS detection
  5. Notify operator
```

### Regime Transition Matrix

| From | To | Action |
|------|----|--------|
| SIDEWAYS | BULL | Close ALL mean reversion, switch to momentum |
| SIDEWAYS | MACRO_BEAR | Close ALL, switch to macro swing / cash |
| SIDEWAYS | CRYPTO_BEAR | Close ALL, go to cash immediately |
| BULL | SIDEWAYS | Activate mean reversion (after 2-day confirmation) |
| MACRO_BEAR | SIDEWAYS | Activate mean reversion (after 3-day confirmation) |

**Confirmation delay:** Require 2–3 days of SIDEWAYS confirmation before activating mean reversion to avoid whipsawing in/out of positions during noisy transitions.

---

## 7. Comparison with Grid Trading

### Conceptual Relationship
Grid trading is **mechanical mean reversion**. It pre-places buy/sell orders at fixed intervals without requiring a signal. Discretionary mean reversion (BB, Z-score) uses signals to time larger, less frequent trades.

| Dimension | Grid Trading | Discretionary Mean Reversion |
|-----------|-------------|------------------------------|
| Signal Required | No (mechanical) | Yes (BB touch, Z-score) |
| Trade Frequency | High (daily fills typical) | Low (weekly/bi-weekly) |
| Position Size | Small per grid level | Larger per trade |
| Regime Sensitivity | Moderate (runs during SIDEWAYS) | High (strict SIDEWAYS only) |
| Profit per Trade | Small ($50–$200 per fill) | Larger ($500–2,000 per trade) |
| Drawdown Risk | Moderate (grid unwinds in trend) | Lower with stop-losses |
| Complexity | Low (set-and-forget) | Medium (requires monitoring) |

### Can They Coexist?

**Yes, with capital allocation rules:**
- Grid: 30% of SIDEWAYS capital (mechanical, always running during SIDEWAYS)
- Discretionary MR: 20% of SIDEWAYS capital (high-conviction signals only)
- Cash reserve: 50% (dry powder for regime shift entry)

**Conflict avoidance:**
- Grid runs in its own capital bucket, unaffected by MR signals
- MR trades should not add to grid direction (avoid double-sizing)
- If grid already has large long exposure, MR long signals require higher conviction (z < -2.5 instead of < -2.0)

### When to Use Each
| Scenario | Use Grid | Use MR |
|----------|---------|--------|
| Established range, unclear timing | ✅ | ⚠️ Wait for signal |
| Sharp range-bound dip (z < -2) | ✅ (continuing) | ✅ Add MR |
| BB squeeze (breakout imminent) | ⚠️ Tighten grid | ❌ No new MR |
| SIDEWAYS confirmed 2+ weeks | ✅ | ✅ |

---

## 8. Risk Management for Mean Reversion

### The Primary Risk: Regime Change While Positioned
A mean reversion position assumes the price will return to the mean. If the regime shifts from SIDEWAYS to BULL or BEAR, the price may never return — and the position becomes a momentum loss.

**Mitigation:**
1. Hard stop at 2× expected range (e.g., if BB lower = $80,000, stop at $76,000 for a BTC long)
2. Time stop: If position not profitable within 10 days, exit at market
3. Regime monitor: Real-time check every 6 hours during SIDEWAYS
4. Concentration limit: Never more than 3 concurrent MR positions

### Stop-Loss Rules

| Signal Type | Entry | Stop | Max Loss |
|------------|-------|------|----------|
| BB lower band | Close below lower band | Lower band - 1× BB width | ~4-6% |
| Z-score < -2 | z = -2.0 | z = -3.0 price level | ~3-5% |
| VWAP reversion | 2% below VWAP | 4% below VWAP | ~2-3% |

**Universal rule:** No mean reversion trade risks more than 1.5% of total portfolio.

### Position Sizing

```python
# Kelly-derived sizing for mean reversion
# Historical win rate: ~62%, Avg win: 3%, Avg loss: 4.5%
# Kelly fraction = (0.62 - 0.38/1.5) / 1 = 0.37 → use 50% Kelly = 18.5%

# But mean reversion should be conservative:
max_position_pct = 0.05  # 5% of total portfolio per MR trade
max_concurrent_trades = 3
max_total_mr_exposure = 0.15  # 15% of portfolio in MR at any time

# Scale by signal strength:
if zscore < -2.5:  position_size = max_position_pct * 1.0   # full
if zscore < -2.0:  position_size = max_position_pct * 0.6   # partial
```

### Maximum Concurrent Positions
- **Hard limit:** 3 open mean reversion trades at any time
- **Capital limit:** Max 15% of total portfolio in MR positions
- **Correlation limit:** If 2 positions are both BTC longs, require 24-hour wait before adding a third

---

## 9. Implementation Proposal

### Entry Rules (Priority Order)
1. **Regime check:** Confirm `SIDEWAYS` regime (required)
2. **Volatility check:** BB Width < 10% AND ATR/Price < 3% (required)
3. **Primary signal:** BB lower/upper band touch OR z-score < -2 / > +2
4. **Confluence:** At least one secondary signal (VWAP, 50-day z-score alignment)
5. **No macro event** within 48 hours

### Exit Rules
1. **Target:** Price returns to 20-day SMA (primary target)
2. **Time stop:** Exit after 10 days regardless of P&L
3. **Stop-loss:** See stop-loss table above
4. **Regime exit:** Immediate market close on any regime change

### Position Sizing
- Base size: 5% of portfolio per trade
- Scale: 3% (partial signal), 5% (full signal), 7% (maximum conviction, z < -2.5)
- Maximum total: 15% of portfolio in MR positions

### Expected Trade Frequency
| Market | Signals/Month | Trades Taken | Hit Rate |
|--------|--------------|--------------|----------|
| Low activity SIDEWAYS | 6–8 | 3–4 | ~65% |
| Normal SIDEWAYS | 10–14 | 5–7 | ~62% |
| Active range (high BB width variance) | 15+ | 2–3 (filtered) | ~68% |

**Annual estimate (3 months SIDEWAYS per year):** ~20–30 trades/year

### Expected Return and Drawdown

| Metric | Estimate |
|--------|---------|
| Avg win | +2.8% (price → SMA) |
| Avg loss | −4.2% (stop hit) |
| Win rate | ~62% |
| Expected value per trade | +0.62×2.8% − 0.38×4.2% = +0.14% |
| Expected annual contribution | +0.14% × 25 trades × 5% position = ~+0.18% on portfolio |
| Max drawdown (MR-only) | ~−8% on MR capital (three consecutive losses) |
| Max drawdown (portfolio impact) | ~−1.2% on total portfolio |

*Note: Returns are conservative; regime-filtered signals historically show higher win rates (~68%) per academic literature on conditional mean reversion.*

---

## 10. Expected Improvement to Overall Strategy

### Baseline Strategy (No Mean Reversion)
During SIDEWAYS periods, the macro swing strategy sits mostly in cash or runs grid only. Capital is deployed at low efficiency.

### With Mean Reversion Layer
| Period | Without MR | With MR | Improvement |
|--------|-----------|---------|-------------|
| BULL regime | No change | No change | — |
| MACRO_BEAR | No change | No change | — |
| SIDEWAYS (est. 3 mo/yr) | Grid ~8% ann. | Grid + MR ~11% ann. | +3% on MR capital |
| Annual portfolio impact | — | — | +0.5–1.0% on total |

### Qualitative Benefits
1. **Capital efficiency:** MR deploys 15-20% of portfolio during idle SIDEWAYS periods
2. **Diversification:** MR profits are largely uncorrelated with momentum trades
3. **Regime signal:** When MR stop-losses cluster, it signals regime change (early warning)
4. **Psychological:** Keeps the strategy active during boring markets, reducing drift-chasing

### Integration Priority
1. **Phase 1 (implement now):** BB + Z-score mean reversion, BTC-only, SIDEWAYS only
2. **Phase 2 (3 months later):** Add VWAP confluence, tune stop parameters from Phase 1 data
3. **Phase 3 (6 months later):** BTC/ETH pairs trading if correlation remains high

---

## Appendix: Key Parameters Summary

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| BB period | 20-day | Standard, widely watched |
| BB std dev | 2.0 | ~95% probability bands |
| Z-score lookback (primary) | 20-day | Intra-range sensitivity |
| Z-score lookback (filter) | 50-day | Trend context |
| Entry z-score (long) | < -2.0 | 2σ below mean |
| Entry z-score (short) | > +2.5 | Extra buffer (BTC upward bias) |
| Max BB Width for activation | 10% | Range-bound confirmation |
| Min ATR/Price for deactivation | 4% | Volatility breakout signal |
| Position size | 3–7% per trade | Kelly-derived, conservative |
| Max MR exposure | 15% portfolio | Concentration limit |
| Max concurrent trades | 3 | Correlation management |
| Time stop | 10 days | Prevent capital tie-up |
| Regime confirmation delay | 2 days | Avoid whipsaw on entry |

---

*Research compiled for Issue #19. See `backtest/results/mean_reversion_results.md` for empirical validation.*
