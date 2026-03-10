# Live Account Status

## Kraken Account

| Field | Value |
|-------|-------|
| **Exchange** | Kraken |
| **Account Status** | Active, verified |
| **API Status** | ✅ Connected, trade-enabled |
| **Funded** | 2026-03-10 |
| **Starting Capital** | ~$752 (0.3679 ETH) |

## Current Balances (2026-03-10 16:30 ET)

| Asset | Amount | USD Value |
|-------|--------|-----------|
| ETH | 0.366870 | $749.96 |
| BTC | 0.000008 | $0.53 |
| USD | 1.98 | $1.98 |
| **TOTAL** | | **$752.47** |

## Test Trades Completed

| Time | Action | Pair | Amount | Price | Cost | Status |
|------|--------|------|--------|-------|------|--------|
| 2026-03-10 16:28 | SELL | ETH/USD | 0.004 | $2,043.67 | $8.17 | ✅ Filled |
| 2026-03-10 16:30 | BUY | ETH/USD | 0.003 | ~$2,044 | $6.13 | ✅ Filled |

**Test trade result:** Round-trip executed successfully. Market orders filling correctly. Fees ~0.40% taker as expected.

## Trading Client

- Location: `.secrets/kraken_trader.py` (not in this repo for security)
- Capabilities: balance, ticker, orders, trades, market buy/sell, limit buy/sell, stop-loss
- Validated: order placement, execution, balance queries, trade history

## High-Water Mark

| Date | Value |
|------|-------|
| 2026-03-10 | $752.47 (initial) |
