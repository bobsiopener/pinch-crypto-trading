# Macro Swing Signal Definitions
**Issue:** #1 | **Status:** Complete | **Date:** 2026-03-10

## Overview

Each signal is defined with:
- **Trigger condition** — What specifically constitutes a signal?
- **Direction** — Long, short, or reduce?
- **Strength** — How much conviction does this add?
- **Timing** — When to act relative to the event?
- **Historical behavior** — How has BTC reacted historically?

---

## PRIMARY SIGNALS

### Signal 1: CPI Surprise

**Data source:** Bureau of Labor Statistics, released 8:30 AM ET, monthly
**Schedule:** Usually 2nd or 3rd week of the month

| Condition | Direction | Strength | Action |
|-----------|-----------|----------|--------|
| CPI YoY > consensus by ≥0.2% | SHORT/REDUCE | High | Reduce long exposure or go short |
| CPI YoY < consensus by ≥0.2% | LONG | High | Add to long position |
| CPI YoY meets consensus (±0.1%) | NEUTRAL | Low | No action; watch 24h price action |
| Core CPI diverges from headline | MODIFIER | Medium | Core matters more to Fed — weight accordingly |

**Historical Behavior (2024-2026):**
- BTC averages 2-4% move immediately post-CPI
- Retraces 1-2% within 24-48 hours (don't chase the initial spike)
- Cool CPI in Jan 2025: BTC rose above $98,500
- Hot CPI in Q4 2025: BTC dropped 3-5% same day
- **Key insight:** The *surprise* matters more than the level. Market prices in expectations.

**Execution Rules:**
- Wait 15-30 minutes after release for initial volatility to settle
- Enter via limit order, not market
- If CPI + Core CPI both surprise in same direction → Strong signal (increase size)
- If CPI and Core diverge → Weak signal (minimum size or no trade)

---

### Signal 2: FOMC Rate Decision + Powell Presser

**Data source:** Federal Reserve, 2:00 PM ET statement, 2:30 PM presser
**Schedule:** 8 meetings per year (~every 6 weeks)

| Condition | Direction | Strength | Action |
|-----------|-----------|----------|--------|
| Rate cut (unexpected or larger than priced) | LONG | Critical | Max conviction long |
| Rate cut (expected, priced in) | NEUTRAL | Low | Minimal reaction expected |
| Rate hold (when cut expected) | SHORT/REDUCE | High | Risk-off; reduce longs |
| Rate hike (unexpected) | SHORT | Critical | Immediate exit of all longs |
| Dovish language shift (no action but tone change) | LONG | Medium | Gradual positioning |
| Hawkish language shift | SHORT/REDUCE | Medium | Tighten stops, reduce exposure |
| Dot plot shows more cuts than expected | LONG | High | Medium-term positioning |
| Dot plot shows fewer cuts | SHORT/REDUCE | High | Medium-term de-risking |

**Historical Behavior (2023-2026):**
- Dec 2023: Hold at 5.25-5.50% → BTC surged 22% post-meeting (dovish pivot language)
- Sept 2024: First cut (50bps) → BTC rallied 8% over following week
- 2025: BTC rallied after only 1 of 8 FOMC meetings despite cutting cycle — "priced in" effect
- **Key insight:** Powell's presser language matters MORE than the rate decision itself. The Q&A creates the vol.

**Execution Rules:**
- Do NOT trade the 2:00 PM statement — wait for 2:30 PM presser
- Initial move in first 30 minutes is often reversed
- Best entry window: 3:00-4:00 PM ET after presser digested
- For swing trade: enter after close, hold 2-7 days for full reaction to develop
- Always check Fed funds futures for what's priced in BEFORE the meeting

---

### Signal 3: Non-Farm Payrolls (NFP)

**Data source:** Bureau of Labor Statistics, 8:30 AM ET, first Friday of month
**Schedule:** Monthly, first Friday

| Condition | Direction | Strength | Action |
|-----------|-----------|----------|--------|
| NFP >> consensus (strong jobs) | COMPLEX | Medium | Short-term bearish (no cuts), but long-term positive (no recession) |
| NFP << consensus (weak jobs) | COMPLEX | Medium | Short-term bearish (risk-off), medium-term bullish (forces Fed cuts) |
| NFP negative (job losses) | SHORT near-term | High | Risk-off; but watch for Fed pivot narrative to develop |
| Unemployment spikes ≥0.3% | SHORT near-term | High | Recession fear dominates initially |
| Wage growth hot (>4% YoY) | SHORT | Medium | Inflation pressure → hawkish Fed |
| Wage growth cooling (<3% YoY) | LONG | Medium | Goldilocks for rate cuts |

**Current Context (March 2026):**
- Feb NFP: -92,000 (catastrophic miss) at 4.4% unemployment
- This has shifted the narrative toward recession/stagflation
- Next NFP (April 4) will either confirm or deny the deterioration trend

**Historical Behavior:**
- NFP surprises create 1-3% BTC moves within 2 hours
- The *direction* depends on the macro regime (see Signal Framework interaction below)
- In risk-off regime: bad NFP = bad for BTC (sell everything)
- In rate-cut-hopeful regime: bad NFP = good for BTC (Fed will cut)

**Execution Rules:**
- Wait 30-60 minutes after release — NFP creates complex, multi-leg moves
- Check unemployment rate AND wage growth, not just headline NFP
- In current stagflation regime: treat bad NFP as initially bearish, with medium-term bullish potential if Fed pivots

---

### Signal 4: Oil Price Shock / Geopolitical Escalation

**Data source:** Real-time news feeds, oil futures (CL, BZ)
**Schedule:** Unpredictable — event-driven

| Condition | Direction | Strength | Action |
|-----------|-----------|----------|--------|
| Oil spikes >5% in a day (escalation) | SHORT crypto | High | Risk-off; liquidity drain |
| Oil drops >5% in a day (de-escalation) | LONG crypto | High | Risk-on relief rally |
| New military action / sanctions | SHORT crypto | Medium | Monitor for 24h before acting |
| Ceasefire / peace talks | LONG crypto | Medium | Scale into long on confirmation |
| Oil sustained above $100/bbl | BEARISH bias | Low | Maintains stagflation pressure |
| Oil returns below $80/bbl | BULLISH bias | Low | Removes inflation accelerant |

**Current Context:**
- Iran conflict week 2, oil hit $120/bbl Monday, now at ~$87
- Strait of Hormuz disruption is the key risk factor
- Trump "very complete" comments caused oil pullback — unreliable source

**Execution Rules:**
- Don't trade the headline — wait for oil price confirmation
- Geopolitical signals are binary and fast; use smaller position sizes
- Pair with other signals for conviction (oil spike + hot CPI = strong short)

---

### Signal 5: BTC ETF Flow Momentum

**Data source:** ETF flow aggregators (SoSoValue, BitMEX Research, Bloomberg)
**Schedule:** Daily, available by ~6 PM ET

| Condition | Direction | Strength | Action |
|-----------|-----------|----------|--------|
| 5 consecutive days net inflows | LONG confirmation | Medium | Confirms bullish momentum |
| 5 consecutive days net outflows | SHORT confirmation | Medium | Confirms bearish pressure |
| Single-day massive inflow (>$500M) | LONG | Medium | Institutional demand spike |
| Single-day massive outflow (>$500M) | SHORT/REDUCE | Medium | Institutional liquidation |
| Flow acceleration (increasing daily inflows) | LONG | Low-Medium | Trend strengthening |
| Flow reversal (inflows → outflows or vice versa) | ALERT | Medium | Potential trend change |

**Current Context:**
- ETF outflows resumed in March 2026
- This is a bearish confirmation signal

**Execution Rules:**
- ETF flow is a CONFIRMATION signal, not a primary trigger
- Use to adjust conviction level of trades triggered by other signals
- 5-day rolling sum is more meaningful than any single day

---

## SECONDARY SIGNALS (Technical)

### RSI Extremes (Daily)
- RSI < 25: Oversold extreme → potential mean reversion long (only with macro support)
- RSI > 75: Overbought extreme → reduce longs or take profit
- RSI 40-60: Neutral zone → no action from this signal

### 200-Day Moving Average
- Price above 200 DMA: Bullish regime confirmation
- Price below 200 DMA: Bearish regime confirmation (CURRENT)
- Cross above from below: Regime change signal — very significant
- Cross below from above: Regime change signal — reduce exposure

### Volume Profile
- Breakout with >2x average volume: High conviction
- Breakout with normal volume: Suspect — may be false breakout
- Extreme low volume: Consolidation; wait for resolution

### Funding Rate (Futures)
- Funding > 0.1%: Market excessively long → contrarian short bias
- Funding < -0.05%: Market excessively short → contrarian long bias
- Normal range: No signal

### Fear & Greed Index
- Below 15 (Extreme Fear): Contrarian long signal (with macro confirmation)
- Above 85 (Extreme Greed): Contrarian short/reduce signal
- 30-70: No signal from this indicator

---

## SIGNAL INTERACTION FRAMEWORK

No signal operates in isolation. Here's how they combine:

### Strong Long Setup (3+ aligned signals)
Example: Cool CPI + Dovish FOMC language + ETF inflows resuming
→ Position size: 25-30% of account
→ Stop: 6-8%
→ Target: 15-20%

### Moderate Long (2 aligned signals)
Example: Cool CPI + RSI oversold
→ Position size: 15-20%
→ Stop: 8%
→ Target: 10-15%

### Strong Short/Reduce (3+ aligned signals)
Example: Hot CPI + Oil spike + ETF outflows accelerating
→ Action: Reduce to 0-10% exposure or short
→ Stop: 8%
→ Target: 10-15%

### Conflicting Signals → NO TRADE
Example: Cool CPI but FOMC hawkish language
→ Action: Stay in cash until signals align
→ Cash IS a position

### The Cardinal Rule
**If you can't clearly articulate why you're entering a trade using at least 2 signals from this framework, you don't have a trade.**
