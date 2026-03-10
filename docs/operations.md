# Operations: Live Trading & Monitoring

This document describes the operational flow from Go Live onwards — how trades are executed, monitored, and reported.

## Phase 6: Live Trading Operations

### Daily Schedule (All times ET)

| Time | Activity | Details |
|------|----------|---------|
| 7:00 AM | **Pre-market scan** | Check overnight crypto moves, Asian/European session, oil, futures |
| 8:30 AM | **Economic data check** | CPI, PPI, PCE, NFP released at 8:30 AM — react if applicable |
| 9:30 AM | **Market open review** | Equity open influences crypto sentiment. Evaluate positions. Post to #investments. |
| 10:00 AM | **Signal evaluation** | Synthesize morning data → trade decision: add, reduce, hold, or no action |
| 2:00 PM | **FOMC window** | Fed announcements at 2 PM on meeting days. High-alert mode. |
| 3:50 PM | **Pre-close review** | Evaluate EOD positions, decide on overnight exposure. Post to #investments. |
| 8:00 PM | **Evening scan** | Check crypto-specific news, funding rates, whale movements |
| Overnight | **Automated monitoring** | Stop-losses are live on exchange. Alerts for >3% moves. |

### Trade Execution Flow

```
1. SIGNAL DETECTED
   ├── Macro event (CPI/FOMC/NFP/geopolitical)
   ├── Technical trigger (RSI extreme, MA cross, breakout)
   └── Kalshi odds divergence (prediction market mispricing)
   
2. SIGNAL EVALUATION
   ├── Count primary signals aligned (need ≥2 for action)
   ├── Check secondary confirmation
   ├── Assess current regime (is this the right strategy for now?)
   └── Check existing positions (correlation, concentration)
   
3. POSITION SIZING
   ├── Determine conviction level (low/medium/high)
   ├── Calculate position size (10%/20%/30% of account)
   ├── Verify against risk limits (max exposure, correlation cap)
   └── Calculate stop-loss level and place order
   
4. EXECUTION
   ├── Place limit order (not market — avoid slippage)
   ├── Scale in: 50% initial, 50% on confirmation
   ├── Set stop-loss order on exchange immediately
   ├── Log trade: entry price, size, stop, target, rationale
   └── Post trade notification to #investments
   
5. POSITION MANAGEMENT
   ├── Monitor vs. stop-loss and profit targets
   ├── Adjust trailing stop per framework (10% up → breakeven stop, etc.)
   ├── Time stop: re-evaluate at 5 days if flat
   ├── Catalyst exit: close immediately if thesis changes
   └── Log all adjustments with timestamp and reason
   
6. EXIT
   ├── Stop-loss hit → automatic exit, log loss
   ├── Target hit → take 60% profit, trail remainder
   ├── Time stop → close if no new catalyst
   ├── Catalyst change → immediate exit
   └── Log final P&L, hold time, notes
```

### Position Monitoring Dashboard

Track for each open position:
- Entry price and date
- Current price and unrealized P&L ($ and %)
- Stop-loss level and distance
- Target level and distance
- Days held
- Thesis status (still valid / weakening / invalidated)

### Account-Level Monitoring

Track daily:
- Account balance (cash + positions)
- High-water mark
- Current drawdown from HWM
- Number of open positions
- Total exposure (% of account deployed)
- Cash reserve (must be ≥20%)

### Alert Triggers

| Event | Action |
|-------|--------|
| Position hits stop-loss | Auto-exit. Log. Notify. |
| Position up >10% | Move stop to breakeven. Notify. |
| Account drawdown >5% | Review all positions. Tighten stops. |
| Account drawdown >10% | Reduce to 50% sizing. Alert Bob. |
| Account drawdown >15% | GO TO CASH. Alert Bob. Full review. |
| Major macro event (unscheduled) | Immediate position review. |
| 3 consecutive losses | Reduce sizing 50% for next 3 trades. |

## Reporting Cadence

### Daily (included in investment brief)
```
📊 LIVE ACCOUNT STATUS
Balance: $X,XXX | Positions: X open | Drawdown: X.X%
Open: BTC LONG $XX,XXX @ $70,500 (stop $64,860) | P&L: +X.X%
Today: No trades / Bought ETH @ $X,XXX (macro swing signal)
```

### Weekly (Sunday evening)
- Win/loss summary (X wins / X losses)
- Total P&L for the week ($ and %)
- Best and worst trade
- Average hold time
- Strategy adherence review
- Regime assessment update

### Monthly (1st of each month)
- Full P&L statement
- Comparison to BTC buy-and-hold benchmark
- Sharpe ratio, max drawdown, win rate
- Strategy effectiveness review
- Proposed adjustments for next month

## Emergency Procedures

### Kill Switch Protocol
1. Bob says "go flat" or "kill switch"
2. Cancel ALL open/resting orders
3. Market sell ALL positions immediately
4. Confirm 100% cash
5. Report final state
6. HALT — no trading until Bob re-authorizes

### Exchange Outage
1. If exchange API is unreachable for >5 minutes during a trade
2. Attempt to place stop-loss via alternative method
3. Alert Bob
4. Do not enter new positions until API is stable

### Flash Crash (>15% move in <1 hour)
1. Stops should execute automatically
2. If stops didn't fill (gap through), assess damage
3. Do not chase or revenge trade
4. Go to cash, assess next day
5. Report to Bob
