# Market Regime Detection Algorithm
**Issue:** #3 | **Status:** Complete | **Date:** 2026-03-10

## Overview

This algorithm classifies the crypto market into one of four regimes, updating daily. The regime determines which strategy to run and how aggressively to size positions.

## Regimes

| Regime | Code | Description | Strategy |
|--------|------|-------------|----------|
| Risk-On Bull | `BULL` | Trending up, macro supportive | Momentum long, buy dips |
| Macro-Driven Bear | `MACRO_BEAR` | Macro headwinds dominating | Macro swing, heavy cash, selective |
| Crypto-Native Bear | `CRYPTO_BEAR` | Crypto-specific crisis | Cash only, wait |
| Sideways/Consolidation | `SIDEWAYS` | Range-bound, low vol | Grid trading, mean reversion |

## Input Signals

### 1. Trend Score (-2 to +2)

| Condition | Score |
|-----------|-------|
| BTC above 200 DMA AND above 50 DMA | +2 |
| BTC above 200 DMA but below 50 DMA | +1 |
| BTC below 200 DMA but above 50 DMA | -1 |
| BTC below 200 DMA AND below 50 DMA | -2 |

### 2. Monthly Close Direction (-2 to +2)

| Condition | Score |
|-----------|-------|
| 3+ consecutive green monthly closes | +2 |
| 1-2 green monthly closes | +1 |
| 1-2 red monthly closes | -1 |
| 3+ consecutive red monthly closes | -2 |

### 3. BTC-Equity Correlation (-1 to +1)

| Condition | Score | Meaning |
|-----------|-------|---------|
| Correlation > 0.5 (30-day rolling) | +1 | Macro-driven; BTC moves with stocks |
| Correlation 0.2-0.5 | 0 | Mixed drivers |
| Correlation < 0.2 | -1 | Crypto-native drivers dominant |

*Note: Positive correlation score means macro-driven, not bullish/bearish*

### 4. Macro Environment Score (-2 to +2)

| Condition | Score |
|-----------|-------|
| Fed cutting + low oil + strong jobs | +2 |
| Fed on hold + stable macro | +1 |
| Mixed signals (some positive, some negative) | 0 |
| Fed hawkish + oil rising + jobs weakening | -1 |
| Active crisis (war, stagflation, banking) | -2 |

### 5. ETF Flow Score (-1 to +1)

| Condition | Score |
|-----------|-------|
| 5+ day net inflows | +1 |
| Mixed/neutral flows | 0 |
| 5+ day net outflows | -1 |

### 6. Volatility Regime (0 to 2)

| Condition | Score | Meaning |
|-----------|-------|---------|
| 30-day BTC realized vol < 40% annualized | 0 | Low vol → potential sideways |
| 30-day BTC realized vol 40-80% | 1 | Normal |
| 30-day BTC realized vol > 80% | 2 | High vol → trending or crisis |

### 7. Crypto-Native Stress Indicator (0 or -3)

| Condition | Score |
|-----------|-------|
| No crypto-specific crisis | 0 |
| Major exchange insolvency, stablecoin depeg, or regulatory shock | -3 |

## Classification Algorithm

```python
def classify_regime(trend, monthly, correlation, macro, etf_flow, volatility, crypto_stress):
    """
    Returns: regime string and confidence (0-1)
    """
    
    # CRYPTO_BEAR overrides everything
    if crypto_stress == -3:
        return "CRYPTO_BEAR", 0.95
    
    # Calculate composite score
    directional_score = trend + monthly + macro + etf_flow
    # Range: -7 to +7
    
    is_macro_driven = correlation >= 0.5  # BTC moving with equities
    is_low_vol = volatility == 0
    
    # SIDEWAYS: low vol + weak directional signal
    if is_low_vol and abs(directional_score) <= 2:
        confidence = 0.7 if abs(directional_score) <= 1 else 0.5
        return "SIDEWAYS", confidence
    
    # BULL: strong positive directional + not in crisis
    if directional_score >= 3:
        confidence = min(0.95, 0.5 + directional_score * 0.07)
        return "BULL", confidence
    
    # MACRO_BEAR: negative directional + macro-driven
    if directional_score <= -2 and is_macro_driven:
        confidence = min(0.95, 0.5 + abs(directional_score) * 0.07)
        return "MACRO_BEAR", confidence
    
    # MACRO_BEAR: strongly negative even without high correlation
    if directional_score <= -4:
        return "MACRO_BEAR", 0.7
    
    # SIDEWAYS: moderate signals, no clear direction
    if abs(directional_score) <= 2:
        return "SIDEWAYS", 0.5
    
    # Default: weakly directional
    if directional_score > 0:
        return "BULL", 0.4  # Low confidence bull
    else:
        return "MACRO_BEAR", 0.4  # Low confidence bear


# Current readings (March 10, 2026):
current = classify_regime(
    trend=-2,       # Below both 200 DMA and 50 DMA
    monthly=-2,     # 5 consecutive red monthly closes
    correlation=1,  # BTC-equity correlation 0.55 (macro-driven)
    macro=-2,       # Active crisis: Iran war, stagflation, Fed paralyzed
    etf_flow=-1,    # Net outflows resumed
    volatility=2,   # High vol
    crypto_stress=0  # No crypto-native crisis
)
# Result: MACRO_BEAR, confidence 0.85
```

## Current Assessment (March 10, 2026)

| Signal | Raw Reading | Score |
|--------|------------|-------|
| Trend | Below 200 DMA and 50 DMA | -2 |
| Monthly Closes | 5 consecutive red | -2 |
| BTC-Equity Correlation | 0.55 | +1 (macro-driven) |
| Macro Environment | Iran war, -92K NFP, oil shock, Fed stuck | -2 |
| ETF Flows | Net outflows | -1 |
| Volatility | High (80%+ annualized) | 2 |
| Crypto Stress | No crypto-native crisis | 0 |

**Directional Score:** -2 + -2 + -2 + -1 = **-7** (maximum bearish)
**Macro-Driven:** Yes (correlation > 0.5)

### **REGIME: MACRO_BEAR (confidence: 0.95)**

## Strategy Mapping

| Regime | Max Exposure | Position Sizing | Default Stance |
|--------|-------------|----------------|----------------|
| BULL | 80% | Full (10-30%) | Fully invested, buy dips |
| MACRO_BEAR | 50% | Half (5-15%) | Heavy cash, selective swing |
| CRYPTO_BEAR | 0% | None | 100% cash |
| SIDEWAYS | 60% | Moderate (10-20%) | Grid + mean reversion |

## Transition Alerts

The algorithm runs daily. When a regime change is detected:
1. Alert posted to #investments
2. All open positions reviewed against new regime rules
3. Position sizes adjusted to new regime limits
4. Strategy approach updated

**Regime Change Watchlist (what would shift MACRO_BEAR → BULL):**
- Fed announces rate cuts → macro score improves to 0 or +1
- BTC reclaims 200 DMA → trend score improves to -1 or 0
- Oil drops below $80 → macro score improves
- ETF inflows resume for 5+ days → flow score flips to +1
- 2+ green monthly closes → monthly score improves

**Estimated timeline for potential shift:** 6-12 weeks minimum unless a shock catalyst occurs (emergency rate cut, sudden peace deal)

## Update Log

| Date | Regime | Confidence | Key Change |
|------|--------|-----------|------------|
| 2026-03-10 | MACRO_BEAR | 0.95 | Initial assessment. Iran conflict, -92K NFP, oil shock, 5 red months. |
