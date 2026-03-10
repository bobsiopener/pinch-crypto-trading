# Risk Framework

## Core Principles

1. **Survive first, profit second.** No single trade should threaten the account.
2. **Defined risk on every trade.** No position without a stop-loss.
3. **Cash is a position.** Being flat when signals are unclear is not cowardice — it's discipline.
4. **Drawdown limits are non-negotiable.** Break the rules once, and rules mean nothing.

## Position Limits

| Rule | Limit | Action if Breached |
|------|-------|-------------------|
| Max single position | 30% of account | Cannot open beyond this |
| Max total exposure | 80% of account | Must maintain 20% cash |
| Max per-trade loss | 8% of position value | Hard stop-loss, automated |
| Max correlated exposure | 50% of account | BTC + ETH count as correlated |

## Drawdown Management

| Drawdown Level | Action |
|---------------|--------|
| -5% from HWM | Review all open positions. Tighten stops. |
| -10% from HWM | Reduce all positions to 50% of normal size. Alert Bob. |
| -15% from HWM | **GO TO CASH.** Close all positions. Full strategy review before resuming. |
| -20% from HWM | **HALT.** No trading until Bob explicitly re-authorizes. |

**HWM = High-Water Mark** — the highest account value achieved.

## Stop-Loss Rules

### Hard Stop
- Every position has a stop-loss set at entry
- Maximum 8% from entry price
- Stop is placed as an actual exchange order, not mental
- Stops are NEVER moved further from entry (can only be tightened)

### Trailing Stop
- After a position is up 10%+, move stop to breakeven
- After a position is up 15%+, trail stop at 10% below high
- After a position is up 25%+, take 60% profit, trail remainder at 8%

### Time Stop
- Position open for 5 days with <2% move → re-evaluate
- Position open for 10 days with <5% move → close unless new catalyst exists

## Circuit Breakers

| Trigger | Action |
|---------|--------|
| 3 consecutive losing trades | Reduce position size by 50% for next 3 trades |
| 5 consecutive losing trades | Go to cash. 48-hour cooling period. Strategy review. |
| Single-day account loss >5% | Close all positions. Review next day. |
| Exchange technical issues | Flatten to cash immediately |
| Major unexpected event (black swan) | Flatten to cash immediately |

## Kill Switch

Bob can issue a "go flat" command at any time. Upon receiving this:
1. Cancel all open/resting orders
2. Market sell all positions
3. Confirm 100% cash position
4. Report final account state
5. Do not resume trading until explicitly authorized

## Reporting

### Per-Trade
- Entry price, size, rationale
- Stop-loss level
- Target level
- Exit price, P&L, time held

### Daily
- Account balance
- Open positions with unrealized P&L
- Drawdown from HWM
- Number of trades today

### Weekly
- Win/loss record
- Average gain vs. average loss
- Sharpe ratio (rolling 30-day)
- Max drawdown reached
- Strategy adherence score (did we follow the rules?)

### Monthly
- Full performance report
- Comparison to benchmark (buy-hold BTC)
- Strategy review and adjustments proposed
