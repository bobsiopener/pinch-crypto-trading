#!/usr/bin/env python3
"""
Pinch Crypto Market Monitor
============================
Continuous daemon monitoring BTC/ETH prices, macro events, grid fills,
and sending Discord alerts via openclaw CLI.

Usage:
  python3 market_monitor.py run          — start the daemon loop
  python3 market_monitor.py status       — show current state
  python3 market_monitor.py test-alert   — send a test Discord message
  python3 market_monitor.py add-event "2026-03-25" "08:30" "CPI March" "high"
"""

import csv
import json
import logging
import logging.handlers
import os
import signal
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# ─────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────
BASE_DIR   = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
STATE_DIR  = os.path.join(BASE_DIR, "state")
LOG_DIR    = os.path.join(BASE_DIR, "logs", "monitor")
PRICE_HIST = os.path.join(STATE_DIR, "price_history.json")
GRID_STATE = os.path.join(STATE_DIR, "grid_paper_state.json")
MON_STATE  = os.path.join(STATE_DIR, "monitor_state.json")
SIGNAL_LOG = os.path.join(LOG_DIR,   "signal_log.csv")
MON_LOG    = os.path.join(LOG_DIR,   "monitor.log")

for d in (STATE_DIR, LOG_DIR):
    os.makedirs(d, exist_ok=True)

# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────
logger = logging.getLogger("market_monitor")
logger.setLevel(logging.DEBUG)
_fh = logging.handlers.TimedRotatingFileHandler(
    MON_LOG, when="midnight", backupCount=7
)
_fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
_ch = logging.StreamHandler()
_ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(_fh)
logger.addHandler(_ch)

# ─────────────────────────────────────────────
# Timezone
# ─────────────────────────────────────────────
ET = ZoneInfo("America/New_York")

def now_et() -> datetime:
    return datetime.now(tz=ET)

def ts_et(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M ET")

# ─────────────────────────────────────────────
# Macro Calendar — loaded from external JSON file
# ─────────────────────────────────────────────
CALENDAR_FILE = os.path.join(os.path.dirname(__file__), "macro_calendar.json")

def _load_calendar_file() -> list:
    """Load events from macro_calendar.json. Falls back to empty list."""
    try:
        with open(CALENDAR_FILE, "r") as f:
            data = json.load(f)
        events = data.get("events", [])
        logger.info(f"Loaded {len(events)} events from {CALENDAR_FILE}")
        return events
    except FileNotFoundError:
        logger.warning(f"Calendar file not found: {CALENDAR_FILE} — no scheduled events")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"Calendar file JSON error: {e} — no scheduled events")
        return []

MACRO_CALENDAR = _load_calendar_file()

# ─────────────────────────────────────────────
# Alert thresholds
# ─────────────────────────────────────────────
BTC_ALERT_1H  = 3.0   # %
BTC_ALERT_4H  = 5.0   # %
ETH_ALERT_1H  = 4.0   # %
ETH_ALERT_4H  = 7.0   # %
HEARTBEAT_H   = 4     # hours between heartbeats
DISCORD_TARGET = "1476110474377429124"
DISCORD_ACCT   = "pinch"
PAPER_TRADER_DIR = os.path.join(BASE_DIR, "live", "paper_trading")
PAPER_TRADER_CMD = ["python3", "grid_paper_trader.py", "check"]

# ─────────────────────────────────────────────
# Graceful shutdown
# ─────────────────────────────────────────────
_running = True

def _sighandler(signum, frame):
    global _running
    logger.info("Received signal %s — shutting down gracefully.", signum)
    _running = False

signal.signal(signal.SIGINT,  _sighandler)
signal.signal(signal.SIGTERM, _sighandler)

# ─────────────────────────────────────────────
# Discord / agent helpers
# ─────────────────────────────────────────────
def send_discord(message: str) -> bool:
    """Send a message to the Discord investments channel via openclaw CLI."""
    cmd = [
        "openclaw", "message", "send",
        "--channel", "discord",
        "--account", DISCORD_ACCT,
        "--target", DISCORD_TARGET,
        "-m", message,
    ]
    logger.debug("DISCORD → %s", message[:120])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            logger.error("openclaw send failed: %s", result.stderr.strip())
            return False
        return True
    except Exception as exc:
        logger.error("Failed to send Discord message: %s", exc)
        return False


def trigger_agent(message: str) -> bool:
    """Trigger the Pinch agent for a trade decision."""
    cmd = [
        "openclaw", "agent",
        "--agent", "pinch",
        "--channel", "discord",
        "-m", message,
        "--deliver",
    ]
    logger.info("AGENT TRIGGER → %s", message[:120])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            logger.error("openclaw agent trigger failed: %s", result.stderr.strip())
            return False
        return True
    except Exception as exc:
        logger.error("Failed to trigger agent: %s", exc)
        return False

# ─────────────────────────────────────────────
# Kraken price fetch
# ─────────────────────────────────────────────
KRAKEN_URL = "https://api.kraken.com/0/public/Ticker?pair=XBTUSD,ETHUSD"

def fetch_prices(retries: int = 3) -> dict | None:
    """Fetch BTC and ETH prices from Kraken. Returns {'btc': float, 'eth': float} or None."""
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                KRAKEN_URL,
                headers={"User-Agent": "PinchMonitor/1.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            if data.get("error"):
                raise ValueError(f"Kraken error: {data['error']}")
            result = data["result"]
            btc = float(result["XXBTZUSD"]["c"][0])
            eth = float(result["XETHZUSD"]["c"][0])
            return {"btc": btc, "eth": eth}
        except Exception as exc:
            logger.warning("Kraken fetch attempt %d/%d failed: %s", attempt, retries, exc)
            if attempt < retries:
                time.sleep(5)
    send_discord("⚠️ API ERROR: Kraken price fetch failed after 3 retries. Monitor continuing.")
    return None

# ─────────────────────────────────────────────
# Price history (rolling 24h)
# ─────────────────────────────────────────────
def load_price_history() -> list:
    if os.path.exists(PRICE_HIST):
        try:
            with open(PRICE_HIST) as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_price_history(history: list):
    cutoff = time.time() - 86400  # 24h
    history = [h for h in history if h["ts"] >= cutoff]
    with open(PRICE_HIST, "w") as f:
        json.dump(history, f)


def price_pct_change(history: list, symbol: str, seconds: int) -> float | None:
    """Return % change for symbol over the last `seconds`. None if insufficient data."""
    now_ts = time.time()
    cutoff  = now_ts - seconds
    past = [h for h in history if h["ts"] <= cutoff]
    if not past:
        return None
    oldest = min(past, key=lambda x: abs(x["ts"] - cutoff))
    current = next((h[symbol] for h in reversed(history) if h.get(symbol)), None)
    if current is None or oldest.get(symbol) is None:
        return None
    return (current - oldest[symbol]) / oldest[symbol] * 100


def check_prices(history: list, state: dict) -> list:
    """Fetch current prices, append to history, check alert thresholds. Returns updated history."""
    prices = fetch_prices()
    if prices is None:
        return history

    now_ts = time.time()
    entry = {"ts": now_ts, "btc": prices["btc"], "eth": prices["eth"]}
    history.append(entry)
    save_price_history(history)

    state["last_btc"] = prices["btc"]
    state["last_eth"] = prices["eth"]

    # Check BTC
    for window_sec, threshold, label in [
        (3600, BTC_ALERT_1H, "1h"),
        (14400, BTC_ALERT_4H, "4h"),
    ]:
        pct = price_pct_change(history, "btc", window_sec)
        if pct is not None and abs(pct) >= threshold:
            direction = "🔺" if pct > 0 else "🔻"
            key = f"btc_alert_{label}"
            last_alert_ts = state.get(key, 0)
            # Don't re-alert within the same window
            if now_ts - last_alert_ts > window_sec * 0.5:
                msg = (
                    f"{direction} PRICE ALERT: BTC moved {pct:+.1f}% in {label} "
                    f"(now ${prices['btc']:,.0f})"
                )
                send_discord(msg)
                state[key] = now_ts
                logger.info(msg)

    # Check ETH
    for window_sec, threshold, label in [
        (3600, ETH_ALERT_1H, "1h"),
        (14400, ETH_ALERT_4H, "4h"),
    ]:
        pct = price_pct_change(history, "eth", window_sec)
        if pct is not None and abs(pct) >= threshold:
            direction = "🔺" if pct > 0 else "🔻"
            key = f"eth_alert_{label}"
            last_alert_ts = state.get(key, 0)
            if now_ts - last_alert_ts > window_sec * 0.5:
                msg = (
                    f"{direction} PRICE ALERT: ETH moved {pct:+.1f}% in {label} "
                    f"(now ${prices['eth']:,.2f})"
                )
                send_discord(msg)
                state[key] = now_ts
                logger.info(msg)

    return history

# ─────────────────────────────────────────────
# Grid monitor
# ─────────────────────────────────────────────
def check_grid(state: dict):
    """Check if current ETH price hits any grid levels and trigger paper trader."""
    if not os.path.exists(GRID_STATE):
        return

    try:
        with open(GRID_STATE) as f:
            grid = json.load(f)
    except Exception as exc:
        logger.error("Failed to read grid state: %s", exc)
        return

    eth_price = state.get("last_eth")
    if eth_price is None:
        return

    # Build unified levels list from buy_orders/sell_orders dicts
    levels = []
    for price_str, order in grid.get("buy_orders", {}).items():
        levels.append({
            "id": f"buy_{price_str}",
            "type": "buy",
            "price": float(order.get("price", price_str)),
            "qty": float(order.get("qty", 0)),
            "status": order.get("status", "open"),
        })
    for price_str, order in grid.get("sell_orders", {}).items():
        levels.append({
            "id": f"sell_{price_str}",
            "type": "sell",
            "price": float(order.get("price", price_str)),
            "qty": float(order.get("qty", 0)),
            "status": order.get("status", "open"),
        })
    # Also support legacy "levels" array format
    if not levels and "levels" in grid:
        levels = grid["levels"]

    filled_ids = set(state.get("grid_filled_ids", []))

    for lvl in levels:
        lvl_id    = str(lvl.get("id", ""))
        lvl_type  = lvl.get("type", "").lower()
        lvl_price = float(lvl.get("price", 0))
        lvl_qty   = float(lvl.get("qty", 0))
        status    = lvl.get("status", "open")

        if status != "open":
            continue
        if lvl_id in filled_ids:
            continue

        hit = False
        if lvl_type == "buy"  and eth_price <= lvl_price:
            hit = True
        elif lvl_type == "sell" and eth_price >= lvl_price:
            hit = True

        if hit:
            logger.info("Grid level hit: %s @ $%s (ETH=%.2f)", lvl_type, lvl_price, eth_price)
            # Trigger paper trader
            try:
                result = subprocess.run(
                    PAPER_TRADER_CMD,
                    cwd=PAPER_TRADER_DIR,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                pnl_line = ""
                for line in result.stdout.splitlines():
                    if "P&L" in line or "pnl" in line.lower():
                        pnl_line = line.strip()
                        break
                pnl_str = pnl_line if pnl_line else "P&L: calculating..."
            except Exception as exc:
                logger.error("Paper trader call failed: %s", exc)
                pnl_str = "P&L: error"

            emoji = "🟢" if lvl_type == "buy" else "🔴"
            msg = (
                f"{emoji} GRID FILL: ETH {lvl_type} filled at ${lvl_price:,.0f} "
                f"(qty: {lvl_qty:.3f}). Grid {pnl_str}"
            )
            send_discord(msg)
            filled_ids.add(lvl_id)
            state.setdefault("grid_fills_today", 0)
            state["grid_fills_today"] += 1

    state["grid_filled_ids"] = list(filled_ids)

# ─────────────────────────────────────────────
# Macro calendar helpers
# ─────────────────────────────────────────────
def load_calendar(state: dict) -> list:
    """Return calendar from macro_calendar.json (reloaded each cycle for hot updates)."""
    global MACRO_CALENDAR
    MACRO_CALENDAR = _load_calendar_file()
    return MACRO_CALENDAR


def parse_event_dt(event: dict) -> datetime:
    dt_str = f"{event['date']} {event['time']}"
    naive  = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
    return naive.replace(tzinfo=ET)


def next_event_summary(calendar: list) -> str:
    now = now_et()
    future = [(e, parse_event_dt(e)) for e in calendar if parse_event_dt(e) > now]
    if not future:
        return "No upcoming events"
    future.sort(key=lambda x: x[1])
    evt, dt = future[0]
    delta = dt - now
    hours  = int(delta.total_seconds() // 3600)
    mins   = int((delta.total_seconds() % 3600) // 60)
    if hours > 0:
        time_str = f"in {hours}h {mins}m"
    else:
        time_str = f"in {mins}m"
    return f"{evt['event']} {time_str}"


def check_calendar(state: dict, calendar: list):
    """Send pre-event alerts and schedule post-event signal evaluation."""
    now = now_et()
    now_ts = time.time()
    alerted = state.setdefault("calendar_alerted", {})   # key → set of alert types

    for evt in calendar:
        evt_dt  = parse_event_dt(evt)
        if evt_dt < now - timedelta(minutes=60):
            continue  # past event, skip

        key = f"{evt['date']}_{evt['time']}_{evt['event']}"
        evt_alerted = alerted.setdefault(key, [])
        delta_min = (evt_dt - now).total_seconds() / 60

        # 30-minute alert
        if 28 <= delta_min <= 32 and "30m" not in evt_alerted:
            evt_time_fmt = evt_dt.strftime("%-I:%M %p ET")
            msg = f"⏰ MACRO ALERT: {evt['event']} release in 30 minutes ({evt_time_fmt})"
            send_discord(msg)
            evt_alerted.append("30m")
            logger.info(msg)

        # 5-minute alert
        elif 3 <= delta_min <= 7 and "5m" not in evt_alerted:
            evt_time_fmt = evt_dt.strftime("%-I:%M %p ET")
            msg = f"🔴 MACRO ALERT: {evt['event']} release in 5 minutes! Monitoring for signal."
            send_discord(msg)
            evt_alerted.append("5m")
            logger.info(msg)

        # On-event alert (within 2 min after)
        elif -2 <= delta_min <= 2 and "on_event" not in evt_alerted:
            # Capture price at event time
            state[f"price_at_{key}"] = {
                "btc": state.get("last_btc"),
                "eth": state.get("last_eth"),
                "ts": now_ts,
            }
            msg = f"📊 {evt['event'].upper()} IS OUT: Monitoring price impact for 15 minutes..."
            send_discord(msg)
            evt_alerted.append("on_event")
            # Schedule post-event evaluation at +15 min
            state[f"post_eval_{key}"] = now_ts + 900
            logger.info(msg)

        # Post-event signal evaluation (15 min after)
        post_eval_ts = state.get(f"post_eval_{key}", 0)
        if post_eval_ts and now_ts >= post_eval_ts and "post_eval" not in evt_alerted:
            evaluate_signal(evt, key, state)
            evt_alerted.append("post_eval")

    state["calendar_alerted"] = alerted

# ─────────────────────────────────────────────
# Signal evaluator
# ─────────────────────────────────────────────
def evaluate_signal(evt: dict, key: str, state: dict):
    """Score price movement 15 min post-event and alert."""
    snap = state.get(f"price_at_{key}", {})
    btc_at_event = snap.get("btc")
    eth_at_event = snap.get("eth")
    btc_now = state.get("last_btc")
    eth_now = state.get("last_eth")

    btc_move = None
    eth_move = None
    if btc_at_event and btc_now:
        btc_move = (btc_now - btc_at_event) / btc_at_event * 100
    if eth_at_event and eth_now:
        eth_move = (eth_now - eth_at_event) / eth_at_event * 100

    # Simple scoring framework
    score = 0
    direction = "NEUTRAL"
    reasoning = []

    if btc_move is not None:
        if btc_move >= 1.5:
            score += 2; direction = "LONG"; reasoning.append(f"BTC +{btc_move:.1f}%")
        elif btc_move >= 0.5:
            score += 1; direction = "LONG"; reasoning.append(f"BTC +{btc_move:.1f}%")
        elif btc_move <= -1.5:
            score -= 2; direction = "SHORT"; reasoning.append(f"BTC {btc_move:.1f}%")
        elif btc_move <= -0.5:
            score -= 1; direction = "SHORT"; reasoning.append(f"BTC {btc_move:.1f}%")

    if eth_move is not None:
        if eth_move >= 2.0:
            score += 1; reasoning.append(f"ETH +{eth_move:.1f}%")
        elif eth_move <= -2.0:
            score -= 1; reasoning.append(f"ETH {eth_move:.1f}%")

    importance_bonus = {"critical": 1, "high": 0, "medium": 0}.get(evt.get("importance", "medium"), 0)
    if score != 0:
        score += importance_bonus if score > 0 else -importance_bonus

    # Format post-event message
    btc_str = f"BTC moved {btc_move:+.1f}% in 15 min" if btc_move is not None else "BTC: no data"
    send_discord(f"📊 POST-{evt['event'].upper()}: {btc_str}. Evaluating signal...")

    abs_score = abs(score)
    if abs_score >= 2:
        direction_str = "LONG" if score > 0 else "SHORT"
        asset = "BTC"
        reason_str = " + ".join(reasoning) if reasoning else evt["event"]
        msg = (
            f"🎯 TRADE SIGNAL: {direction_str} {asset}, score {score:+d} "
            f"({reason_str}). Awaiting candlestick confirmation."
        )
        send_discord(msg)
        logger.info(msg)
        # Wake up Pinch
        agent_msg = (
            f"TRADE SIGNAL DETECTED: {direction_str} {asset} after {evt['event']}, "
            f"score {score:+d} ({reason_str}). BTC=${btc_now:,.0f} ETH=${eth_now:,.2f}. "
            f"Evaluate and execute paper trade."
        )
        trigger_agent(agent_msg)
    else:
        msg = (
            f"📊 NO SIGNAL: {evt['event']} inline, score {score:+d}. No trade."
        )
        send_discord(msg)
        logger.info(msg)

    # Log to CSV
    _log_signal(evt, btc_move, eth_move, score, direction)


def _log_signal(evt: dict, btc_move, eth_move, score: int, direction: str):
    file_exists = os.path.exists(SIGNAL_LOG)
    with open(SIGNAL_LOG, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp_et", "event", "importance",
                             "btc_move_pct", "eth_move_pct", "score", "direction"])
        writer.writerow([
            now_et().strftime("%Y-%m-%d %H:%M"),
            evt["event"],
            evt.get("importance", ""),
            f"{btc_move:.2f}" if btc_move is not None else "",
            f"{eth_move:.2f}" if eth_move is not None else "",
            score,
            direction,
        ])

# ─────────────────────────────────────────────
# Heartbeat
# ─────────────────────────────────────────────
def check_heartbeat(state: dict, history: list, calendar: list):
    now_ts   = time.time()
    last_hb  = state.get("last_heartbeat", 0)
    if now_ts - last_hb < HEARTBEAT_H * 3600:
        return

    btc = state.get("last_btc")
    eth = state.get("last_eth")
    if btc is None or eth is None:
        return

    btc_4h = price_pct_change(history, "btc", 14400)
    eth_4h = price_pct_change(history, "eth", 14400)
    btc_4h_str = f"{btc_4h:+.1f}% 4h" if btc_4h is not None else "4h: --"
    eth_4h_str = f"{eth_4h:+.1f}% 4h" if eth_4h is not None else "4h: --"
    fills = state.get("grid_fills_today", 0)
    next_evt = next_event_summary(calendar)

    msg = (
        f"💓 Monitor heartbeat: "
        f"BTC ${btc:,.0f} ({btc_4h_str}) | "
        f"ETH ${eth:,.2f} ({eth_4h_str}) | "
        f"Grid: {fills} fills | "
        f"Next event: {next_evt}"
    )
    send_discord(msg)
    logger.info(msg)
    state["last_heartbeat"] = now_ts

# ─────────────────────────────────────────────
# State persistence
# ─────────────────────────────────────────────
def load_state() -> dict:
    if os.path.exists(MON_STATE):
        try:
            with open(MON_STATE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"start_ts": time.time()}


def save_state(state: dict):
    state["last_save_ts"] = time.time()
    with open(MON_STATE, "w") as f:
        json.dump(state, f, indent=2)

# ─────────────────────────────────────────────
# CLI commands
# ─────────────────────────────────────────────
def cmd_status():
    state = load_state()
    history = load_price_history()
    btc = state.get("last_btc")
    eth = state.get("last_eth")
    start_ts = state.get("start_ts", time.time())
    uptime_h = (time.time() - start_ts) / 3600

    print("=" * 50)
    print("  Pinch Market Monitor — Status")
    print("=" * 50)
    print(f"  Uptime:   {uptime_h:.1f} hours")
    print(f"  BTC:      ${btc:,.0f}" if btc else "  BTC:      --")
    print(f"  ETH:      ${eth:,.2f}" if eth else "  ETH:      --")
    print(f"  History:  {len(history)} price points")
    print(f"  Fills:    {state.get('grid_fills_today', 0)} today")
    print(f"  Last save:{state.get('last_save_ts', 0)}")
    print("=" * 50)


def cmd_test_alert():
    now_str = now_et().strftime("%Y-%m-%d %H:%M ET")
    msg = f"🧪 TEST ALERT: Pinch Market Monitor is alive at {now_str}. Rule #22: A wise man can hear profit in the wind."
    ok = send_discord(msg)
    print("✅ Alert sent." if ok else "❌ Alert failed.")


def cmd_add_event(date: str, time_str: str, event_name: str, importance: str):
    """Add an event to macro_calendar.json (persistent, not in state)."""
    try:
        with open(CALENDAR_FILE, "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {"events": []}

    new_event = {
        "date": date,
        "time": time_str,
        "event": event_name,
        "importance": importance,
    }
    data["events"].append(new_event)

    # Sort by date+time
    data["events"].sort(key=lambda e: f"{e['date']} {e['time']}")

    with open(CALENDAR_FILE, "w") as f:
        json.dump(data, f, indent=2)

    # Reload global calendar
    global MACRO_CALENDAR
    MACRO_CALENDAR = data["events"]

    print(f"✅ Added event: {event_name} on {date} at {time_str} ({importance})")
    print(f"   Calendar now has {len(MACRO_CALENDAR)} events")


def cmd_run():
    """Main daemon loop."""
    logger.info("=" * 60)
    logger.info("Pinch Market Monitor starting. WorkDir=%s", BASE_DIR)
    logger.info("=" * 60)

    state   = load_state()
    state["start_ts"] = state.get("start_ts", time.time())
    history = load_price_history()

    send_discord(
        f"🚀 Pinch Market Monitor STARTED at {ts_et(now_et())}. "
        f"Monitoring BTC, ETH, grid, and macro calendar. "
        f"Rule #22: A wise man can hear profit in the wind."
    )

    global _running
    while _running:
        try:
            calendar = load_calendar(state)

            # 1. Prices
            history = check_prices(history, state)

            # 2. Grid
            check_grid(state)

            # 3. Macro calendar
            check_calendar(state, calendar)

            # 4. Heartbeat
            check_heartbeat(state, history, calendar)

            # Persist state
            save_state(state)

        except Exception as exc:
            logger.exception("Unexpected error in main loop: %s", exc)
            send_discord(f"⚠️ MONITOR ERROR: {type(exc).__name__}: {exc}. Continuing...")

        # Sleep 60 seconds (interruptible)
        for _ in range(60):
            if not _running:
                break
            time.sleep(1)

    save_state(state)
    logger.info("Market monitor stopped cleanly.")
    send_discord(f"🛑 Pinch Market Monitor STOPPED at {ts_et(now_et())}.")

# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────
if __name__ == "__main__":
    args = sys.argv[1:]

    if not args or args[0] == "run":
        cmd_run()

    elif args[0] == "status":
        cmd_status()

    elif args[0] == "test-alert":
        cmd_test_alert()

    elif args[0] == "add-event":
        if len(args) < 5:
            print("Usage: market_monitor.py add-event <date> <time> <event-name> <importance>")
            print("  e.g: market_monitor.py add-event 2026-03-25 08:30 'CPI March' high")
            sys.exit(1)
        cmd_add_event(args[1], args[2], args[3], args[4])

    elif args[0] in ("list-events", "events", "calendar"):
        events = _load_calendar_file()
        now = now_et()
        print(f"\n📅 Macro Calendar — {len(events)} events loaded\n")
        print(f"{'Date':12} {'Time':6} {'Importance':10} {'Event'}")
        print("-" * 60)
        for e in events:
            dt = parse_event_dt(e)
            marker = " ← NEXT" if dt > now and not any(
                parse_event_dt(x) > now and parse_event_dt(x) < dt for x in events
            ) else ""
            past = " (past)" if dt < now else ""
            print(f"{e['date']:12} {e['time']:6} {e['importance']:10} {e['event']}{past}{marker}")
        print()

    else:
        print(__doc__)
        sys.exit(1)
