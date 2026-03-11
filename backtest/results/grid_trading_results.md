# Grid Trading Backtest — ETH/USD

**Period:** 2022-01-01 → 2026-03-01
**Initial Capital:** $100,000  
**Grid Allocation:** $50,000 (50%)  
**Grid Levels:** 10 above + 10 below center  
**Fee Rate:** 0.1% per side  
**Grid Spacings Tested:** $50 · $100 · $150 · $200

## ETH Buy & Hold Benchmark

| Metric | Value |
|--------|-------|
| Entry Price | $3,769.70 |
| Exit Price  | $1,939.07 |
| Final Value | $51,438.26 |
| Total Return | -48.56% |

## Strategy Comparison

| Metric | $50 Grid | $100 Grid | $150 Grid | $200 Grid | Buy & Hold |
|--------|----------|-----------|-----------|-----------|------------|
| Final Value | $136,619.34 | $170,992.83 | $180,527.47 | $164,740.15 | $51,438.26 |
| Total Return | +36.62% | +70.99% | +80.53% | +64.74% | -48.56% |
| Annualized Return | +7.79% | +13.76% | +15.25% | +12.74% | — |
| Max Drawdown | -30.98% | -23.21% | -20.37% | -17.24% | — |
| Realized P&L | +$28,649.55 | +$44,010.72 | +$46,952.46 | +$37,344.36 | — |
| Total Fees | $4,688.61 | $3,118.00 | $2,029.53 | $1,153.33 | — |
| # Completed Cycles | 502 | 355 | 246 | 145 | — |
| Buy Fills | 512 | 365 | 256 | 154 | — |
| Sell Fills | 502 | 355 | 246 | 145 | — |
| Avg Fills/Month | 50.7 | 31.3 | 16.7 | 8.1 | — |
| Profit/Cycle | +$57.07 | +$123.97 | +$190.86 | +$257.55 | — |
| ETH Held at End | 13.2637 ETH | 13.2637 ETH | 13.2637 ETH | 11.9373 ETH | — |

---

## Grid Spacing: $50.0

### Summary

| Metric | Value |
|--------|-------|
| Grid Center (Start) | $3,769.70 |
| ETH Price at End | $1,939.07 |
| Final Account Value | $136,619.34 |
| Realized P&L | +$28,649.55 |
| Unrealized P&L | -$24,280.87 |
| Total Fees Paid | $4,688.61 |
| Total Return | +36.62% |
| Annualized Return | +7.79% |
| Max Drawdown | -30.98% |
| Completed Grid Cycles | 502 |
| Buy Fills | 512 |
| Sell Fills | 502 |
| Avg Fills per Month | 50.7 |
| Avg Profit per Cycle | +$57.07 |
| ETH Remaining | 13.2637 ETH |
| Grid Cash Remaining | $32,250.66 |
| vs Buy & Hold | +85.18% alpha |

### Monthly P&L (Realized, $50.0 Grid)

| Month | Fills | Net P&L |
|-------|-------|---------|
| 2022-01 | 52 | +$1,199.60 |
| 2022-03 | 13 | +$458.90 |
| 2022-04 | 27 | +$686.83 |
| 2024-02 | 10 | +$401.46 |
| 2024-03 | 143 | +$4,160.51 |
| 2024-04 | 77 | +$1,999.99 |
| 2024-05 | 30 | +$1,134.72 |
| 2024-06 | 79 | +$2,053.06 |
| 2024-07 | 58 | +$1,604.90 |
| 2024-08 | 1 | +$0.00 |
| 2024-11 | 59 | +$1,946.39 |
| 2024-12 | 126 | +$3,418.62 |
| 2025-01 | 100 | +$2,864.59 |
| 2025-02 | 5 | +$57.58 |
| 2025-07 | 56 | +$1,873.16 |
| 2025-08 | 42 | +$1,192.83 |
| 2025-10 | 24 | +$678.74 |
| 2025-11 | 94 | +$2,400.25 |
| 2025-12 | 10 | +$287.36 |
| 2026-01 | 8 | +$230.05 |

**Best Month:** 2024-03 (+$4,160.51)  
**Worst Month:** 2025-02 (+$57.58)

---

## Grid Spacing: $100.0

### Summary

| Metric | Value |
|--------|-------|
| Grid Center (Start) | $3,769.70 |
| ETH Price at End | $1,939.07 |
| Final Account Value | $170,992.83 |
| Realized P&L | +$44,010.72 |
| Unrealized P&L | -$24,280.87 |
| Total Fees Paid | $3,118.00 |
| Total Return | +70.99% |
| Annualized Return | +13.76% |
| Max Drawdown | -23.21% |
| Completed Grid Cycles | 355 |
| Buy Fills | 365 |
| Sell Fills | 355 |
| Avg Fills per Month | 31.3 |
| Avg Profit per Cycle | +$123.97 |
| ETH Remaining | 13.2637 ETH |
| Grid Cash Remaining | $51,262.99 |
| vs Buy & Hold | +119.55% alpha |

### Monthly P&L (Realized, $100.0 Grid)

| Month | Fills | Net P&L |
|-------|-------|---------|
| 2022-01 | 48 | +$2,356.76 |
| 2022-02 | 31 | +$1,994.55 |
| 2022-03 | 13 | +$1,120.31 |
| 2022-04 | 34 | +$1,740.52 |
| 2022-05 | 6 | +$375.47 |
| 2024-02 | 9 | +$994.09 |
| 2024-03 | 61 | +$3,825.21 |
| 2024-04 | 68 | +$3,969.20 |
| 2024-05 | 30 | +$2,228.95 |
| 2024-06 | 26 | +$1,356.83 |
| 2024-07 | 39 | +$2,359.41 |
| 2024-08 | 13 | +$499.04 |
| 2024-11 | 35 | +$2,727.98 |
| 2024-12 | 45 | +$2,588.77 |
| 2025-01 | 56 | +$3,467.78 |
| 2025-02 | 18 | +$749.08 |
| 2025-06 | 2 | +$125.16 |
| 2025-07 | 24 | +$2,101.67 |
| 2025-08 | 16 | +$985.07 |
| 2025-10 | 8 | +$491.87 |
| 2025-11 | 70 | +$3,844.31 |
| 2025-12 | 36 | +$2,241.95 |
| 2026-01 | 32 | +$1,866.74 |

**Best Month:** 2024-04 (+$3,969.20)  
**Worst Month:** 2025-06 (+$125.16)

---

## Grid Spacing: $150.0

### Summary

| Metric | Value |
|--------|-------|
| Grid Center (Start) | $3,769.70 |
| ETH Price at End | $1,939.07 |
| Final Account Value | $180,527.47 |
| Realized P&L | +$46,952.46 |
| Unrealized P&L | -$24,280.87 |
| Total Fees Paid | $2,029.53 |
| Total Return | +80.53% |
| Annualized Return | +15.25% |
| Max Drawdown | -20.37% |
| Completed Grid Cycles | 246 |
| Buy Fills | 256 |
| Sell Fills | 246 |
| Avg Fills per Month | 16.7 |
| Avg Profit per Cycle | +$190.86 |
| ETH Remaining | 13.2637 ETH |
| Grid Cash Remaining | $57,855.88 |
| vs Buy & Hold | +129.09% alpha |

### Monthly P&L (Realized, $150.0 Grid)

| Month | Fills | Net P&L |
|-------|-------|---------|
| 2022-01 | 36 | +$2,675.61 |
| 2022-02 | 22 | +$2,298.10 |
| 2022-03 | 15 | +$1,720.69 |
| 2022-04 | 11 | +$762.58 |
| 2022-05 | 12 | +$769.75 |
| 2023-12 | 2 | +$192.74 |
| 2024-01 | 6 | +$577.81 |
| 2024-02 | 10 | +$1,720.69 |
| 2024-03 | 37 | +$3,603.47 |
| 2024-04 | 31 | +$2,664.47 |
| 2024-05 | 14 | +$1,711.94 |
| 2024-06 | 16 | +$1,326.86 |
| 2024-07 | 15 | +$1,333.63 |
| 2024-08 | 23 | +$1,727.85 |
| 2024-09 | 7 | +$769.75 |
| 2024-10 | 11 | +$960.89 |
| 2024-11 | 19 | +$2,478.90 |
| 2024-12 | 24 | +$2,085.47 |
| 2025-01 | 26 | +$2,471.73 |
| 2025-02 | 31 | +$2,302.08 |
| 2025-03 | 4 | +$385.47 |
| 2025-05 | 18 | +$1,922.18 |
| 2025-06 | 13 | +$1,153.63 |
| 2025-07 | 13 | +$2,095.02 |
| 2025-08 | 6 | +$568.26 |
| 2025-10 | 4 | +$378.71 |
| 2025-11 | 37 | +$3,045.16 |
| 2025-12 | 18 | +$1,717.11 |
| 2026-01 | 17 | +$1,339.20 |
| 2026-02 | 4 | +$192.74 |

**Best Month:** 2024-03 (+$3,603.47)  
**Worst Month:** 2023-12 (+$192.74)

---

## Grid Spacing: $200.0

### Summary

| Metric | Value |
|--------|-------|
| Grid Center (Start) | $3,769.70 |
| ETH Price at End | $1,939.07 |
| Final Account Value | $164,740.15 |
| Realized P&L | +$37,344.36 |
| Unrealized P&L | -$21,852.78 |
| Total Fees Paid | $1,153.33 |
| Total Return | +64.74% |
| Annualized Return | +12.74% |
| Max Drawdown | -17.24% |
| Completed Grid Cycles | 145 |
| Buy Fills | 154 |
| Sell Fills | 145 |
| Avg Fills per Month | 8.1 |
| Avg Profit per Cycle | +$257.55 |
| ETH Remaining | 11.9373 ETH |
| Grid Cash Remaining | $54,248.56 |
| vs Buy & Hold | +113.30% alpha |

### Monthly P&L (Realized, $200.0 Grid)

| Month | Fills | Net P&L |
|-------|-------|---------|
| 2022-01 | 24 | +$2,317.89 |
| 2022-02 | 11 | +$1,547.03 |
| 2022-03 | 7 | +$1,287.24 |
| 2022-04 | 9 | +$770.33 |
| 2022-05 | 12 | +$1,039.66 |
| 2022-06 | 1 | +$0.00 |
| 2022-08 | 2 | +$260.31 |
| 2023-04 | 1 | +$260.31 |
| 2023-05 | 1 | +$0.00 |
| 2023-07 | 1 | +$260.31 |
| 2023-08 | 1 | +$0.00 |
| 2023-11 | 1 | +$260.31 |
| 2023-12 | 4 | +$778.29 |
| 2024-01 | 6 | +$777.23 |
| 2024-02 | 5 | +$1,288.30 |
| 2024-03 | 17 | +$2,304.09 |
| 2024-04 | 14 | +$1,541.19 |
| 2024-05 | 9 | +$1,538.01 |
| 2024-06 | 4 | +$256.07 |
| 2024-07 | 6 | +$770.33 |
| 2024-08 | 16 | +$1,550.21 |
| 2024-09 | 4 | +$517.97 |
| 2024-10 | 2 | +$258.72 |
| 2024-11 | 9 | +$1,800.97 |
| 2024-12 | 13 | +$1,534.82 |
| 2025-01 | 14 | +$1,795.67 |
| 2025-02 | 20 | +$1,808.40 |
| 2025-03 | 8 | +$778.82 |
| 2025-05 | 10 | +$1,813.71 |
| 2025-06 | 5 | +$517.44 |
| 2025-07 | 9 | +$2,055.45 |
| 2025-08 | 4 | +$511.61 |
| 2025-10 | 2 | +$255.54 |
| 2025-11 | 18 | +$1,795.67 |
| 2025-12 | 10 | +$1,285.65 |
| 2026-01 | 12 | +$1,287.24 |
| 2026-02 | 7 | +$519.57 |

**Best Month:** 2022-01 (+$2,317.89)  
**Worst Month:** 2025-10 (+$255.54)

---

## Key Observations

- **Best Total Return:** $150.0 grid (+80.53%)
- **Most Active (Cycles):** $50.0 grid (502 completed cycles)
- **Lowest Drawdown:** $200.0 grid (-17.24%)
- **Buy & Hold Return:** -48.56% ($51,438.26)

### Grid Trading Dynamics

- Tighter grids ($50) generate more fills and cycles but each cycle profits less.
- Wider grids ($200) profit more per cycle but fill less frequently.
- High-volatility periods (2022 bear, 2024-2025 bull) drive most grid activity.
- ETH's net decline from $3,769 → ~$1,939 (−49%) creates a challenging environment:
  grid buys accumulate inventory in declining market; unrealized losses offset realized gains.
- Grid trading outperforms buy-and-hold when price oscillates in a range;
  strong directional trends (especially down) reduce effectiveness.

---

*Generated by run_grid_backtest.py — Pinch Grid Trading Engine*