# Crypto Trading Strategy Plan

## 1. Strategy Universe

### Evaluated Strategies

| Strategy | Edge Alignment | Regime Fit | Risk Control | Backtestable | Automation | Score |
|----------|---------------|-----------|-------------|-------------|-----------|-------|
| Trend Following | 3/5 | 3/5 | 4/5 | 5/5 | 5/5 | 3.6 |
| Mean Reversion | 2/5 | 2/5 | 3/5 | 5/5 | 5/5 | 3.0 |
| Grid Trading | 1/5 | 3/5 | 3/5 | 4/5 | 5/5 | 2.8 |
| **Macro Swing** | **5/5** | **5/5** | **4/5** | **3/5** | **3/5** | **4.3 ⭐** |
| DCA | 1/5 | 4/5 | 5/5 | 5/5 | 5/5 | 3.5 |
| Arbitrage | 1/5 | 3/5 | 5/5 | 4/5 | 4/5 | 2.9 |
| Hybrid (Adaptive) | 4/5 | 4/5 | 4/5 | 3/5 | 3/5 | 3.8 |

**Selected Strategy: Macro-Driven Swing Trading**

### Why Macro Swing

1. **Edge Alignment** — Pinch's core capability is synthesizing macro data (CPI, FOMC, NFP, geopolitical events, Kalshi prediction market odds) into directional views. This strategy exploits that edge directly.
2. **Regime Fit** — The current market (March 2026) is macro-driven: BTC correlates 0.55 with equities, -0.69 with gold. Macro signals dominate crypto-native narratives.
3. **Risk Control** — Swing trades have defined entries, exits, and stop-losses. Position sizing is explicit.
4. **Flexibility** — Can go to cash when signals are unclear. The best trade is sometimes no trade.

## 2. Trading Universe

**Core Assets:**
- BTC/USD — Primary. Most liquid, strongest macro correlation, most data available.
- ETH/USD — Secondary. DeFi/smart contract narrative adds a crypto-native dimension.
- SOL/USD — Tertiary. Higher beta, faster moves, useful for asymmetric bets.

**Selective Alts (case-by-case):**
- Only when a specific catalyst exists (e.g., ETF approval, protocol upgrade)
- Max 10% of account in any alt position
- Must have sufficient liquidity (>$50M daily volume)

## 3. Signal Framework

### Primary Signals (Macro)

| Signal | Source | Trade Direction | Weight |
|--------|--------|----------------|--------|
| CPI surprise (hot) | BLS release | Short/reduce | High |
| CPI surprise (cool) | BLS release | Long/add | High |
| FOMC dovish pivot | Fed statement/presser | Long | Critical |
| FOMC hawkish surprise | Fed statement/presser | Short/reduce | Critical |
| NFP strong miss (negative) | BLS release | Complex — short-term bearish, medium-term bullish (forces Fed hand) | Medium |
| Oil shock escalation | News/price action | Short crypto (risk-off) | Medium |
| Oil shock de-escalation | News/price action | Long crypto (risk-on) | Medium |
| BTC ETF flows (5-day) | ETF flow data | Confirms direction | Medium |
| Kalshi odds shift | Kalshi API | Confirms/challenges thesis | Low-Medium |

### Secondary Signals (Technical)

| Signal | Description | Use |
|--------|-------------|-----|
| RSI extremes | RSI < 25 or > 75 on daily | Entry/exit timing |
| 200-day MA | Price vs. 200 DMA | Regime confirmation |
| Volume profile | Unusual volume on breakout/breakdown | Conviction filter |
| Funding rates | Futures funding rate extremes | Contrarian signal |
| Fear & Greed Index | Extreme readings (<15 or >85) | Contrarian timing |

### Signal Combination Rules

- **Strong Long:** 2+ primary signals bullish + 1 secondary confirmation
- **Strong Short/Reduce:** 2+ primary signals bearish + 1 secondary confirmation
- **No Trade:** Conflicting primary signals or no clear catalyst. Go to cash.
- **Size Up:** 3+ primary signals aligned = max position (30%)
- **Size Down:** 1 primary signal only = minimum position (10%)

## 4. Position Sizing

| Signal Strength | Position Size (% of account) |
|----------------|------------------------------|
| Strong conviction (3+ signals) | 25-30% |
| Medium conviction (2 signals) | 15-20% |
| Low conviction (1 signal) | 10% |
| No signal / conflicting | 0% (cash) |

**Total exposure cap:** 80% of account (minimum 20% cash reserve)

## 5. Entry & Exit Rules

### Entry
- Wait for signal confirmation (data release + initial market reaction, typically 15-60 min)
- Use limit orders, not market orders (avoid slippage)
- Scale in: 50% at initial entry, 50% on confirmation or pullback

### Exit
- **Take profit:** 60% of position at 2:1 reward-to-risk target; trail stop on remainder
- **Stop-loss:** Hard stop at -8% from entry. No exceptions. No "let it breathe."
- **Time stop:** If position hasn't moved meaningfully in 5 trading days, re-evaluate. Close if no new catalyst.
- **Catalyst exit:** If the macro catalyst changes (e.g., ceasefire announced while short), exit immediately regardless of P&L.

## 6. Expected Performance

| Scenario | Annual Return | Win Rate | Avg Win/Loss Ratio | Max Drawdown |
|----------|-------------|----------|-------------------|-------------|
| Bull case | +40-80% | 60%+ | 3:1 | <10% |
| Base case | +15-30% | 55% | 2:1 | <15% |
| Bear case | -10-20% | 45% | 1.5:1 | <20% |
| Disaster case | -30%+ | <40% | <1:1 | >25% |

**Benchmark:** Buy-and-hold BTC over the same period.

## 7. Key Dates & Catalysts (March-April 2026)

| Date | Event | Potential Impact |
|------|-------|-----------------|
| Mar 11 | CPI | High — inflation trajectory |
| Mar 12 | PPI | Medium — pipeline inflation |
| Mar 13 | Core PCE | High — Fed's preferred gauge |
| Mar 18 | FOMC + Powell presser | Critical — rate decision & guidance |
| Apr 4 | NFP | High — labor market trajectory |
| Mar 16 | NVDA GTC | Medium — AI/tech sentiment |
