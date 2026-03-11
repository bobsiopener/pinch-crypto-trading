-- Pinch Market Data Schema
-- SQLite schema for comprehensive market data collection
-- Rule of Acquisition #74: Knowledge equals profit.

-- Core price data
CREATE TABLE IF NOT EXISTS prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,          -- unix seconds
    symbol TEXT NOT NULL,                 -- 'BTC', 'AAPL', 'SPY'
    asset_class TEXT NOT NULL,            -- 'crypto', 'stock', 'etf', 'index', 'commodity', 'fx'
    source TEXT NOT NULL,                 -- 'kraken', 'yahoo', 'binance', 'fred'
    timeframe TEXT NOT NULL DEFAULT '1d', -- '1m', '5m', '1h', '1d'
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL,
    UNIQUE(timestamp, symbol, source, timeframe)
);
CREATE INDEX IF NOT EXISTS idx_prices_symbol_ts ON prices(symbol, timestamp);
CREATE INDEX IF NOT EXISTS idx_prices_class ON prices(asset_class, timestamp);

-- Options chains (crypto + stocks)
CREATE TABLE IF NOT EXISTS options_chain (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    symbol TEXT NOT NULL,                 -- underlying
    asset_class TEXT NOT NULL,
    source TEXT NOT NULL,
    expiry TEXT NOT NULL,                 -- 'YYYY-MM-DD'
    strike REAL NOT NULL,
    option_type TEXT NOT NULL,            -- 'C' or 'P'
    open_interest REAL,
    volume REAL,
    bid REAL,
    ask REAL,
    last_price REAL,
    mark_price REAL,
    implied_volatility REAL,
    delta REAL,
    gamma REAL,
    theta REAL,
    vega REAL,
    underlying_price REAL,
    UNIQUE(timestamp, symbol, source, expiry, strike, option_type)
);
CREATE INDEX IF NOT EXISTS idx_options_symbol_ts ON options_chain(symbol, timestamp);
CREATE INDEX IF NOT EXISTS idx_options_expiry ON options_chain(symbol, expiry, strike);

-- Derived metrics (max pain, P/C ratio, IV rank, etc)
CREATE TABLE IF NOT EXISTS derived_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    source TEXT NOT NULL,
    metric TEXT NOT NULL,                 -- 'max_pain', 'pc_ratio_oi', 'pc_ratio_vol', 'iv_rank', 'iv_percentile'
    value REAL,
    metadata TEXT,                        -- JSON blob
    UNIQUE(timestamp, symbol, source, metric)
);
CREATE INDEX IF NOT EXISTS idx_derived_symbol_metric ON derived_metrics(symbol, metric, timestamp);

-- Funding rates (crypto perpetuals)
CREATE TABLE IF NOT EXISTS funding_rates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    rate REAL NOT NULL,
    UNIQUE(timestamp, symbol, exchange)
);
CREATE INDEX IF NOT EXISTS idx_funding_symbol ON funding_rates(symbol, timestamp);

-- On-chain metrics
CREATE TABLE IF NOT EXISTS onchain_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    symbol TEXT NOT NULL,                 -- 'BTC', 'ETH'
    metric TEXT NOT NULL,                 -- 'mvrv', 'exchange_reserve', 'active_addresses', 'hash_rate', etc
    source TEXT NOT NULL,
    value REAL,
    metadata TEXT,
    UNIQUE(timestamp, symbol, metric, source)
);
CREATE INDEX IF NOT EXISTS idx_onchain_symbol_metric ON onchain_metrics(symbol, metric, timestamp);

-- Sentiment indicators
CREATE TABLE IF NOT EXISTS sentiment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    indicator TEXT NOT NULL,              -- 'fear_greed_crypto', 'fear_greed_stocks', 'google_trends_btc', 'reddit_wsb'
    source TEXT NOT NULL,
    value REAL,
    label TEXT,                           -- 'Fear', 'Greed', etc
    metadata TEXT,
    UNIQUE(timestamp, indicator, source)
);
CREATE INDEX IF NOT EXISTS idx_sentiment_indicator ON sentiment(indicator, timestamp);

-- ETF and fund flows
CREATE TABLE IF NOT EXISTS etf_flows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    symbol TEXT NOT NULL,                 -- 'IBIT', 'FBTC', 'SPY', 'QQQ'
    source TEXT NOT NULL,
    flow_usd REAL,                       -- positive = inflow, negative = outflow
    aum REAL,                            -- assets under management
    metadata TEXT,
    UNIQUE(timestamp, symbol, source)
);
CREATE INDEX IF NOT EXISTS idx_flows_symbol ON etf_flows(symbol, timestamp);

-- Liquidation data
CREATE TABLE IF NOT EXISTS liquidations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    side TEXT NOT NULL,                   -- 'long' or 'short'
    amount_usd REAL,
    price REAL,
    UNIQUE(timestamp, symbol, exchange, side)
);
CREATE INDEX IF NOT EXISTS idx_liq_symbol ON liquidations(symbol, timestamp);

-- Long/short ratios
CREATE TABLE IF NOT EXISTS long_short_ratios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    long_pct REAL,
    short_pct REAL,
    ratio REAL,
    UNIQUE(timestamp, symbol, exchange)
);

-- Economic data (FRED)
CREATE TABLE IF NOT EXISTS economic_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    series_id TEXT NOT NULL,              -- FRED series: 'DGS10', 'UNRATE', 'CPIAUCSL'
    source TEXT NOT NULL DEFAULT 'fred',
    value REAL,
    UNIQUE(timestamp, series_id, source)
);
CREATE INDEX IF NOT EXISTS idx_econ_series ON economic_data(series_id, timestamp);

-- Prediction markets
CREATE TABLE IF NOT EXISTS prediction_markets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    market TEXT NOT NULL,                 -- 'kalshi', 'polymarket'
    event_ticker TEXT NOT NULL,           -- 'KXRECSSNBER-26'
    event_name TEXT,
    yes_price REAL,
    no_price REAL,
    volume REAL,
    UNIQUE(timestamp, market, event_ticker)
);
CREATE INDEX IF NOT EXISTS idx_pred_event ON prediction_markets(event_ticker, timestamp);

-- Orderbook snapshots (top N levels)
CREATE TABLE IF NOT EXISTS orderbook_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    bid_depth_json TEXT,                  -- JSON: [[price, qty], ...]
    ask_depth_json TEXT,
    spread_pct REAL,
    mid_price REAL,
    UNIQUE(timestamp, symbol, exchange)
);

-- VIX term structure
CREATE TABLE IF NOT EXISTS vix_term_structure (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    expiry TEXT NOT NULL,
    vix_value REAL,
    days_to_expiry INTEGER,
    UNIQUE(timestamp, expiry)
);

-- Collection metadata / health
CREATE TABLE IF NOT EXISTS collection_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    collector TEXT NOT NULL,
    status TEXT NOT NULL,                 -- 'success', 'error', 'partial'
    records_inserted INTEGER,
    duration_ms INTEGER,
    error_msg TEXT
);
