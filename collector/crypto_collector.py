"""
crypto_collector.py — Collects ALL crypto market data for Pinch Market Data.

Sources:
  Prices      : Kraken + CoinGecko
  Options     : Deribit (BTC + ETH full chains)
  Funding     : Binance perpetual funding rates
  On-Chain    : blockchain.info + mempool.space
  Sentiment   : Alternative.me Fear & Greed
  Liquidations: TODO (no free unauthenticated public endpoint found)

Usage:
  python3 crypto_collector.py all       # collect everything
  python3 crypto_collector.py prices    # just prices
  python3 crypto_collector.py options   # just options
  python3 crypto_collector.py funding   # just funding rates
  python3 crypto_collector.py onchain   # just on-chain metrics
  python3 crypto_collector.py sentiment # just sentiment
  python3 crypto_collector.py status    # show last collection times

Rule of Acquisition #74: Knowledge equals profit.
"""

import sys
import os
import json
import time
import logging
import re

from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# ---------------------------------------------------------------------------
# Path setup — importable from anywhere
# ---------------------------------------------------------------------------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from db import MarketDB
import config

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("crypto_collector")

# ---------------------------------------------------------------------------
# HTTP configuration from config
# ---------------------------------------------------------------------------
HTTP_TIMEOUT    = getattr(config, "REQUEST_TIMEOUT", 30)
HTTP_RETRIES    = getattr(config, "MAX_RETRIES", 3)
HTTP_RETRY_DELAY = float(getattr(config, "RETRY_DELAY", 2))

# ---------------------------------------------------------------------------
# Kraken pairs — values are Kraken pair names, keys are our symbols
# ---------------------------------------------------------------------------
KRAKEN_PAIRS = config.KRAKEN_PAIRS   # dict: symbol -> kraken_pair

# Reverse map for lookup
KRAKEN_REVERSE = {v: k for k, v in KRAKEN_PAIRS.items()}

# CoinGecko IDs: dict symbol -> coingecko_id
COINGECKO_IDS = config.COINGECKO_IDS

# Binance perpetual symbols
BINANCE_PAIRS = config.BINANCE_PAIRS  # dict: symbol -> XXXUSDT

# Deribit option currencies
DERIBIT_CURRENCIES = config.CRYPTO_OPTIONS.get("deribit", ["BTC", "ETH"])

# ---------------------------------------------------------------------------
# Month abbreviation map for Deribit expiry parsing (e.g. "28MAR26")
# ---------------------------------------------------------------------------
_MONTH_MAP = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04",
    "MAY": "05", "JUN": "06", "JUL": "07", "AUG": "08",
    "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12",
}

# ---------------------------------------------------------------------------
# HTTP utility
# ---------------------------------------------------------------------------

def _fetch(url: str, headers: dict | None = None,
           retries: int = HTTP_RETRIES, delay: float = HTTP_RETRY_DELAY):
    """GET JSON from URL with exponential-backoff retry."""
    hdrs = {
        "User-Agent": "pinch-market-data/1.0",
        "Accept": "application/json",
    }
    if headers:
        hdrs.update(headers)
    req = Request(url, headers=hdrs)
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            with urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                return json.loads(resp.read())
        except HTTPError as e:
            last_exc = e
            if e.code == 429:
                wait = delay * (2 ** attempt)
                logger.warning("Rate limited %s — sleeping %.1fs", url, wait)
                time.sleep(wait)
            else:
                logger.warning("HTTP %d on %s (attempt %d/%d)", e.code, url, attempt, retries)
                time.sleep(delay)
        except (URLError, OSError) as e:
            last_exc = e
            logger.warning("Network error on %s (attempt %d/%d): %s", url, attempt, retries, e)
            time.sleep(delay)
    raise RuntimeError(f"Failed after {retries} attempts: {url}") from last_exc


def _parse_deribit_expiry(raw_expiry: str) -> str:
    """Convert Deribit expiry like '28MAR26' → '2026-03-28'."""
    m = re.match(r"(\d{1,2})([A-Z]{3})(\d{2})", raw_expiry.upper())
    if not m:
        return raw_expiry
    day, mon, yr = m.group(1), m.group(2), m.group(3)
    month_num = _MONTH_MAP.get(mon, "01")
    return f"20{yr}-{month_num}-{int(day):02d}"


def _parse_deribit_instrument(name: str) -> dict:
    """
    Parse 'BTC-28MAR26-70000-C' →
    { currency, expiry (YYYY-MM-DD), strike, option_type ('C' or 'P') }
    """
    parts = name.split("-")
    result = {
        "currency":    parts[0] if len(parts) > 0 else "",
        "expiry":      "",
        "strike":      None,
        "option_type": None,
    }
    if len(parts) >= 2:
        result["expiry"] = _parse_deribit_expiry(parts[1])
    if len(parts) >= 3:
        try:
            result["strike"] = float(parts[2])
        except ValueError:
            pass
    if len(parts) >= 4:
        result["option_type"] = "C" if parts[3].upper() == "C" else "P"
    return result


# ---------------------------------------------------------------------------
# 1. Crypto Prices  (Kraken + CoinGecko → prices table)
# ---------------------------------------------------------------------------

def collect_crypto_prices() -> int:
    """Fetch prices from Kraken + CoinGecko; store as close price rows."""
    t0 = time.time()
    rows = []
    ts = int(time.time())

    # --- Kraken ---
    try:
        kraken_pairs_str = ",".join(KRAKEN_PAIRS.values())
        url = f"{config.KRAKEN_BASE}/Ticker?pair={kraken_pairs_str}"
        print("Collecting Kraken prices...", end=" ", flush=True)
        data = _fetch(url)
        if data.get("error"):
            logger.warning("Kraken API error: %s", data["error"])
        result = data.get("result", {})
        for kraken_pair, ticker in result.items():
            symbol = KRAKEN_REVERSE.get(kraken_pair)
            if not symbol:
                # best-effort normalise
                sym = re.sub(r"(ZUSD|USD)$", "", kraken_pair)
                symbol = re.sub(r"^X(?=[A-Z]{3})", "", sym) or kraken_pair
            price = float(ticker["c"][0])
            volume = float(ticker["v"][1])   # 24h rolling volume
            rows.append({
                "timestamp":  ts,
                "symbol":     symbol,
                "asset_class": "crypto",
                "source":     "kraken",
                "timeframe":  "1d",
                "open":       float(ticker["o"]),
                "high":       float(ticker["h"][1]),
                "low":        float(ticker["l"][1]),
                "close":      price,
                "volume":     volume,
            })
        print(f"{len(result)} pairs...", end=" ", flush=True)
        time.sleep(0.5)
    except Exception as e:
        logger.error("Kraken prices failed: %s", e)

    kraken_count = len(rows)

    # --- CoinGecko ---
    try:
        ids = ",".join(COINGECKO_IDS.values())
        url = (
            f"{config.COINGECKO_BASE}/simple/price"
            f"?ids={ids}&vs_currencies=usd"
            f"&include_24hr_vol=true&include_24hr_change=true"
        )
        print("CoinGecko...", end=" ", flush=True)
        data = _fetch(url)
        # Build reverse map: coingecko_id -> symbol
        cg_reverse = {v: k for k, v in COINGECKO_IDS.items()}
        for coin_id, vals in data.items():
            symbol = cg_reverse.get(coin_id, coin_id.upper())
            rows.append({
                "timestamp":  ts,
                "symbol":     symbol,
                "asset_class": "crypto",
                "source":     "coingecko",
                "timeframe":  "1d",
                "open":       None,
                "high":       None,
                "low":        None,
                "close":      vals.get("usd"),
                "volume":     vals.get("usd_24h_vol"),
            })
        print(f"{len(data)} coins...", end=" ", flush=True)
        time.sleep(1.5)    # CoinGecko free tier: 10–30 req/min
    except Exception as e:
        logger.error("CoinGecko prices failed: %s", e)

    coingecko_count = len(rows) - kraken_count

    with MarketDB() as mdb:
        written = mdb.insert_many("prices", rows)
        elapsed_ms = int((time.time() - t0) * 1000)
        mdb.log_collection("crypto_prices", "success", written, elapsed_ms)

    elapsed = time.time() - t0
    print(f"done ({elapsed:.1f}s) — {written} rows "
          f"(kraken={kraken_count} coingecko={coingecko_count})")
    return written


# ---------------------------------------------------------------------------
# 2. Crypto Options (Deribit → options_chain + derived_metrics)
# ---------------------------------------------------------------------------

def _calc_max_pain(instruments: list[dict]) -> float | None:
    """
    For a single expiry: find the strike that minimises total dollar pain.
    Pain(S) = Σ_calls  max(0, S – K) × OI  +  Σ_puts  max(0, K – S) × OI
    """
    candidates = sorted({r["strike"] for r in instruments if r["strike"]})
    if not candidates:
        return None

    calls = [(r["strike"], r.get("open_interest") or 0)
             for r in instruments if r["option_type"] == "C" and r["strike"]]
    puts  = [(r["strike"], r.get("open_interest") or 0)
             for r in instruments if r["option_type"] == "P" and r["strike"]]

    min_pain  = float("inf")
    mp_strike = candidates[0]
    for s in candidates:
        pain = (sum(max(0, s - k) * oi for k, oi in calls) +
                sum(max(0, k - s) * oi for k, oi in puts))
        if pain < min_pain:
            min_pain  = pain
            mp_strike = s
    return mp_strike


def collect_crypto_options() -> int:
    """Fetch Deribit BTC + ETH full options chains; compute max pain, P/C ratio."""
    t0 = time.time()
    total_written = 0

    for currency in DERIBIT_CURRENCIES:
        t1 = time.time()
        try:
            url = (
                f"{config.DERIBIT_BASE}"
                f"/get_book_summary_by_currency?currency={currency}&kind=option"
            )
            print(f"Collecting Deribit {currency} options...", end=" ", flush=True)
            data = _fetch(url)
            instruments_raw = data.get("result", [])
            print(f"{len(instruments_raw)} instruments...", end=" ", flush=True)

            ts = int(time.time())
            option_rows = []
            for inst in instruments_raw:
                name   = inst.get("instrument_name", "")
                parsed = _parse_deribit_instrument(name)
                option_rows.append({
                    "timestamp":         ts,
                    "symbol":            parsed["currency"],
                    "asset_class":       "crypto",
                    "source":            "deribit",
                    "expiry":            parsed["expiry"],
                    "strike":            parsed["strike"],
                    "option_type":       parsed["option_type"],
                    "open_interest":     inst.get("open_interest"),
                    "volume":            inst.get("volume"),
                    "bid":               inst.get("bid_price"),
                    "ask":               inst.get("ask_price"),
                    "last_price":        None,
                    "mark_price":        inst.get("mark_price"),
                    "implied_volatility": inst.get("mark_iv"),
                    "delta":             None,
                    "gamma":             None,
                    "theta":             None,
                    "vega":              None,
                    "underlying_price":  inst.get("underlying_price"),
                })

            with MarketDB() as mdb:
                written = mdb.insert_many("options_chain", option_rows)

                # --- Derived metrics per expiry ---
                expiries: dict[str, list] = {}
                for r in option_rows:
                    if r["expiry"]:
                        expiries.setdefault(r["expiry"], []).append(r)

                derived_rows = []
                for expiry, insts in expiries.items():
                    calls  = [i for i in insts if i["option_type"] == "C"]
                    puts   = [i for i in insts if i["option_type"] == "P"]
                    oi_c   = sum(i.get("open_interest") or 0 for i in calls)
                    oi_p   = sum(i.get("open_interest") or 0 for i in puts)
                    vol_c  = sum(i.get("volume") or 0 for i in calls)
                    vol_p  = sum(i.get("volume") or 0 for i in puts)
                    mp     = _calc_max_pain(insts)

                    meta = {"expiry": expiry, "n_calls": len(calls),
                            "n_puts": len(puts), "oi_calls": oi_c, "oi_puts": oi_p}

                    for metric, value in [
                        ("max_pain",     mp),
                        ("pc_ratio_oi",  round(oi_p / oi_c,  4) if oi_c  else None),
                        ("pc_ratio_vol", round(vol_p / vol_c, 4) if vol_c else None),
                    ]:
                        derived_rows.append({
                            "timestamp": ts,
                            "symbol":    currency,
                            "source":    "deribit",
                            "metric":    f"{metric}_{expiry}",
                            "value":     value,
                            "metadata":  json.dumps(meta),
                        })

                mdb.insert_many("derived_metrics", derived_rows)
                elapsed_ms = int((time.time() - t1) * 1000)
                mdb.log_collection(f"crypto_options_{currency.lower()}",
                                   "success", written, elapsed_ms)

            total_written += written
            print(f"done ({(time.time()-t1):.1f}s)")
            time.sleep(1.0)   # Deribit courtesy pause

        except Exception as e:
            logger.error("Deribit %s options failed: %s", currency, e)
            with MarketDB() as mdb:
                mdb.log_collection(f"crypto_options_{currency.lower()}",
                                   "error", 0,
                                   int((time.time()-t1)*1000), str(e))

    return total_written


# ---------------------------------------------------------------------------
# 3. Funding Rates  (Binance → funding_rates table)
# ---------------------------------------------------------------------------

def collect_funding_rates() -> int:
    """
    Fetch latest perpetual funding rates.
    Primary: Binance fapi (may be geo-blocked — HTTP 451)
    Fallback: Bybit V5 public API (no auth required)
    """
    t0 = time.time()
    rows = []
    ts   = int(time.time())

    # --- Binance ---
    print("Collecting Binance funding rates...", end=" ", flush=True)
    binance_ok = 0
    for symbol, binance_pair in BINANCE_PAIRS.items():
        try:
            url = (
                f"https://fapi.binance.com/fapi/v1/fundingRate"
                f"?symbol={binance_pair}&limit=1"
            )
            data = _fetch(url, retries=1)    # 1 attempt only — fast fail
            if isinstance(data, list) and data:
                entry = data[0]
                rows.append({
                    "timestamp": ts,
                    "symbol":    symbol,
                    "exchange":  "binance",
                    "rate":      float(entry.get("fundingRate", 0)),
                })
                binance_ok += 1
            time.sleep(0.15)
        except Exception:
            pass   # silently skip — will try Bybit below

    if binance_ok == 0:
        logger.info("Binance fapi unavailable (geo-block?) — trying Bybit fallback")

    # --- OKX fallback (public API, no auth, no geo-block observed) ---
    # OKX: GET https://www.okx.com/api/v5/public/funding-rate?instId=BTC-USD-SWAP
    okx_symbol_map = {
        "BTC": "BTC-USD-SWAP", "ETH": "ETH-USD-SWAP", "SOL": "SOL-USD-SWAP",
        "XRP": "XRP-USD-SWAP", "BNB": "BNB-USD-SWAP", "DOGE": "DOGE-USD-SWAP",
        "ADA": "ADA-USD-SWAP", "AVAX": "AVAX-USD-SWAP", "DOT": "DOT-USD-SWAP",
        "LINK": "LINK-USD-SWAP",
    }
    okx_ok = 0
    for symbol, okx_inst in okx_symbol_map.items():
        if any(r["symbol"] == symbol and r["exchange"] == "binance" for r in rows):
            continue
        try:
            url  = f"https://www.okx.com/api/v5/public/funding-rate?instId={okx_inst}"
            data = _fetch(url, retries=2)
            entries = data.get("data", [])
            if entries:
                e = entries[0]
                rows.append({
                    "timestamp": ts,
                    "symbol":    symbol,
                    "exchange":  "okx",
                    "rate":      float(e.get("fundingRate", 0)),
                })
                okx_ok += 1
            time.sleep(0.15)
        except Exception as e:
            logger.warning("OKX funding rate failed for %s: %s", okx_inst, e)

    # Bybit V5 as tertiary (may be geo-blocked in some regions)
    bybit_ok = 0
    for symbol in BINANCE_PAIRS:
        if any(r["symbol"] == symbol for r in rows):
            continue
        try:
            bybit_pair = f"{symbol}USDT"
            url = (
                "https://api.bybit.com/v5/market/funding/history"
                f"?category=linear&symbol={bybit_pair}&limit=1"
            )
            data = _fetch(url, retries=1)
            entries = data.get("result", {}).get("list", [])
            if entries:
                e = entries[0]
                rows.append({
                    "timestamp": ts,
                    "symbol":    symbol,
                    "exchange":  "bybit",
                    "rate":      float(e.get("fundingRate", 0)),
                })
                bybit_ok += 1
            time.sleep(0.15)
        except Exception:
            pass

    with MarketDB() as mdb:
        written = mdb.insert_many("funding_rates", rows)
        elapsed_ms = int((time.time() - t0) * 1000)
        status = "success" if written > 0 else "partial"
        mdb.log_collection("funding_rates", status, written, elapsed_ms,
                           f"binance={binance_ok} okx={okx_ok} bybit={bybit_ok}")

    elapsed = time.time() - t0
    print(f"{written} symbols (binance={binance_ok} okx={okx_ok} bybit={bybit_ok})... done ({elapsed:.1f}s)")
    return written


# ---------------------------------------------------------------------------
# 4. On-Chain Metrics  (blockchain.info + mempool.space → onchain_metrics)
# ---------------------------------------------------------------------------

def collect_onchain() -> int:
    """Fetch Bitcoin on-chain metrics from blockchain.info and mempool.space."""
    t0 = time.time()
    rows = []
    ts = int(time.time())

    # --- blockchain.info stats ---
    try:
        print("Collecting blockchain.info stats...", end=" ", flush=True)
        data = _fetch(f"{config.BLOCKCHAIN_INFO}/stats")
        wanted = [
            "hash_rate", "n_tx", "n_blocks_mined", "minutes_between_blocks",
            "total_fees_btc", "n_btc_mined", "difficulty", "estimated_btc_sent",
            "miners_revenue_btc", "market_price_usd",
        ]
        for key in wanted:
            if key in data:
                rows.append({
                    "timestamp": ts, "symbol": "BTC",
                    "metric":    key, "source": "blockchain.info",
                    "value":     float(data[key]), "metadata": None,
                })
        print(f"{len(rows)} metrics...", end=" ", flush=True)
        time.sleep(0.5)
    except Exception as e:
        logger.error("blockchain.info stats failed: %s", e)

    # --- blockchain.info market cap ---
    try:
        data = _fetch(
            f"{config.BLOCKCHAIN_INFO}/charts/market-cap"
            f"?timespan=1days&format=json"
        )
        values = data.get("values", [])
        if values:
            latest = values[-1]
            rows.append({
                "timestamp": ts, "symbol": "BTC",
                "metric":    "market_cap_usd", "source": "blockchain.info",
                "value":     float(latest.get("y", 0)), "metadata": None,
            })
        time.sleep(0.5)
    except Exception as e:
        logger.error("blockchain.info market-cap failed: %s", e)

    # --- mempool.space fee / congestion ---
    try:
        print("mempool.space...", end=" ", flush=True)
        data = _fetch(f"{config.MEMPOOL_SPACE}/v1/fees/mempool-blocks")
        if isinstance(data, list) and data:
            block0 = data[0]
            meta   = json.dumps({"block_index": 0,
                                  "n_tx": block0.get("nTx"),
                                  "block_size": block0.get("blockSize")})
            for metric, key in [
                ("mempool_median_fee_sat_vb", "medianFee"),
                ("mempool_block_total_fees_sat", "totalFees"),
                ("mempool_block_size_bytes",    "blockSize"),
            ]:
                val = block0.get(key)
                if val is not None:
                    rows.append({
                        "timestamp": ts, "symbol": "BTC",
                        "metric":    metric, "source": "mempool.space",
                        "value":     float(val), "metadata": meta,
                    })
        time.sleep(0.3)
    except Exception as e:
        logger.error("mempool.space failed: %s", e)

    with MarketDB() as mdb:
        written = mdb.insert_many("onchain_metrics", rows)
        elapsed_ms = int((time.time() - t0) * 1000)
        mdb.log_collection("onchain", "success", written, elapsed_ms)

    elapsed = time.time() - t0
    print(f"done ({elapsed:.1f}s) — {written} rows")
    return written


# ---------------------------------------------------------------------------
# 5. Sentiment  (Alternative.me → sentiment table)
# ---------------------------------------------------------------------------

def collect_sentiment() -> int:
    """Fetch Crypto Fear & Greed index from alternative.me."""
    t0 = time.time()
    rows = []
    ts = int(time.time())

    try:
        print("Collecting Fear & Greed index...", end=" ", flush=True)
        data = _fetch(f"{config.ALTERNATIVE_ME}?limit=1")
        entries = data.get("data", [])
        for entry in entries:
            rows.append({
                "timestamp": ts,
                "indicator": "fear_greed_crypto",
                "source":    "alternative.me",
                "value":     float(entry.get("value", 0)),
                "label":     entry.get("value_classification"),
                "metadata":  json.dumps(entry),
            })
        time.sleep(0.3)
    except Exception as e:
        logger.error("Fear & Greed failed: %s", e)
        with MarketDB() as mdb:
            mdb.log_collection("sentiment", "error", 0,
                               int((time.time()-t0)*1000), str(e))
        return 0

    with MarketDB() as mdb:
        written = mdb.insert_many("sentiment", rows)
        elapsed_ms = int((time.time() - t0) * 1000)
        mdb.log_collection("sentiment", "success", written, elapsed_ms)

    elapsed = time.time() - t0
    if rows:
        print(f"{rows[0].get('value')} ({rows[0].get('label')})... "
              f"done ({elapsed:.1f}s)")
    return written


# ---------------------------------------------------------------------------
# 6. Liquidations — TODO
# ---------------------------------------------------------------------------

def collect_liquidations() -> int:
    """
    TODO: Liquidation data — no free unauthenticated public endpoint found.
    - CoinGlass requires API key ($)
    - Coinalyze requires authentication
    - Bybit/OKX/Binance websocket streams require auth or are rate-limited
    Implement once an API key is available.
    """
    logger.info("Liquidations: TODO — no free public endpoint available")
    return 0


# ---------------------------------------------------------------------------
# Aggregate collector
# ---------------------------------------------------------------------------

def collect_all_crypto() -> dict:
    """Run all crypto collectors and return dict of {collector: rows_written}."""
    t0 = time.time()
    print("=" * 60)
    print("  💰 Crypto Data Collection — START")
    print("=" * 60)

    results = {
        "prices":    collect_crypto_prices(),
        "options":   collect_crypto_options(),
        "funding":   collect_funding_rates(),
        "onchain":   collect_onchain(),
        "sentiment": collect_sentiment(),
    }

    total   = sum(results.values())
    elapsed = time.time() - t0
    print("=" * 60)
    print(f"  Done in {elapsed:.1f}s — {total} total rows written")
    print(f"  {results}")
    print("=" * 60)

    with MarketDB() as mdb:
        mdb.log_collection("collect_all_crypto", "success", total,
                           int(elapsed * 1000), json.dumps(results))
    return results


# ---------------------------------------------------------------------------
# Status report
# ---------------------------------------------------------------------------

def show_status():
    """Print last collection times for all crypto collectors."""
    collectors = [
        "crypto_prices", "crypto_options_btc", "crypto_options_eth",
        "funding_rates", "onchain", "sentiment", "collect_all_crypto",
    ]
    print(f"\n{'Collector':<30} {'Last Run':<22} {'Status':<10} "
          f"{'Rows':>6}  {'Duration':>8}")
    print("-" * 84)
    with MarketDB() as mdb:
        for name in collectors:
            rows = mdb.query(
                "SELECT * FROM collection_log WHERE collector=? "
                "ORDER BY timestamp DESC LIMIT 1",
                [name]
            )
            if rows:
                r = rows[0]
                ts_str = time.strftime("%Y-%m-%d %H:%M:%S",
                                       time.localtime(r["timestamp"]))
                dur = f"{r['duration_ms']/1000:.2f}s" if r["duration_ms"] else "—"
                print(f"{name:<30} {ts_str:<22} {r['status']:<10} "
                      f"{r['records_inserted'] or 0:>6}  {dur:>8}")
            else:
                print(f"{name:<30} {'— never —':<22}")

        # Quick DB row counts
        print("\n  DB row counts:")
        for table in ["prices", "options_chain", "derived_metrics",
                      "funding_rates", "onchain_metrics", "sentiment"]:
            try:
                n = mdb.query(f"SELECT COUNT(*) as n FROM {table}")[0]["n"]
                print(f"    {table:<25} {n:>8} rows")
            except Exception:
                pass
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else "help"
    dispatch = {
        "all":       collect_all_crypto,
        "prices":    collect_crypto_prices,
        "options":   collect_crypto_options,
        "funding":   collect_funding_rates,
        "onchain":   collect_onchain,
        "sentiment": collect_sentiment,
        "status":    show_status,
    }
    fn = dispatch.get(cmd)
    if fn:
        fn()
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
