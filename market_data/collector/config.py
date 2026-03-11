# Pinch Market Data — Central Configuration
# Rule of Acquisition #34: War is good for business.
# Rule of Acquisition #35: Peace is good for business.
# Either way, data is good for profit.

# Crypto symbols to track
CRYPTO_SYMBOLS = ['BTC', 'ETH', 'SOL', 'XRP', 'BNB', 'DOGE', 'ADA', 'AVAX', 'DOT', 'LINK']

# Crypto options (only available on certain exchanges)
CRYPTO_OPTIONS = {
    'deribit': ['BTC', 'ETH'],
    'binance': ['BTC', 'ETH', 'BNB', 'SOL', 'XRP', 'DOGE'],
}

# Stock symbols to track
STOCK_SYMBOLS = [
    'SPY', 'QQQ', 'IWM', 'AAPL', 'NVDA', 'MSFT', 'GOOG', 'AMZN', 'TSLA',
    'AMD', 'PLTR', 'ANET', 'META', 'AVGO', 'BRK-B', 'CSCO', 'WFC', 'ORCL',
    'GLD', 'TLT', 'XLE', 'MSTR'
]

# Stock options to track (subset - most liquid)
STOCK_OPTIONS = [
    'SPY', 'QQQ', 'IWM', 'AAPL', 'NVDA', 'MSFT', 'GOOG', 'AMZN', 'TSLA',
    'AMD', 'PLTR', 'META'
]

# FRED economic series
FRED_SERIES = {
    'DGS2':               '2-Year Treasury',
    'DGS5':               '5-Year Treasury',
    'DGS10':              '10-Year Treasury',
    'DGS30':              '30-Year Treasury',
    'T10Y2Y':             '10Y-2Y Spread',
    'DTWEXBGS':           'Dollar Index',
    'VIXCLS':             'VIX',
    'UNRATE':             'Unemployment Rate',
    'CPIAUCSL':           'CPI',
    'PCEPI':              'PCE Price Index',
    'FEDFUNDS':           'Fed Funds Rate',
    'M2SL':               'M2 Money Supply',
    'GDPC1':              'Real GDP',
    'ICSA':               'Initial Claims',
    'UMCSENT':            'Consumer Sentiment',
    'DCOILWTICO':         'WTI Crude Oil',
    'DCOILBRENTEU':       'Brent Crude',
    'GOLDPMGBD228NLBM':   'Gold Price',
    'DHHNGSP':            'Natural Gas',
    'BAMLH0A0HYM2':       'High Yield Spread',
    'TEDRATE':            'TED Spread',
}

# API endpoints
DERIBIT_BASE     = 'https://www.deribit.com/api/v2/public'
KRAKEN_BASE      = 'https://api.kraken.com/0/public'
BINANCE_BASE     = 'https://api.binance.com/api/v3'
FRED_BASE        = 'https://api.stlouisfed.org/fred/series/observations'
ALTERNATIVE_ME   = 'https://api.alternative.me/fng/'
COINGECKO_BASE   = 'https://api.coingecko.com/api/v3'
BLOCKCHAIN_INFO  = 'https://api.blockchain.info'
MEMPOOL_SPACE    = 'https://mempool.space/api'

# Kraken symbol map: our symbol -> Kraken pair
KRAKEN_PAIRS = {
    'BTC':  'XXBTZUSD',
    'ETH':  'XETHZUSD',
    'SOL':  'SOLUSD',
    'XRP':  'XXRPZUSD',
    'BNB':  'BNBUSD',
    'DOGE': 'XDGUSD',
    'ADA':  'ADAUSD',
    'AVAX': 'AVAXUSD',
    'DOT':  'DOTUSD',
    'LINK': 'LINKUSD',
}

# Binance symbol map: our symbol -> Binance pair
BINANCE_PAIRS = {
    'BTC':  'BTCUSDT',
    'ETH':  'ETHUSDT',
    'SOL':  'SOLUSDT',
    'XRP':  'XRPUSDT',
    'BNB':  'BNBUSDT',
    'DOGE': 'DOGEUSDT',
    'ADA':  'ADAUSDT',
    'AVAX': 'AVAXUSDT',
    'DOT':  'DOTUSDT',
    'LINK': 'LINKUSDT',
}

# CoinGecko IDs for on-chain data
COINGECKO_IDS = {
    'BTC':  'bitcoin',
    'ETH':  'ethereum',
    'SOL':  'solana',
    'XRP':  'ripple',
    'BNB':  'binancecoin',
    'DOGE': 'dogecoin',
    'ADA':  'cardano',
    'AVAX': 'avalanche-2',
    'DOT':  'polkadot',
    'LINK': 'chainlink',
}

# Retry configuration
MAX_RETRIES    = 3
RETRY_DELAY    = 2   # seconds between retries
REQUEST_TIMEOUT = 30  # seconds

# Data paths
DATA_ROOT = '/mnt/media/market_data'
DB_PATH   = f'{DATA_ROOT}/pinch_market.db'
SCHEMA_PATH = f'{DATA_ROOT}/schema.sql'
BACKUP_DIR  = f'{DATA_ROOT}/backups'
RAW_DIR     = f'{DATA_ROOT}/raw'
