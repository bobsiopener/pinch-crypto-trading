# Kelly Criterion — Dynamic Position Sizing Research

**Author:** Pinch (Chief of Finance)  
**Date:** 2026-03-11  
**Strategy:** Macro Swing (BTC, macro event-driven entries)

> *Rule of Acquisition #75: Home is where the heart is, but the stars are made of latinum.*  
> *More applicable: Rule #22 — A wise man can hear profit in the wind. And a wiser man sizes his position to survive the storm.*

---

## 1. The Kelly Criterion

### Formula

The Kelly Criterion determines the **optimal fraction of capital** to risk on a single bet to maximize long-run geometric growth:

```
f* = (b·p - q) / b
```

Where:
- **f*** = optimal fraction of capital to allocate
- **b** = odds ratio = average_win / average_loss (in absolute terms)
- **p** = probability of a winning trade (win rate)
- **q** = probability of a losing trade = 1 - p

This formula maximizes the **expected logarithm of wealth**, which is equivalent to maximizing long-run compounded growth. Over many trades, any deviation from Kelly (above or below) results in lower terminal wealth.

### Intuition

Kelly balances two competing forces:
1. **Bet more** when edge is high (captures more profit)
2. **Bet less** when variance is high (avoids ruin from drawdowns)

A bettor who over-bets Kelly will eventually go broke. Under-betting is suboptimal but survivable. This asymmetry is why fractional Kelly is preferred in practice.

---

## 2. Our Strategy Parameters (from Backtest Results)

From `backtest/results/macro_swing_results.md`:

| Parameter | Value |
|-----------|-------|
| Win Rate (p) | 70.00% |
| Average Win | +7.25% |
| Average Loss | -8.40% |
| Profit Factor | 2.015 |
| Number of Trades | 10 |

### Kelly Calculation

```
b = avg_win / abs(avg_loss) = 7.25% / 8.40% = 0.8631

p = 0.70
q = 1 - 0.70 = 0.30

f* = (b·p - q) / b
   = (0.8631 × 0.70 - 0.30) / 0.8631
   = (0.6042 - 0.30) / 0.8631
   = 0.3042 / 0.8631
   = 0.3524 → 35.24%
```

### Kelly Fractions

| Variant | Fraction | Position Size |
|---------|----------|---------------|
| Full Kelly | 1.0 × f* | **35.24%** |
| Half Kelly | 0.5 × f* | **17.62%** |
| Quarter Kelly | 0.25 × f* | **8.81%** |
| Current Fixed (score=2) | — | 20.00% |
| Current Fixed (score≥3) | — | 30.00% |

**Observation:** Our current fixed sizing (20-30%) brackets Kelly almost perfectly — 20% is close to half-Kelly and 30% approaches full Kelly. This is a reasonable coincidence, but Kelly provides a principled, adaptive basis for sizing rather than a static guess.

---

## 3. Why Fractional Kelly is Preferred

### The Problem with Full Kelly

Full Kelly is theoretically optimal only under idealized conditions that never hold in practice:

1. **Parameter uncertainty:** Win rate and average win/loss are estimated from small samples (10 trades in our backtest). Estimation error can easily be ±10-15%. Over-estimated edge → over-bet → catastrophic drawdown.

2. **Drawdown magnitude:** Full Kelly produces **aggressive drawdowns**. The expected maximum drawdown at full Kelly is roughly `f* / 2 = 17.6%` per losing streak — painful and potentially trade-disrupting.

3. **Non-stationarity:** Markets change. A regime shift (e.g., 2022 bear market) can flip win rates dramatically. Half Kelly provides a buffer.

4. **Path dependence:** Kelly maximizes *expected* terminal wealth, but individual paths can be brutal. Half Kelly trades ~25% of long-run return for a ~50% reduction in variance.

### Half Kelly is the Practical Standard

Half Kelly (f*/2 = **17.62%**) is the most widely used fractional variant:
- Reduces variance by ~75% (variance scales with f²)
- Reduces expected return by only ~25% (return scales with f - f²/2)
- Provides meaningful protection against parameter estimation errors
- Keeps max expected drawdown to ~8.8% — consistent with our 8% stop-loss design

Quarter Kelly (f*/4 = **8.81%**) is appropriate for:
- Highly uncertain parameters (few trades)
- Strategies with significant tail risk
- Conservative growth mandates

**For our macro swing strategy: Half Kelly (≈17.6%) is recommended.**

---

## 4. Fixed Sizing vs. Kelly Sizing

| Aspect | Fixed Sizing (Current) | Kelly Sizing |
|--------|----------------------|--------------|
| Logic | Rule-based: 20% or 30% by signal score | Data-driven: calibrated to win rate + payoff ratio |
| Adaptability | Static — doesn't update with performance | Dynamic — can update as edge is re-estimated |
| Risk of ruin | Moderate (can over-bet in low-edge regimes) | Lower (Kelly self-limits when edge is low) |
| Simplicity | High | Medium |
| Requires estimation | No | Yes (win rate, avg win/loss) |
| Current sizing vs Kelly | 20-30% ≈ 0.57-0.85× Kelly | By definition, optimal |

**Key risk of fixed sizing:** If our win rate dropped to 55% (edge deteriorates), Kelly would drop to ~8%, but fixed sizing would still deploy 20-30% — triple the optimal. This is the hidden drawdown risk in our current approach.

---

## 5. Volatility-Adjusted Sizing (ATR Method)

### Formula

```
position_size = target_risk_dollars / (ATR_value × account_value)

Or equivalently:
position_fraction = target_risk_pct / (ATR_pct)
```

Where:
- **ATR** = Average True Range over 20 days (as % of price)
- **target_risk_pct** = maximum loss we'll accept on this trade (e.g., 2%)
- **ATR_pct** = ATR / current_price

### Rationale

ATR-based sizing equalizes **dollar risk** across trades regardless of market volatility:
- High volatility period → smaller position (stop hits harder, so size down)
- Low volatility period → larger position (stop has more room, so size up)
- Result: each trade risks approximately the same dollar amount

### Practical Implementation

```
atr_20 = 20-day Average True Range (price units)
atr_pct = atr_20 / current_price

# To risk 2% of account per trade:
position_size = 0.02 / atr_pct
```

**BTC context:** BTC's 20-day ATR typically ranges from 2-8% of price. At 4% ATR:
```
position_size = 0.02 / 0.04 = 0.50 = 50%
```
That's too large. We cap at Kelly or a fixed max (30%). Hence the `combined_sizing()` function: **take the minimum of Kelly and ATR sizing.**

---

## 6. Proposed Rules for the Macro Swing Strategy

### Position Sizing Decision Tree

```
1. Compute Kelly size:
   - Use rolling estimates (last 20+ trades) when available
   - Use backtest priors (p=0.70, b=0.8631) when < 20 trades
   - Apply half-Kelly: kelly_size = f* × 0.5

2. Compute ATR size:
   - 20-day ATR as % of price
   - atr_size = 0.02 / atr_pct   (target: 2% account risk per trade)

3. Combined size = min(kelly_size, atr_size)

4. Hard caps:
   - Maximum: 30% of account (never exceeded)
   - Minimum: 10% of account (below this, skip trade)

5. Score adjustment (optional multiplier):
   - Score = ±2: 1.0× combined size
   - Score = ±3: 1.2× combined size (capped at 30%)
```

### Parameter Re-estimation

- **Rolling window:** Re-estimate win_rate, avg_win, avg_loss every 20 trades
- **Shrinkage:** Blend rolling estimate with backtest prior (50/50) for first 50 trades
- **Circuit breaker:** If win rate < 40% in last 10 trades → halve position sizes

### Implementation Notes

- Current backtest uses only 10 trades — too few for robust rolling estimation
- Use backtest priors (p=0.70, b=0.8631) for initial live deployment
- Re-evaluate quarterly or after 20+ live trades
- Half Kelly ≈ 17.6% aligns closely with our existing 20% sizing — minimal strategy disruption

---

## 7. Summary

| Method | Position Size | Max Drawdown Risk | Best For |
|--------|--------------|-------------------|----------|
| Fixed 20% | 20% | Moderate | Simplicity |
| Fixed 30% | 30% | Higher | Strong signals |
| Full Kelly | 35.24% | High (parameter sensitive) | Theory only |
| Half Kelly | 17.62% | Low-Moderate | **Recommended** |
| Quarter Kelly | 8.81% | Low | Conservative |
| ATR-based (2%) | Variable | Low (volatility-calibrated) | High-vol regimes |
| **Combined (min)** | **Variable ≤ 30%** | **Lowest** | **Production** |

**Bottom line:** Half Kelly (~17.6%) is the theoretical optimum for our strategy's edge. Combined with ATR-based sizing as a volatility cap, we get adaptive position sizing that protects capital during high-volatility periods while maximizing compounded growth when conditions are favorable.

> *Rule of Acquisition #22: A wise man can hear profit in the wind.*  
> *A wiser man knows how much latinum to risk when the wind shifts.*
