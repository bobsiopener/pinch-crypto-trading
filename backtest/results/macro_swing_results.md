# Macro Swing Strategy — Backtest Results

**Generated:** 2026-03-10 17:22 UTC  
**Period:** 2022-01-01 → 2026-03-01  
**Initial Capital:** $100,000.00  

---

## Strategy Performance

| Metric | Macro Swing | Buy & Hold BTC |
|--------|-------------|----------------|
| Final Value | $105,228.04 | $137,853.84 |
| Total Return | 5.23% | 37.85% |
| Annualized Return | 1.23% | 8.02% |
| Max Drawdown | 3.33% | 66.89% |
| Sharpe Ratio | 1.403 | N/A |

---

## Trade Statistics

| Metric | Value |
|--------|-------|
| Number of Trades | 10 |
| Win Rate | 70.00% |
| Average Win | 7.25% |
| Average Loss | -8.40% |
| Profit Factor | 2.015 |

### Exit Reasons
- **stop_loss**: 3
- **time_stop**: 7

---

## Benchmark Comparison

- BTC Start Price: $47,686.81 (2022-01-01)
- BTC End Price: $65,738.10 (2026-03-01)
- Buy & Hold Return: 37.85%
- Strategy Return: 5.23%
- **Alpha vs BH:** -32.63%

---

## Strategy Signal Log (first 50 entries)

```
SIGNAL 2024-01-05 | score=-1 | NFP strong: -1
SIGNAL 2024-01-11 | score=-2 | CPI hot (3.4 vs 3.2): -2
SIGNAL 2024-01-31 | score=+0 | FOMC neutral (hold, rate→5.5%): 0
SIGNAL 2024-02-02 | score=-1 | NFP strong: -1
SIGNAL 2024-02-13 | score=-2 | CPI hot (3.1 vs 2.9): -2
SIGNAL 2024-03-08 | score=-1 | NFP strong: -1
SIGNAL 2024-03-12 | score=-2 | CPI hot (3.2 vs 3.1): -2
SIGNAL 2024-03-20 | score=+0 | FOMC neutral (hold, rate→5.5%): 0
SIGNAL 2024-04-05 | score=-1 | NFP strong: -1
SIGNAL 2024-04-10 | score=-2 | CPI hot (3.5 vs 3.4): -2
SIGNAL 2024-05-01 | score=+0 | FOMC neutral (hold, rate→5.5%): 0
SIGNAL 2024-05-03 | score=+1 | NFP weak (rate 5.50% > 4%): +1
SIGNAL 2024-05-15 | score=+0 | CPI neutral (3.4 vs 3.4): 0
SIGNAL 2024-06-07 | score=-1 | NFP strong: -1
SIGNAL 2024-06-12 | score=+2 | CPI cool (3.3 vs 3.4): +2 | FOMC neutral (hold, rate→5.5%): 0
OPEN 2024-06-12 | score=+2 | LONG 20% | entry=68241.19 SL=62781.89 TP=79159.78 | Account=100000.00
CLOSE 2024-06-24 | stop_loss | entry=68241.19 exit=62781.89 | PnL=-8.40% | Account=98320.00
SIGNAL 2024-07-05 | score=+0 | NFP neutral: 0
SIGNAL 2024-07-11 | score=+2 | CPI cool (3.0 vs 3.1): +2
OPEN 2024-07-11 | score=+2 | LONG 20% | entry=57344.91 SL=52757.32 TP=66520.10 | Account=98320.00
PARTIAL_TP 2024-07-19 | price=66520.10 | 60% taken | partial_pnl=15.80% | Account=100184.15
CLOSE 2024-07-25 | time_stop | entry=57344.91 exit=65777.23 | PnL=15.28% | Account=101325.02
SIGNAL 2024-07-31 | score=+0 | FOMC neutral (hold, rate→5.5%): 0
SIGNAL 2024-08-02 | score=+1 | NFP weak (rate 5.50% > 4%): +1
SIGNAL 2024-08-14 | score=+2 | CPI cool (2.9 vs 3.0): +2
OPEN 2024-08-14 | score=+2 | LONG 20% | entry=58737.27 SL=54038.29 TP=68135.23 | Account=101325.02
CLOSE 2024-08-28 | time_stop | entry=58737.27 exit=59027.62 | PnL=0.09% | Account=101344.13
SIGNAL 2024-09-06 | score=+1 | NFP weak (rate 5.50% > 4%): +1
SIGNAL 2024-09-11 | score=+2 | CPI cool (2.5 vs 2.6): +2
OPEN 2024-09-11 | score=+2 | LONG 20% | entry=57343.17 SL=52755.72 TP=66518.08 | Account=101344.13
SIGNAL 2024-09-18 | score=+3 | FOMC dovish (cut25, rate→5.0%): +3
CLOSE 2024-09-25 | time_stop | entry=57343.17 exit=63143.14 | PnL=9.71% | Account=103313.15
SIGNAL 2024-10-04 | score=-1 | NFP strong: -1
SIGNAL 2024-10-10 | score=-2 | CPI hot (2.4 vs 2.3): -2
SIGNAL 2024-11-01 | score=+1 | NFP weak (rate 5.00% > 4%): +1
SIGNAL 2024-11-07 | score=+0 | FOMC neutral (cut25, rate→4.75%): 0
SIGNAL 2024-11-13 | score=+0 | CPI neutral (2.6 vs 2.6): 0
SIGNAL 2024-12-06 | score=+0 | NFP neutral: 0
SIGNAL 2024-12-11 | score=+0 | CPI neutral (2.7 vs 2.7): 0
SIGNAL 2024-12-18 | score=-3 | FOMC hawkish (cut25, rate→4.5%): -3
SIGNAL 2025-01-10 | score=-1 | NFP strong: -1
SIGNAL 2025-01-15 | score=+0 | CPI neutral (2.9 vs 2.9): 0
SIGNAL 2025-01-29 | score=+0 | FOMC neutral (hold, rate→4.5%): 0
SIGNAL 2025-02-07 | score=+1 | NFP weak (rate 4.50% > 4%): +1
SIGNAL 2025-02-12 | score=-2 | CPI hot (3.0 vs 2.9): -2
SIGNAL 2025-03-07 | score=+0 | NFP neutral: 0
SIGNAL 2025-03-12 | score=+2 | CPI cool (2.8 vs 2.9): +2
OPEN 2025-03-12 | score=+2 | LONG 20% | entry=83722.36 SL=77024.57 TP=97117.94 | Account=103313.15
SIGNAL 2025-03-19 | score=+0 | FOMC neutral (cut25, rate→4.25%): 0
CLOSE 2025-03-26 | time_stop | entry=83722.36 exit=86900.88 | PnL=3.40% | Account=104014.95
```

---

## Trade Log Summary

| # | Entry | Exit | Entry $ | Exit $ | PnL% | Reason |
|---|-------|------|---------|--------|------|--------|
| 1 | 2024-06-12 | 2024-06-24 | $68,241.19 | $62,781.89 | -8.40% | stop_loss |
| 2 | 2024-07-11 | 2024-07-25 | $57,344.91 | $65,777.23 | 15.28% | time_stop |
| 3 | 2024-08-14 | 2024-08-28 | $58,737.27 | $59,027.62 | 0.09% | time_stop |
| 4 | 2024-09-11 | 2024-09-25 | $57,343.17 | $63,143.14 | 9.71% | time_stop |
| 5 | 2025-03-12 | 2025-03-26 | $83,722.36 | $86,900.88 | 3.40% | time_stop |
| 6 | 2025-04-10 | 2025-04-24 | $79,626.14 | $93,943.80 | 16.59% | time_stop |
| 7 | 2025-05-13 | 2025-05-27 | $104,169.81 | $108,994.64 | 4.23% | time_stop |
| 8 | 2025-06-11 | 2025-06-22 | $108,686.62 | $99,991.70 | -8.40% | stop_loss |
| 9 | 2025-08-12 | 2025-08-25 | $120,172.91 | $110,559.07 | -8.40% | stop_loss |
| 10 | 2025-09-17 | 2025-10-01 | $116,468.51 | $118,648.93 | 1.47% | time_stop |

---

## Notes

- **Signal Source:** CPI, FOMC, NFP macro events (2024-2026 data)
- **Trading Costs:** 0.40% round-trip (Kraken taker fees)  
- **Risk:** 8% stop-loss, 16% take-profit (2:1 R:R), 14-day time stop
- **Position Sizing:** 20% (score±2) or 30% (score≥±3) of account
- **Data Source:** CoinGecko free API + manual macro event database

> *Rule of Acquisition #22: A wise man can hear profit in the wind.*
