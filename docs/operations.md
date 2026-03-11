# Operations: Live Trading & Monitoring

> *"Rule of Acquisition #74: Knowledge equals profit."*

This document describes the operational flow from Go Live onwards — how trades are executed, monitored, and reported.
It also serves as the day-to-day runbook for system health, configuration, and maintenance.

---

## Quick Reference

| Task | Command |
|---|---|
| Full dashboard | `python3 live/monitoring/dashboard.py` |
| Brief P&L | `python3 live/monitoring/dashboard.py --brief` |
| Market monitor status | `python3 live/monitor/market_monitor.py status` |
| Kill switch | `python3 live/execution/kill_switch.py kill` |
| Paper trade status | `python3 live/paper_trading/track_manager.py status` |
| Run macro swing backtest | `cd backtest && python3 run_backtest.py` |
| DB health check | `cd /mnt/media/market_data && python3 collect.py status` |

---

## System Health Checks

### Daily Health Check

Run the full health check in the morning before market open:

```bash
# 1. Check market monitor daemon is running
sudo systemctl status pinch-market-monitor

# 2. Dashboard — live prices + paper P&L
python3 live/monitoring/dashboard.py --brief

# 3. Market monitor state
python3 live/monitor/market_monitor.py status

# 4. Risk state (drawdown, HWM)
cat live/config/risk_state.json

# 5. Data collection health
cd /mnt/media/market_data && python3 collect.py status
```

### Collection Health

```bash
# Check last collection run status
sqlite3 /mnt/media/market_data/pinch_market.db \
  "SELECT datetime(timestamp,'unixepoch') AS run, collector, status, records_inserted, error_msg
   FROM collection_log ORDER BY timestamp DESC LIMIT 10;"

# Check for gaps in BTC price data (missing days)
sqlite3 /mnt/media/market_data/pinch_market.db \
  "SELECT date(timestamp,'unixepoch') AS day, COUNT(*) AS rows
   FROM prices WHERE symbol='BTC' AND timeframe='1d'
   AND timestamp >= strftime('%s','now','-30 days')
   GROUP BY day ORDER BY day;"
```

### Monitor Log Review

```bash
# Tail live monitor log
tail -50 logs/monitor/monitor.log

# Search for alerts fired
grep "ALERT" logs/monitor/monitor.log | tail -20

# Search for errors
grep "ERROR" logs/monitor/monitor.log | tail -20
```

---

## How to Add a New Symbol to Track

### 1. Add to market data collector config

Edit `market_data/collector/config.py`:

```python
# Add to CRYPTO_SYMBOLS or STOCK_SYMBOLS
CRYPTO_SYMBOLS = ['BTC', 'ETH', 'SOL', 'NEW_SYMBOL']  # example
STOCK_SYMBOLS  = ['SPY', 'QQQ', 'AAPL', ..., 'NEW_TICKER']
```

### 2. Backfill historical data

```bash
cd /mnt/media/market_data
python3 collect.py crypto   # or stocks
# Then backfill via historical_backfill.py if needed
python3 collector/historical_backfill.py NEW_SYMBOL
```

### 3. Add to market monitor alerts (optional)

Edit `live/monitor/market_monitor.py` — find the `TRACKED_SYMBOLS` list and add the new symbol.

### 4. Add CSV data for backtesting (if needed)

```bash
# Export from DB to CSV for backtesting
sqlite3 /mnt/media/market_data/pinch_market.db \
  ".headers on" ".mode csv" \
  "SELECT date(timestamp,'unixepoch') AS date, open, high, low, close, volume
   FROM prices WHERE symbol='NEW' AND timeframe='1d' ORDER BY timestamp;" \
  > backtest/data/new_daily.csv
```

### 5. Verify

```bash
sqlite3 /mnt/media/market_data/pinch_market.db \
  "SELECT COUNT(*), MIN(date(timestamp,'unixepoch')), MAX(date(timestamp,'unixepoch'))
   FROM prices WHERE symbol='NEW_SYMBOL';"
```

---

## How to Add a Macro Event to the Calendar

The macro calendar drives the market monitor's pre-event alerts.

### Via CLI (recommended)

```bash
python3 live/monitor/market_monitor.py add-event \
  "2026-04-10" "08:30" "CPI March 2026" "high"
```

Arguments: `<date YYYY-MM-DD> <time HH:MM ET> <name> <impact: high|medium|low>`

### Manual edit

Edit `live/monitor/macro_calendar.json`:

```json
{
  "events": [
    {
      "date": "2026-04-10",
      "time": "08:30",
      "name": "CPI March 2026",
      "impact": "high",
      "description": "Consumer Price Index - March 2026 release"
    }
  ]
}
```

Impact levels:
- `high` — Alert 24h before + 1h before (CPI, FOMC, NFP)
- `medium` — Alert 1h before (PPI, PCE, Retail Sales)
- `low` — Log only (minor releases)

### Verify

```bash
python3 live/monitor/market_monitor.py status
# Look for "Upcoming Events" in output
```

---

## How to Run a Backtest

### Run the primary strategy (Macro Swing)

```bash
cd /tmp/pinch-crypto-trading/backtest
python3 run_backtest.py
# Results → backtest/results/macro_swing_results.md
```

### Run any other strategy

```bash
python3 run_ema_backtest.py        # EMA Crossover
python3 run_grid_backtest.py       # Grid Trading
python3 run_meanrev_backtest.py    # Mean Reversion
python3 run_maxpain_backtest.py    # Max Pain Expiry
python3 run_rsi_backtest.py        # RSI Overlay
python3 run_candlestick_backtest.py # Candlestick Filter
python3 run_options_backtest.py    # Options Overlay
python3 run_onchain_backtest.py    # On-Chain Overlay
python3 run_kelly_backtest.py      # Kelly Sizing
python3 run_stoploss_backtest.py   # Stop-Loss Optimization
python3 run_oos_validation.py      # Out-of-Sample Validation
```

### Use fresh data from DB

```bash
# Export latest BTC data from market DB
sqlite3 /mnt/media/market_data/pinch_market.db \
  ".headers on" ".mode csv" \
  "SELECT date(timestamp,'unixepoch') AS date, open, high, low, close, volume
   FROM prices WHERE symbol='BTC' AND timeframe='1d'
   AND timestamp >= strftime('%s','2022-01-01')
   ORDER BY timestamp;" \
  > backtest/data/btc_daily_fresh.csv

# Then update run_backtest.py to use the fresh file, or pass as arg
```

### Backtest results location

All results write to `backtest/results/*.md`. Check them after running:

```bash
cat backtest/results/macro_swing_results.md | head -40
```

---

## How to Check Paper Trading Status

### Quick status

```bash
python3 live/paper_trading/track_manager.py status
```

### Full dashboard (includes paper trades)

```bash
python3 live/monitoring/dashboard.py
```

### Raw state files

```bash
# All three tracks
cat live/paper_trading/state/paper_tracks.json | python3 -m json.tool

# Grid trader state
cat live/paper_trading/state/grid_paper_state.json | python3 -m json.tool
```

### Trade log

```bash
# All paper trades
cat logs/trades/paper_trades.csv

# Today's activity
grep "$(date +%Y-%m-%d)" logs/trades/paper_trades.csv

# P&L summary
python3 - <<'EOF'
import csv
with open('logs/trades/paper_trades.csv') as f:
    trades = list(csv.DictReader(f))
total_pnl = sum(float(t.get('pnl_pct', 0)) for t in trades if t.get('pnl_pct'))
print(f"Total trades: {len(trades)}")
print(f"Total P&L: {total_pnl:.2f}%")
EOF
```

### Enter a paper trade manually

```bash
# Track A, BUY BTC at current market
python3 live/paper_trading/track_manager.py update A BUY BTC 85000 0.1

# Track A, CLOSE position
python3 live/paper_trading/track_manager.py update A SELL BTC 87000 0.1
```

---

## How to Deploy / Restart Services

### Market Monitor Daemon

```bash
# First-time install
sudo cp live/monitor/market-monitor.service /etc/systemd/system/pinch-market-monitor.service
sudo systemctl daemon-reload
sudo systemctl enable pinch-market-monitor
sudo systemctl start pinch-market-monitor

# Check it's running
sudo systemctl status pinch-market-monitor

# View live logs
journalctl -u pinch-market-monitor -f

# Restart after code changes
sudo systemctl restart pinch-market-monitor

# Stop
sudo systemctl stop pinch-market-monitor
```

### Data Collector (manual run)

```bash
cd /mnt/media/market_data

# Full collection
python3 collect.py all

# Individual collectors
python3 collect.py crypto
python3 collect.py stocks
python3 collect.py macro

# Status
python3 collect.py status

# Backup DB
python3 collect.py backup
```

### Setting up cron for data collection

```bash
crontab -e
```

Add:

```cron
# Hourly crypto prices
0 * * * * cd /mnt/media/market_data && python3 collect.py crypto >> logs/collect.log 2>&1

# Daily full collection at 6:30 AM ET
30 10 * * * cd /mnt/media/market_data && python3 collect.py all >> logs/collect.log 2>&1

# Weekly backup Sunday midnight
0 5 * * 0 cd /mnt/media/market_data && python3 collect.py backup >> logs/collect.log 2>&1
```

### Test Discord alert

```bash
python3 live/monitor/market_monitor.py test-alert
```

---

## Emergency Procedures

### Kill Switch Protocol

**Trigger:** Bob says "go flat", "kill switch", or drawdown exceeds 15%.

```bash
# Step 1: Check current state
python3 live/execution/kill_switch.py status

# Step 2: Health check
python3 live/execution/kill_switch.py check

# Step 3: EXECUTE — cancels all orders, market-sells all positions
python3 live/execution/kill_switch.py kill
```

What it does:
1. Connects to Kraken via API
2. Cancels ALL open/resting orders
3. Market-sells ALL open positions (BTC, ETH, SOL)
4. Logs to `logs/trades/kill_switch_log.csv`
5. Sets `trading_halted: true` in `live/config/risk_state.json`

**After kill switch:** No new trades until Bob explicitly re-authorizes (`trading_halted` must be reset to `false`).

### Exchange API Outage

1. Do NOT enter new positions
2. Monitor positions via exchange web UI
3. Manually place stop-loss orders via web UI if API unresponsive >5 minutes
4. Alert Bob
5. Attempt restart of market monitor: `sudo systemctl restart pinch-market-monitor`
6. Resume automated operations only when API confirmed stable

### Flash Crash (>15% move in <1 hour)

1. Check if stop-losses executed (review `logs/trades/paper_trades.csv` or live positions)
2. Do NOT revenge trade or chase
3. Execute kill switch if stops didn't fill and losses mounting
4. Go to cash, reassess next session
5. Report full P&L and event timeline to Bob

### Data Collection Failure

```bash
# Check what failed
sqlite3 /mnt/media/market_data/pinch_market.db \
  "SELECT * FROM collection_log WHERE status='error' ORDER BY timestamp DESC LIMIT 10;"

# Re-run failed collector
cd /mnt/media/market_data && python3 collect.py crypto   # or macro/stocks

# Check DB integrity
sqlite3 /mnt/media/market_data/pinch_market.db "PRAGMA integrity_check;"

# Restore from backup if needed
ls -lh /mnt/media/market_data/backups/
gunzip -c backups/pinch_market_YYYYMMDD.db.gz > pinch_market.db
```

---

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
