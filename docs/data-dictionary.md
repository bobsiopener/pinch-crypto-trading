# Pinch Market Data — Data Dictionary

> *"Rule of Acquisition #74: Knowledge equals profit."*

Database: `/mnt/media/market_data/pinch_market.db` (SQLite, WAL mode)  
Schema: `market_data/schema.sql`

---

## Table Index

| # | Table | Purpose | Update Frequency |
|---|---|---|---|
| 1 | [prices](#1-prices) | OHLCV bars for all assets | Hourly (crypto), Daily (stocks) |
| 2 | [options_chain](#2-options_chain) | Options contracts | Daily |
| 3 | [derived_metrics](#3-derived_metrics) | Max pain, P/C ratio, IV rank | Daily |
| 4 | [funding_rates](#4-funding_rates) | Crypto perp funding rates | Every 8 hours |
| 5 | [onchain_metrics](#5-onchain_metrics) | BTC/ETH on-chain data | Daily |
| 6 | [sentiment](#6-sentiment) | Fear & Greed, Reddit | Daily |
| 7 | [etf_flows](#7-etf_flows) | BTC ETF inflows/outflows | Daily |
| 8 | [liquidations](#8-liquidations) | Crypto liquidation events | Hourly |
| 9 | [long_short_ratios](#9-long_short_ratios) | Binance L/S ratios | Hourly |
| 10 | [economic_data](#10-economic_data) | FRED macro series | On release |
| 11 | [prediction_markets](#11-prediction_markets) | Kalshi / Polymarket | Daily |
| 12 | [orderbook_snapshots](#12-orderbook_snapshots) | L2 orderbook top-of-book | Hourly |
| 13 | [vix_term_structure](#13-vix_term_structure) | VIX futures curve | Daily |
| 14 | [collection_log](#14-collection_log) | Collection health audit | Every run |

---

## 1. `prices`

**Purpose:** Core OHLCV price data for all tracked assets — crypto, stocks, ETFs, indexes, commodities, and FX.

**Data Sources:** CoinGecko, Kraken, Binance, Yahoo Finance

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Auto-increment row ID |
| `timestamp` | INTEGER | Unix seconds (UTC) |
| `symbol` | TEXT | Ticker: `'BTC'`, `'ETH'`, `'AAPL'`, `'SPY'` |
| `asset_class` | TEXT | `'crypto'`, `'stock'`, `'etf'`, `'index'`, `'commodity'`, `'fx'` |
| `source` | TEXT | `'kraken'`, `'yahoo'`, `'binance'`, `'coingecko'` |
| `timeframe` | TEXT | `'1m'`, `'5m'`, `'1h'`, `'1d'` |
| `open` | REAL | Open price |
| `high` | REAL | High price |
| `low` | REAL | Low price |
| `close` | REAL | Close price |
| `volume` | REAL | Volume in base currency |

**Unique constraint:** `(timestamp, symbol, source, timeframe)`

**Indexes:** `(symbol, timestamp)`, `(asset_class, timestamp)`

**Sample queries:**

```sql
-- Latest BTC daily close
SELECT datetime(timestamp, 'unixepoch'), close
FROM prices
WHERE symbol = 'BTC' AND timeframe = '1d'
ORDER BY timestamp DESC
LIMIT 10;

-- 30-day BTC price history for backtesting
SELECT date(timestamp, 'unixepoch') AS date, open, high, low, close, volume
FROM prices
WHERE symbol = 'BTC' AND timeframe = '1d'
  AND timestamp >= strftime('%s', 'now', '-30 days')
ORDER BY timestamp;

-- All crypto assets tracked
SELECT DISTINCT symbol FROM prices WHERE asset_class = 'crypto';

-- Compare ETF performance over past week
SELECT symbol, 
       first_value(close) OVER (PARTITION BY symbol ORDER BY timestamp) AS start_price,
       last_value(close) OVER (PARTITION BY symbol ORDER BY timestamp
         ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS end_price
FROM prices
WHERE asset_class = 'etf' AND timeframe = '1d'
  AND timestamp >= strftime('%s', 'now', '-7 days');
```

---

## 2. `options_chain`

**Purpose:** Full options chain data — strike prices, expirations, greeks, and market data for BTC/ETH (Deribit) and equities (yfinance).

**Data Sources:** Deribit (BTC/ETH crypto options), Binance, yfinance

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Auto-increment row ID |
| `timestamp` | INTEGER | Unix seconds (UTC) |
| `symbol` | TEXT | Underlying: `'BTC'`, `'ETH'`, `'SPY'` |
| `asset_class` | TEXT | `'crypto'`, `'stock'`, `'etf'` |
| `source` | TEXT | `'deribit'`, `'binance'`, `'yahoo'` |
| `expiry` | TEXT | Expiration date: `'YYYY-MM-DD'` |
| `strike` | REAL | Strike price in USD |
| `option_type` | TEXT | `'C'` (call) or `'P'` (put) |
| `open_interest` | REAL | Open interest in contracts |
| `volume` | REAL | Daily volume |
| `bid` | REAL | Best bid price |
| `ask` | REAL | Best ask price |
| `last_price` | REAL | Last traded price |
| `mark_price` | REAL | Mark price (mid-market) |
| `implied_volatility` | REAL | IV as decimal (0.85 = 85%) |
| `delta` | REAL | Delta greek |
| `gamma` | REAL | Gamma greek |
| `theta` | REAL | Theta greek (daily) |
| `vega` | REAL | Vega greek |
| `underlying_price` | REAL | Spot price at snapshot time |

**Unique constraint:** `(timestamp, symbol, source, expiry, strike, option_type)`

**Indexes:** `(symbol, timestamp)`, `(symbol, expiry, strike)`

**Sample queries:**

```sql
-- Current BTC options for nearest expiry
SELECT expiry, strike, option_type, open_interest, implied_volatility
FROM options_chain
WHERE symbol = 'BTC'
  AND timestamp = (SELECT MAX(timestamp) FROM options_chain WHERE symbol = 'BTC')
ORDER BY expiry, strike;

-- Max pain calculation: strike with max total OI value (simplified)
SELECT strike,
       SUM(CASE WHEN option_type = 'C' THEN open_interest ELSE 0 END) AS call_oi,
       SUM(CASE WHEN option_type = 'P' THEN open_interest ELSE 0 END) AS put_oi,
       SUM(open_interest) AS total_oi
FROM options_chain
WHERE symbol = 'BTC'
  AND expiry = (SELECT MIN(expiry) FROM options_chain
                WHERE symbol = 'BTC' AND expiry > date('now'))
  AND timestamp = (SELECT MAX(timestamp) FROM options_chain WHERE symbol = 'BTC')
GROUP BY strike
ORDER BY total_oi DESC
LIMIT 10;

-- Put/Call ratio (OI-based)
SELECT 
  SUM(CASE WHEN option_type = 'P' THEN open_interest ELSE 0 END) /
  SUM(CASE WHEN option_type = 'C' THEN open_interest ELSE 0 END) AS pc_ratio
FROM options_chain
WHERE symbol = 'BTC'
  AND timestamp = (SELECT MAX(timestamp) FROM options_chain WHERE symbol = 'BTC');
```

---

## 3. `derived_metrics`

**Purpose:** Pre-computed metrics derived from options and price data — max pain level, P/C ratio, IV rank, IV percentile, market cap.

**Data Sources:** Computed from `options_chain` and `prices` tables

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Auto-increment row ID |
| `timestamp` | INTEGER | Unix seconds (UTC) |
| `symbol` | TEXT | Asset ticker |
| `source` | TEXT | Computing source/version |
| `metric` | TEXT | `'max_pain'`, `'pc_ratio_oi'`, `'pc_ratio_vol'`, `'iv_rank'`, `'iv_percentile'`, `'market_cap'` |
| `value` | REAL | Metric value |
| `metadata` | TEXT | JSON blob for additional context |

**Unique constraint:** `(timestamp, symbol, source, metric)`

**Index:** `(symbol, metric, timestamp)`

**Sample queries:**

```sql
-- Latest max pain for BTC
SELECT datetime(timestamp, 'unixepoch'), value AS max_pain_usd
FROM derived_metrics
WHERE symbol = 'BTC' AND metric = 'max_pain'
ORDER BY timestamp DESC LIMIT 5;

-- IV rank history (high IV = options expensive = sell premium)
SELECT date(timestamp, 'unixepoch'), value AS iv_rank
FROM derived_metrics
WHERE symbol = 'BTC' AND metric = 'iv_rank'
ORDER BY timestamp DESC LIMIT 30;

-- P/C ratio trend
SELECT date(timestamp, 'unixepoch'), value
FROM derived_metrics
WHERE symbol = 'BTC' AND metric = 'pc_ratio_oi'
ORDER BY timestamp DESC LIMIT 14;
```

---

## 4. `funding_rates`

**Purpose:** Perpetual futures funding rates — indicates market sentiment (positive = longs paying, bearish signal; negative = shorts paying, bullish signal).

**Data Sources:** Binance perpetuals (BTC, ETH, SOL)

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Auto-increment row ID |
| `timestamp` | INTEGER | Funding settlement time (Unix seconds) |
| `symbol` | TEXT | `'BTC'`, `'ETH'`, `'SOL'` |
| `exchange` | TEXT | `'binance'`, `'bybit'` |
| `rate` | REAL | Funding rate as decimal (0.0001 = 0.01%, charged every 8h) |

**Unique constraint:** `(timestamp, symbol, exchange)`

**Index:** `(symbol, timestamp)`

**Sample queries:**

```sql
-- Latest BTC funding rate
SELECT datetime(timestamp, 'unixepoch'), rate, rate * 3 * 365 AS annualized_pct
FROM funding_rates
WHERE symbol = 'BTC' AND exchange = 'binance'
ORDER BY timestamp DESC LIMIT 1;

-- 7-day average funding (market sentiment)
SELECT symbol, AVG(rate) AS avg_rate,
       CASE WHEN AVG(rate) > 0.0005 THEN 'BULLISH_EXTREME'
            WHEN AVG(rate) > 0.0001 THEN 'BULLISH'
            WHEN AVG(rate) < -0.0001 THEN 'BEARISH'
            ELSE 'NEUTRAL' END AS sentiment
FROM funding_rates
WHERE timestamp >= strftime('%s', 'now', '-7 days')
GROUP BY symbol;
```

---

## 5. `onchain_metrics`

**Purpose:** Blockchain-native signals — on-chain health, miner behavior, network activity.

**Data Sources:** Blockchain APIs (Glassnode proxy, public endpoints)

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Auto-increment row ID |
| `timestamp` | INTEGER | Unix seconds (UTC) |
| `symbol` | TEXT | `'BTC'`, `'ETH'` |
| `metric` | TEXT | See metric list below |
| `source` | TEXT | Data provider |
| `value` | REAL | Metric value |
| `metadata` | TEXT | JSON — units, notes |

**Key metrics:**

| Metric | Description | Signal |
|---|---|---|
| `mvrv` | Market Value to Realized Value ratio | >3.5 = overvalued; <1 = undervalued |
| `exchange_reserve` | BTC on exchanges (supply) | Declining = bullish (HODLers) |
| `active_addresses` | Daily active addresses | Network usage proxy |
| `hash_rate` | Mining hash rate (EH/s) | Security / miner confidence |
| `mempool_size` | Unconfirmed txs | Network congestion |
| `sopr` | Spent Output Profit Ratio | >1 = profit-taking |
| `nupl` | Net Unrealized Profit/Loss | Sentiment gauge |

**Sample queries:**

```sql
-- Latest MVRV ratio
SELECT datetime(timestamp, 'unixepoch'), value AS mvrv
FROM onchain_metrics
WHERE symbol = 'BTC' AND metric = 'mvrv'
ORDER BY timestamp DESC LIMIT 1;

-- On-chain composite score (simplified)
SELECT 
  AVG(CASE WHEN metric = 'mvrv' AND value < 2.0 THEN 1
           WHEN metric = 'mvrv' AND value > 3.5 THEN -1
           ELSE 0 END) AS mvrv_signal,
  MAX(timestamp) AS latest
FROM onchain_metrics
WHERE symbol = 'BTC'
  AND timestamp >= strftime('%s', 'now', '-1 days');
```

---

## 6. `sentiment`

**Purpose:** Market sentiment indicators — fear/greed index, social media sentiment.

**Data Sources:** Alternative.me (Crypto Fear & Greed), CNN (Equity Fear & Greed), Reddit

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Auto-increment row ID |
| `timestamp` | INTEGER | Unix seconds (UTC) |
| `indicator` | TEXT | See list below |
| `source` | TEXT | Data provider |
| `value` | REAL | 0-100 scale (sentiment index) or raw score |
| `label` | TEXT | Human-readable: `'Extreme Fear'`, `'Greed'`, etc. |
| `metadata` | TEXT | JSON — additional context |

**Key indicators:**

| Indicator | Range | Source |
|---|---|---|
| `fear_greed_crypto` | 0–100 | Alternative.me |
| `fear_greed_stocks` | 0–100 | CNN |
| `google_trends_btc` | 0–100 | Google Trends |
| `reddit_wsb` | Float | Reddit activity score |

**Sample queries:**

```sql
-- Current crypto fear & greed
SELECT datetime(timestamp, 'unixepoch'), value, label
FROM sentiment
WHERE indicator = 'fear_greed_crypto'
ORDER BY timestamp DESC LIMIT 1;

-- 30-day sentiment trend
SELECT date(timestamp, 'unixepoch') AS day, value, label
FROM sentiment
WHERE indicator = 'fear_greed_crypto'
  AND timestamp >= strftime('%s', 'now', '-30 days')
ORDER BY timestamp;
```

---

## 7. `etf_flows`

**Purpose:** Daily net inflows/outflows for Bitcoin spot ETFs (IBIT, FBTC, etc.) and equity ETFs (SPY, QQQ). Large inflows are a bullish signal.

**Data Sources:** ETF provider disclosures, Yahoo Finance

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Auto-increment row ID |
| `timestamp` | INTEGER | Unix seconds (business date) |
| `symbol` | TEXT | `'IBIT'`, `'FBTC'`, `'BITB'`, `'SPY'`, `'QQQ'` |
| `source` | TEXT | Data provider |
| `flow_usd` | REAL | Net flow in USD (positive = inflow, negative = outflow) |
| `aum` | REAL | Assets under management in USD |
| `metadata` | TEXT | JSON — shares, NAV |

**Unique constraint:** `(timestamp, symbol, source)`

**Index:** `(symbol, timestamp)`

**Sample queries:**

```sql
-- Total BTC ETF flows today
SELECT SUM(flow_usd) AS total_flow,
       CASE WHEN SUM(flow_usd) > 0 THEN 'NET_INFLOW' ELSE 'NET_OUTFLOW' END AS signal
FROM etf_flows
WHERE symbol IN ('IBIT', 'FBTC', 'BITB', 'HODL', 'ARKB')
  AND timestamp >= strftime('%s', 'now', 'start of day');

-- 7-day ETF flow trend
SELECT date(timestamp, 'unixepoch') AS day,
       SUM(CASE WHEN symbol IN ('IBIT','FBTC','BITB') THEN flow_usd ELSE 0 END) AS btc_etf_flow
FROM etf_flows
WHERE timestamp >= strftime('%s', 'now', '-7 days')
GROUP BY day
ORDER BY day;
```

---

## 8. `liquidations`

**Purpose:** Forced liquidations on crypto perpetual exchanges. Large liquidation cascades signal volatility and potential reversals.

**Data Sources:** Binance, Bybit (via aggregator APIs)

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Auto-increment row ID |
| `timestamp` | INTEGER | Unix seconds (UTC) |
| `symbol` | TEXT | `'BTC'`, `'ETH'`, `'SOL'` |
| `exchange` | TEXT | `'binance'`, `'bybit'` |
| `side` | TEXT | `'long'` or `'short'` |
| `amount_usd` | REAL | Liquidation value in USD |
| `price` | REAL | Execution price |

**Unique constraint:** `(timestamp, symbol, exchange, side)`

**Index:** `(symbol, timestamp)`

**Sample queries:**

```sql
-- Largest long liquidations in last 24h (potential bottom signal)
SELECT datetime(timestamp, 'unixepoch'), exchange, amount_usd, price
FROM liquidations
WHERE symbol = 'BTC' AND side = 'long'
  AND timestamp >= strftime('%s', 'now', '-1 day')
ORDER BY amount_usd DESC LIMIT 10;

-- Hourly liquidation heatmap
SELECT strftime('%H:00', timestamp, 'unixepoch') AS hour,
       SUM(CASE WHEN side='long' THEN amount_usd ELSE 0 END) AS longs_liquidated,
       SUM(CASE WHEN side='short' THEN amount_usd ELSE 0 END) AS shorts_liquidated
FROM liquidations
WHERE symbol = 'BTC'
  AND timestamp >= strftime('%s', 'now', '-1 day')
GROUP BY hour
ORDER BY hour;
```

---

## 9. `long_short_ratios`

**Purpose:** Percentage of traders positioned long vs. short on Binance perpetuals. Extreme readings are contrarian signals.

**Data Sources:** Binance futures L/S ratio API

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Auto-increment row ID |
| `timestamp` | INTEGER | Unix seconds (UTC) |
| `symbol` | TEXT | `'BTC'`, `'ETH'`, `'SOL'` |
| `exchange` | TEXT | `'binance'` |
| `long_pct` | REAL | % of accounts net long |
| `short_pct` | REAL | % of accounts net short |
| `ratio` | REAL | `long_pct / short_pct` |

**Sample queries:**

```sql
-- Current L/S ratio
SELECT datetime(timestamp, 'unixepoch'), long_pct, short_pct, ratio,
       CASE WHEN ratio > 1.5 THEN 'CROWDED_LONG'
            WHEN ratio < 0.7 THEN 'CROWDED_SHORT'
            ELSE 'NEUTRAL' END AS signal
FROM long_short_ratios
WHERE symbol = 'BTC'
ORDER BY timestamp DESC LIMIT 1;
```

---

## 10. `economic_data`

**Purpose:** Macro economic series from FRED. Used as signal inputs for the Macro Swing strategy.

**Data Sources:** Federal Reserve Economic Data (FRED) — free API key required

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Auto-increment row ID |
| `timestamp` | INTEGER | Unix seconds (release date) |
| `series_id` | TEXT | FRED series code (see list below) |
| `source` | TEXT | `'fred'` |
| `value` | REAL | Data value |

**Unique constraint:** `(timestamp, series_id, source)`

**Index:** `(series_id, timestamp)`

**Key FRED series tracked:**

| Series ID | Description | Signal Relevance |
|---|---|---|
| `DGS10` | 10-Year Treasury Yield | Risk-off signal when rising fast |
| `DFF` | Federal Funds Rate | Macro regime driver |
| `CPIAUCSL` | CPI (All Urban) | Inflation signal |
| `CPILFESL` | Core CPI | Preferred inflation gauge |
| `PCEPI` | PCE Index | Fed's preferred inflation gauge |
| `UNRATE` | Unemployment Rate | NFP companion |
| `M2SL` | M2 Money Supply | Liquidity proxy |
| `DTWEXBGS` | USD Index (broad) | Dollar strength |
| `VIXCLS` | VIX Closing Level | Fear gauge |
| `T10Y2Y` | 10Y-2Y Yield Spread | Recession indicator |

**Sample queries:**

```sql
-- Latest CPI reading
SELECT datetime(timestamp, 'unixepoch'), series_id, value
FROM economic_data
WHERE series_id = 'CPIAUCSL'
ORDER BY timestamp DESC LIMIT 1;

-- Fed Funds Rate history
SELECT date(timestamp, 'unixepoch') AS date, value AS rate
FROM economic_data
WHERE series_id = 'DFF'
ORDER BY timestamp DESC LIMIT 12;

-- All latest macro readings
SELECT series_id, value, datetime(timestamp, 'unixepoch') AS updated
FROM economic_data
WHERE (series_id, timestamp) IN (
  SELECT series_id, MAX(timestamp) FROM economic_data GROUP BY series_id
)
ORDER BY series_id;
```

---

## 11. `prediction_markets`

**Purpose:** Kalshi and Polymarket event prices. Used to gauge market-implied probabilities for macro outcomes.

**Data Sources:** Kalshi API, Polymarket

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Auto-increment row ID |
| `timestamp` | INTEGER | Unix seconds (UTC) |
| `market` | TEXT | `'kalshi'` or `'polymarket'` |
| `event_ticker` | TEXT | Contract ID (e.g., `'KXRECSSNBER-26'`) |
| `event_name` | TEXT | Human-readable event description |
| `yes_price` | REAL | Yes probability (0–1) |
| `no_price` | REAL | No probability (0–1) |
| `volume` | REAL | Trading volume |

**Unique constraint:** `(timestamp, market, event_ticker)`

**Index:** `(event_ticker, timestamp)`

**Sample queries:**

```sql
-- Recession probability from Kalshi
SELECT event_name, yes_price AS prob_yes, datetime(timestamp, 'unixepoch') AS updated
FROM prediction_markets
WHERE market = 'kalshi'
  AND event_name LIKE '%recession%'
ORDER BY timestamp DESC LIMIT 5;
```

---

## 12. `orderbook_snapshots`

**Purpose:** Level 2 orderbook snapshots showing bid/ask depth. Used for spread analysis and liquidity assessment.

**Data Sources:** Kraken, Binance

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Auto-increment row ID |
| `timestamp` | INTEGER | Unix seconds (UTC) |
| `symbol` | TEXT | Asset ticker |
| `exchange` | TEXT | `'kraken'`, `'binance'` |
| `bid_depth_json` | TEXT | JSON: `[[price, qty], ...]` |
| `ask_depth_json` | TEXT | JSON: `[[price, qty], ...]` |
| `spread_pct` | REAL | `(ask - bid) / mid * 100` |
| `mid_price` | REAL | `(best_bid + best_ask) / 2` |

**Sample queries:**

```sql
-- Current BTC spread on Kraken
SELECT datetime(timestamp, 'unixepoch'), spread_pct, mid_price
FROM orderbook_snapshots
WHERE symbol = 'BTC' AND exchange = 'kraken'
ORDER BY timestamp DESC LIMIT 1;
```

---

## 13. `vix_term_structure`

**Purpose:** VIX futures curve. Contango (future > spot) = normal; backwardation = fear/event risk.

**Data Sources:** CBOE via Yahoo Finance

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Auto-increment row ID |
| `timestamp` | INTEGER | Unix seconds (UTC) |
| `expiry` | TEXT | Contract expiry: `'YYYY-MM-DD'` |
| `vix_value` | REAL | VIX futures price |
| `days_to_expiry` | INTEGER | Calendar days to expiration |

**Unique constraint:** `(timestamp, expiry)`

**Sample queries:**

```sql
-- Current VIX term structure
SELECT expiry, vix_value, days_to_expiry
FROM vix_term_structure
WHERE timestamp = (SELECT MAX(timestamp) FROM vix_term_structure)
ORDER BY days_to_expiry;

-- Contango / backwardation signal
SELECT 
  (SELECT vix_value FROM vix_term_structure
   WHERE timestamp = (SELECT MAX(timestamp) FROM vix_term_structure)
   ORDER BY days_to_expiry LIMIT 1 OFFSET 1)
  -
  (SELECT vix_value FROM vix_term_structure
   WHERE timestamp = (SELECT MAX(timestamp) FROM vix_term_structure)
   ORDER BY days_to_expiry LIMIT 1)
  AS front_to_second_spread;
```

---

## 14. `collection_log`

**Purpose:** Health and audit log for every collector run. Use to detect failed collections or data gaps.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Auto-increment row ID |
| `timestamp` | INTEGER | Run start time (Unix seconds) |
| `collector` | TEXT | `'crypto'`, `'stocks'`, `'macro'` |
| `status` | TEXT | `'success'`, `'error'`, `'partial'` |
| `records_inserted` | INTEGER | New rows inserted this run |
| `duration_ms` | INTEGER | Run duration in milliseconds |
| `error_msg` | TEXT | Error message if status = 'error' |

**Sample queries:**

```sql
-- Last 10 collection runs with status
SELECT datetime(timestamp, 'unixepoch') AS run_time, collector, status,
       records_inserted, duration_ms, error_msg
FROM collection_log
ORDER BY timestamp DESC LIMIT 10;

-- Failed collections in last 7 days
SELECT datetime(timestamp, 'unixepoch'), collector, error_msg
FROM collection_log
WHERE status != 'success'
  AND timestamp >= strftime('%s', 'now', '-7 days')
ORDER BY timestamp DESC;

-- Average collection performance
SELECT collector, 
       COUNT(*) AS runs,
       AVG(duration_ms) AS avg_ms,
       SUM(records_inserted) AS total_records,
       SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS errors
FROM collection_log
GROUP BY collector;
```

---

## Database Health Check

```sql
-- Row counts by table
SELECT 'prices' AS tbl, COUNT(*) AS rows FROM prices UNION ALL
SELECT 'options_chain', COUNT(*) FROM options_chain UNION ALL
SELECT 'derived_metrics', COUNT(*) FROM derived_metrics UNION ALL
SELECT 'funding_rates', COUNT(*) FROM funding_rates UNION ALL
SELECT 'onchain_metrics', COUNT(*) FROM onchain_metrics UNION ALL
SELECT 'sentiment', COUNT(*) FROM sentiment UNION ALL
SELECT 'etf_flows', COUNT(*) FROM etf_flows UNION ALL
SELECT 'liquidations', COUNT(*) FROM liquidations UNION ALL
SELECT 'long_short_ratios', COUNT(*) FROM long_short_ratios UNION ALL
SELECT 'economic_data', COUNT(*) FROM economic_data UNION ALL
SELECT 'prediction_markets', COUNT(*) FROM prediction_markets UNION ALL
SELECT 'orderbook_snapshots', COUNT(*) FROM orderbook_snapshots UNION ALL
SELECT 'vix_term_structure', COUNT(*) FROM vix_term_structure UNION ALL
SELECT 'collection_log', COUNT(*) FROM collection_log;

-- Database file size
SELECT page_count * page_size / 1024 / 1024.0 AS size_mb
FROM pragma_page_count(), pragma_page_size();
```
