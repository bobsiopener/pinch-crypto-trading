#!/usr/bin/env python3
"""
Pinch Daily Monitoring Dashboard
Rule of Acquisition #22: A wise man can hear profit in the wind.

Usage:
  python3 dashboard.py           — full dashboard
  python3 dashboard.py --brief   — compact 5-line summary
  python3 dashboard.py --json    — machine-readable JSON
  python3 dashboard.py --discord — Discord markdown format
"""

import sys
import os
import json
import csv
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

# ── Paths ────────────────────────────────────────────────────────────────────
BASE = "/home/bob/AI_sandbox/pinch-crypto-trading"
SECRETS_DIR = "/home/bob/.openclaw/workspace-pinch/.secrets"

PAPER_TRACKS    = f"{BASE}/live/paper_trading/state/paper_tracks.json"
GRID_STATE      = f"{BASE}/live/paper_trading/state/grid_paper_state.json"
RISK_STATE      = f"{BASE}/live/config/risk_state.json"
MACRO_CAL       = f"{BASE}/live/monitor/macro_calendar.json"
MONITOR_STATE   = f"{BASE}/state/monitor_state.json"
PAPER_TRADES    = f"{BASE}/logs/trades/paper_trades.csv"
DAILY_PNL       = f"{BASE}/logs/trades/daily_pnl.csv"


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}

def now_et():
    """Return current time in US/Eastern (UTC-5 standard, UTC-4 DST — approximate)."""
    utc_now = datetime.now(timezone.utc)
    # Rough ET offset; good enough for dashboard purposes
    et_offset = timedelta(hours=-4)  # EDT (Mar–Nov)
    return utc_now + et_offset

def fmt_usd(val):
    try:
        return f"${float(val):,.2f}"
    except Exception:
        return str(val)

def fmt_pct(val):
    try:
        v = float(val)
        sign = "+" if v >= 0 else ""
        return f"{sign}{v:.2f}%"
    except Exception:
        return str(val)

def importance_icon(level):
    return {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(level, "⚪")

def days_countdown(event_date_str):
    try:
        ev = datetime.strptime(event_date_str, "%Y-%m-%d").date()
        today = now_et().date()
        delta = (ev - today).days
        if delta == 0:
            return "TODAY"
        elif delta == 1:
            return "tomorrow"
        elif delta < 0:
            return f"{-delta}d ago"
        else:
            return f"in {delta}d"
    except Exception:
        return "?"


# ── Section 1: Market Overview ────────────────────────────────────────────────

def fetch_market():
    result = {"btc_last": None, "btc_open": None, "eth_last": None, "eth_open": None, "error": None}
    try:
        url = "https://api.kraken.com/0/public/Ticker?pair=XBTUSD,ETHUSD"
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
        r = data.get("result", {})
        btc = r.get("XXBTZUSD", {})
        eth = r.get("XETHZUSD", {})
        result["btc_last"] = float(btc["c"][0]) if btc else None
        result["btc_open"] = float(btc["o"]) if btc else None
        result["eth_last"] = float(eth["c"][0]) if eth else None
        result["eth_open"] = float(eth["o"]) if eth else None
    except Exception as e:
        result["error"] = str(e)
    return result


def market_change(last, open_):
    if last is None or open_ is None or open_ == 0:
        return None
    return (last - open_) / open_ * 100


# ── Section 2: Account Status ─────────────────────────────────────────────────

def fetch_account():
    result = {"status": "unknown", "balances": {}, "total_usd": None, "error": None}
    try:
        sys.path.insert(0, SECRETS_DIR)
        import kraken_trader as kt
        summary = kt.get_balance_summary()
        result["balances"] = summary
        total = sum(v.get("usd_value", 0) for v in summary.values() if isinstance(v, dict))
        result["total_usd"] = total
        result["status"] = "ok"
    except Exception as e:
        result["status"] = "manual"
        result["error"] = str(e)
    return result


# ── Section 3: Paper Trading Tracks ──────────────────────────────────────────

def load_tracks():
    data = load_json(PAPER_TRACKS, {})
    tracks = data.get("tracks", {})
    out = {}
    for name, t in tracks.items():
        start_val = t.get("starting_capital", 0)
        cur_val   = t.get("current_value", start_val)
        ret_pct   = (cur_val - start_val) / start_val * 100 if start_val else 0
        trades    = t.get("trades", [])
        wins      = sum(1 for tr in trades if tr.get("pnl_usd", 0) > 0)
        win_rate  = wins / len(trades) * 100 if trades else None
        out[name] = {
            "label":      t.get("name", name),
            "start":      start_val,
            "value":      cur_val,
            "return_pct": ret_pct,
            "num_trades": len(trades),
            "win_rate":   win_rate,
        }
    return out


def load_grid():
    data = load_json(GRID_STATE, {})
    fills = [f for f in data.get("fill_history", [])]
    buy_open  = sum(1 for v in data.get("buy_orders", {}).values()  if v.get("status") == "open")
    sell_open = sum(1 for v in data.get("sell_orders", {}).values() if v.get("status") == "open")
    return {
        "pair":         data.get("pair", "?"),
        "center":       data.get("center_price"),
        "realized_pnl": data.get("realized_pnl", 0),
        "inventory":    data.get("inventory", 0),
        "cash":         data.get("cash", 0),
        "fills":        len(fills),
        "buy_open":     buy_open,
        "sell_open":    sell_open,
        "capital":      data.get("capital", 0),
    }


# ── Section 4: Risk Status ────────────────────────────────────────────────────

def load_risk():
    data = load_json(RISK_STATE, {})
    return {
        "hwm":              data.get("high_water_mark"),
        "consecutive_loss": data.get("consecutive_losses", 0),
        "circuit_breaker":  data.get("circuit_breaker_status", "UNKNOWN"),
        "kill_switch":      data.get("kill_switch_armed", False),
        "last_trade":       data.get("last_trade_date"),
    }


# ── Section 5: Open Signals ───────────────────────────────────────────────────

def load_open_trades(btc_price=None, eth_price=None):
    """Load open trades (no exit_date) from paper_trades.csv"""
    open_trades = []
    prices = {"BTC/USD": btc_price, "ETH/USD": eth_price, "BTCUSD": btc_price, "ETHUSD": eth_price}
    try:
        with open(PAPER_TRADES, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if not row.get("exit_date", "").strip():
                    pair  = row.get("pair", "")
                    side  = row.get("side", "")
                    entry = float(row.get("entry_price", 0) or 0)
                    size  = float(row.get("size", 0) or 0)
                    stop  = float(row.get("stop_loss", 0) or 0)
                    cur_price = prices.get(pair)
                    upnl = None
                    stop_dist = None
                    if cur_price and entry:
                        if side.upper() == "LONG":
                            upnl = (cur_price - entry) * size
                            stop_dist = (entry - stop) / entry * 100 if stop else None
                        else:
                            upnl = (entry - cur_price) * size
                            stop_dist = (stop - entry) / entry * 100 if stop else None
                    open_trades.append({
                        "trade_id":   row.get("trade_id", ""),
                        "entry_date": row.get("entry_date", ""),
                        "pair":       pair,
                        "side":       side,
                        "entry":      entry,
                        "size":       size,
                        "stop":       stop,
                        "cur_price":  cur_price,
                        "upnl":       upnl,
                        "stop_dist":  stop_dist,
                    })
    except Exception:
        pass
    return open_trades


# ── Section 6: Macro Calendar ─────────────────────────────────────────────────

def load_macro_next7():
    data = load_json(MACRO_CAL, {})
    events = data.get("events", [])
    today = now_et().date()
    cutoff = today + timedelta(days=7)
    upcoming = []
    for ev in events:
        try:
            ev_date = datetime.strptime(ev["date"], "%Y-%m-%d").date()
            if today <= ev_date <= cutoff:
                upcoming.append({
                    "date":       ev["date"],
                    "time":       ev.get("time", "?"),
                    "event":      ev.get("event", ""),
                    "importance": ev.get("importance", "low"),
                    "countdown":  days_countdown(ev["date"]),
                })
        except Exception:
            pass
    upcoming.sort(key=lambda x: (x["date"], x["time"]))
    return upcoming


# ── Section 7: Monitor Health ─────────────────────────────────────────────────

def load_monitor():
    data = load_json(MONITOR_STATE, {})
    start_ts = data.get("start_ts")
    last_hb  = data.get("last_heartbeat")
    now_ts   = datetime.now(timezone.utc).timestamp()
    uptime_s = None
    if start_ts:
        uptime_s = int(now_ts - start_ts)
    last_btc = data.get("last_btc")
    last_eth = data.get("last_eth")
    stale    = True
    if last_hb:
        stale = (now_ts - last_hb) > 300  # >5 min = stale
    return {
        "uptime_s":  uptime_s,
        "last_btc":  last_btc,
        "last_eth":  last_eth,
        "stale":     stale,
        "last_save": data.get("last_save_ts"),
    }

def fmt_uptime(seconds):
    if seconds is None:
        return "unknown"
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m {s}s"


# ── Section 8: Performance Summary ───────────────────────────────────────────

def load_performance():
    """Read closed trades and compute P&L summaries."""
    trades = []
    try:
        with open(PAPER_TRADES, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("exit_date", "").strip():
                    try:
                        trades.append({
                            "exit_date": row["exit_date"],
                            "pnl":       float(row.get("pnl_usd", 0) or 0),
                            "pair":      row.get("pair", ""),
                            "side":      row.get("side", ""),
                        })
                    except Exception:
                        pass
    except Exception:
        pass

    if not trades:
        return {"no_data": True}

    today = now_et().date()
    week_start  = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    daily_pnl   = sum(t["pnl"] for t in trades if t["exit_date"][:10] == str(today))
    weekly_pnl  = sum(t["pnl"] for t in trades if t["exit_date"][:10] >= str(week_start))
    monthly_pnl = sum(t["pnl"] for t in trades if t["exit_date"][:10] >= str(month_start))

    best  = max(trades, key=lambda x: x["pnl"])
    worst = min(trades, key=lambda x: x["pnl"])

    # Sharpe (simple, annualised from daily returns bucketed by exit_date)
    daily_buckets = {}
    for t in trades:
        d = t["exit_date"][:10]
        daily_buckets[d] = daily_buckets.get(d, 0) + t["pnl"]
    sharpe = None
    if len(daily_buckets) >= 5:
        vals = list(daily_buckets.values())
        mean_ = sum(vals) / len(vals)
        var_  = sum((v - mean_) ** 2 for v in vals) / len(vals)
        std_  = var_ ** 0.5
        sharpe = (mean_ / std_ * (252 ** 0.5)) if std_ > 0 else None

    return {
        "no_data":    False,
        "total":      len(trades),
        "daily_pnl":  daily_pnl,
        "weekly_pnl": weekly_pnl,
        "monthly_pnl":monthly_pnl,
        "best":       best,
        "worst":      worst,
        "sharpe":     sharpe,
    }


# ── Collect all data ──────────────────────────────────────────────────────────

def collect_all():
    mkt     = fetch_market()
    acct    = fetch_account()
    tracks  = load_tracks()
    grid    = load_grid()
    risk    = load_risk()
    open_tr = load_open_trades(mkt.get("btc_last"), mkt.get("eth_last"))
    macro   = load_macro_next7()
    monitor = load_monitor()
    perf    = load_performance()

    btc_chg = market_change(mkt.get("btc_last"), mkt.get("btc_open"))
    eth_chg = market_change(mkt.get("eth_last"), mkt.get("eth_open"))

    return {
        "generated_at": now_et().strftime("%Y-%m-%d %H:%M ET"),
        "market": {**mkt, "btc_chg": btc_chg, "eth_chg": eth_chg},
        "account": acct,
        "tracks": tracks,
        "grid": grid,
        "risk": risk,
        "open_trades": open_tr,
        "macro": macro,
        "monitor": monitor,
        "performance": perf,
    }


# ── Renderers ─────────────────────────────────────────────────────────────────

def render_full(d):
    lines = []
    W = 65

    def box_top(title=""):
        if title:
            pad = W - len(title) - 4
            return f"╔══ {title} {'═' * pad}╗"
        return "╔" + "═" * (W - 2) + "╗"

    def box_mid():
        return "╠" + "═" * (W - 2) + "╣"

    def box_bot():
        return "╚" + "═" * (W - 2) + "╝"

    def row(text):
        text = str(text)
        pad = W - 4 - len(text)
        if pad < 0:
            text = text[:W - 7] + "..."
            pad = 0
        return f"║  {text}{' ' * pad}  ║"

    def blank():
        return row("")

    ts = d["generated_at"]
    lines.append(box_top(f"💰 PINCH DASHBOARD  {ts}"))

    # ── Market ──────────────────────────────────────────────────────────────
    m = d["market"]
    lines.append(box_mid())
    lines.append(row("📈  MARKET OVERVIEW"))
    lines.append(blank())
    if m.get("error"):
        lines.append(row(f"  ⚠ Fetch error: {m['error'][:45]}"))
    else:
        btc = m.get("btc_last")
        eth = m.get("eth_last")
        bc  = m.get("btc_chg")
        ec  = m.get("eth_chg")
        btc_s = fmt_usd(btc) if btc else "—"
        eth_s = fmt_usd(eth) if eth else "—"
        bc_s  = fmt_pct(bc)  if bc  is not None else "—"
        ec_s  = fmt_pct(ec)  if ec  is not None else "—"
        b_arrow = "▲" if (bc or 0) >= 0 else "▼"
        e_arrow = "▲" if (ec or 0) >= 0 else "▼"
        lines.append(row(f"  BTC/USD  {btc_s:<14}  {b_arrow} {bc_s} (24h)"))
        lines.append(row(f"  ETH/USD  {eth_s:<14}  {e_arrow} {ec_s} (24h)"))
        if btc and eth:
            ratio = btc / eth
            lines.append(row(f"  BTC/ETH ratio:  {ratio:.2f}  (higher = BTC dominant)"))

    # ── Account ─────────────────────────────────────────────────────────────
    lines.append(box_mid())
    lines.append(row("🏦  ACCOUNT STATUS"))
    lines.append(blank())
    acct = d["account"]
    if acct["status"] == "ok":
        lines.append(row(f"  Total Value: {fmt_usd(acct['total_usd'])}"))
        for asset, info in (acct.get("balances") or {}).items():
            if isinstance(info, dict):
                amt = info.get("amount", 0)
                uv  = info.get("usd_value", 0)
                if uv > 0.01:
                    lines.append(row(f"    {asset:<8} {amt:>14.6f}  ≈ {fmt_usd(uv)}"))
    else:
        lines.append(row("  Kraken: check manually"))
        if acct.get("error"):
            lines.append(row(f"  ({acct['error'][:50]})"))

    # ── Paper Tracks ─────────────────────────────────────────────────────────
    lines.append(box_mid())
    lines.append(row("📊  PAPER TRADING TRACKS"))
    lines.append(blank())
    for k, t in sorted(d["tracks"].items()):
        wr  = f"{t['win_rate']:.0f}%" if t["win_rate"] is not None else "—"
        ret = fmt_pct(t["return_pct"])
        val = fmt_usd(t["value"])
        lines.append(row(f"  Track {k} [{t['label']}]"))
        lines.append(row(f"    Value: {val:<12}  Return: {ret:<10}  Trades: {t['num_trades']}  WR: {wr}"))

    g = d["grid"]
    lines.append(blank())
    lines.append(row(f"  Grid ({g['pair']})  Center: {fmt_usd(g['center'])}"))
    lines.append(row(f"    Buys open: {g['buy_open']}  Sells open: {g['sell_open']}  Fills: {g['fills']}"))
    lines.append(row(f"    Realized P&L: {fmt_usd(g['realized_pnl'])}  Inventory: {g['inventory']} units"))

    # ── Risk ──────────────────────────────────────────────────────────────────
    lines.append(box_mid())
    lines.append(row("🛡️  RISK STATUS"))
    lines.append(blank())
    r = d["risk"]
    cb = r["circuit_breaker"]
    cb_icon = "✅" if cb == "OK" else "🔴"
    ks_icon = "🔫" if r["kill_switch"] else "  "
    lines.append(row(f"  Circuit Breaker: {cb_icon} {cb}    Kill Switch: {ks_icon}"))
    lines.append(row(f"  HWM: {fmt_usd(r['hwm'])}    Consecutive Losses: {r['consecutive_loss']}"))
    last_t = r.get("last_trade") or "none"
    lines.append(row(f"  Last Trade: {last_t}"))

    # ── Open Signals ──────────────────────────────────────────────────────────
    lines.append(box_mid())
    lines.append(row("🎯  OPEN SIGNALS"))
    lines.append(blank())
    ot = d["open_trades"]
    if not ot:
        lines.append(row("  No open paper trades."))
    else:
        hdr = f"  {'Pair':<10} {'Side':<5} {'Entry':>10} {'Current':>10} {'uPnL':>9} {'SL%':>7}"
        lines.append(row(hdr))
        for t in ot:
            upnl_s  = fmt_usd(t["upnl"]) if t["upnl"] is not None else "—"
            sl_s    = fmt_pct(t["stop_dist"]) if t["stop_dist"] is not None else "—"
            cur_s   = fmt_usd(t["cur_price"]) if t["cur_price"] else "—"
            entry_s = fmt_usd(t["entry"])
            line = f"  {t['pair']:<10} {t['side']:<5} {entry_s:>10} {cur_s:>10} {upnl_s:>9} {sl_s:>7}"
            lines.append(row(line))

    # ── Macro Calendar ────────────────────────────────────────────────────────
    lines.append(box_mid())
    lines.append(row("📅  MACRO CALENDAR (next 7 days)"))
    lines.append(blank())
    mc = d["macro"]
    if not mc:
        lines.append(row("  No events in next 7 days."))
    else:
        for ev in mc:
            icon = importance_icon(ev["importance"])
            lines.append(row(f"  {icon} {ev['date']} {ev['time']} ET  {ev['event']:<30}  [{ev['countdown']}]"))

    # ── Monitor Health ────────────────────────────────────────────────────────
    lines.append(box_mid())
    lines.append(row("💓  MONITOR HEALTH"))
    lines.append(blank())
    mn = d["monitor"]
    status_icon = "🔴 STALE" if mn["stale"] else "🟢 LIVE"
    lines.append(row(f"  Status: {status_icon}    Uptime: {fmt_uptime(mn['uptime_s'])}"))
    last_btc = fmt_usd(mn.get("last_btc")) if mn.get("last_btc") else "—"
    last_eth = fmt_usd(mn.get("last_eth")) if mn.get("last_eth") else "—"
    lines.append(row(f"  Last BTC: {last_btc}    Last ETH: {last_eth}"))

    # ── Performance ───────────────────────────────────────────────────────────
    lines.append(box_mid())
    lines.append(row("📉  PERFORMANCE SUMMARY"))
    lines.append(blank())
    p = d["performance"]
    if p.get("no_data"):
        lines.append(row("  Insufficient data — no closed trades yet."))
    else:
        lines.append(row(f"  Daily P&L:  {fmt_usd(p['daily_pnl'])}"))
        lines.append(row(f"  Weekly P&L: {fmt_usd(p['weekly_pnl'])}"))
        lines.append(row(f"  Monthly P&L:{fmt_usd(p['monthly_pnl'])}"))
        if p.get("best"):
            b = p["best"]
            lines.append(row(f"  Best trade:  {b['pair']} {b['side']} → {fmt_usd(b['pnl'])}"))
        if p.get("worst"):
            w = p["worst"]
            lines.append(row(f"  Worst trade: {w['pair']} {w['side']} → {fmt_usd(w['pnl'])}"))
        if p.get("sharpe") is not None:
            lines.append(row(f"  Sharpe (est): {p['sharpe']:.2f}  (annualised, {p['total']} trades)"))

    lines.append(box_bot())
    lines.append(f'  Rule #22: A wise man can hear profit in the wind. 💰')
    return "\n".join(lines)


def render_brief(d):
    m   = d["market"]
    r   = d["risk"]
    mn  = d["monitor"]
    p   = d["performance"]
    ot  = d["open_trades"]

    btc_s = fmt_usd(m.get("btc_last")) if m.get("btc_last") else "—"
    eth_s = fmt_usd(m.get("eth_last")) if m.get("eth_last") else "—"
    bc_s  = fmt_pct(m.get("btc_chg"))  if m.get("btc_chg") is not None else ""
    ec_s  = fmt_pct(m.get("eth_chg"))  if m.get("eth_chg") is not None else ""
    cb    = r["circuit_breaker"]
    st    = "🟢 LIVE" if not mn["stale"] else "🔴 STALE"
    daily = fmt_usd(p.get("daily_pnl", 0)) if not p.get("no_data") else "—"

    lines = [
        f"💰 PINCH BRIEF  {d['generated_at']}",
        f"  BTC {btc_s} ({bc_s})  |  ETH {eth_s} ({ec_s})",
        f"  Risk: {cb}  |  Open trades: {len(ot)}  |  Monitor: {st}",
        f"  Daily P&L: {daily}  |  Uptime: {fmt_uptime(mn['uptime_s'])}",
        f"  Next event: " + (
            f"{d['macro'][0]['date']} {d['macro'][0]['event']}" if d["macro"] else "none in 7 days"
        ),
    ]
    return "\n".join(lines)


def render_discord(d):
    ts = d["generated_at"]
    m  = d["market"]
    r  = d["risk"]
    mn = d["monitor"]
    p  = d["performance"]
    ot = d["open_trades"]
    mc = d["macro"]

    btc_s = fmt_usd(m.get("btc_last")) if m.get("btc_last") else "—"
    eth_s = fmt_usd(m.get("eth_last")) if m.get("eth_last") else "—"
    bc_s  = fmt_pct(m.get("btc_chg"))  if m.get("btc_chg") is not None else "—"
    ec_s  = fmt_pct(m.get("eth_chg"))  if m.get("eth_chg") is not None else "—"
    b_arrow = "▲" if (m.get("btc_chg") or 0) >= 0 else "▼"
    e_arrow = "▲" if (m.get("eth_chg") or 0) >= 0 else "▼"

    acct = d["account"]
    acct_s = fmt_usd(acct.get("total_usd")) if acct.get("status") == "ok" else "check manually"

    cb = r["circuit_breaker"]
    cb_icon = "✅" if cb == "OK" else "🚨"
    st_icon = "🟢" if not mn["stale"] else "🔴"

    lines = [
        f"## 💰 Pinch Daily Brief — {ts}",
        "",
        "### 📈 Market",
        f"- **BTC** {btc_s}  {b_arrow} {bc_s}",
        f"- **ETH** {eth_s}  {e_arrow} {ec_s}",
        "",
        "### 🏦 Account",
        f"- Total: **{acct_s}**",
        "",
        "### 📊 Paper Tracks",
    ]
    for k, t in sorted(d["tracks"].items()):
        ret = fmt_pct(t["return_pct"])
        val = fmt_usd(t["value"])
        wr  = f"{t['win_rate']:.0f}%" if t["win_rate"] is not None else "—"
        lines.append(f"- **Track {k}** ({t['label']}): {val}  {ret}  trades: {t['num_trades']}  WR: {wr}")

    g = d["grid"]
    lines.extend([
        f"- **Grid** ({g['pair']}): center {fmt_usd(g['center'])}  fills: {g['fills']}  pnl: {fmt_usd(g['realized_pnl'])}",
        "",
        "### 🛡️ Risk",
        f"- Circuit Breaker: {cb_icon} {cb}  |  Consecutive losses: {r['consecutive_loss']}  |  Monitor: {st_icon}",
        "",
    ])

    if ot:
        lines.append("### 🎯 Open Signals")
        for t in ot:
            upnl_s = fmt_usd(t["upnl"]) if t["upnl"] is not None else "—"
            lines.append(f"- **{t['pair']}** {t['side']}  entry {fmt_usd(t['entry'])}  uPnL: {upnl_s}")
        lines.append("")

    if mc:
        lines.append("### 📅 Upcoming Events (7d)")
        for ev in mc[:5]:
            icon = importance_icon(ev["importance"])
            lines.append(f"- {icon} **{ev['date']} {ev['time']} ET** — {ev['event']}  _{ev['countdown']}_")
        lines.append("")

    if not p.get("no_data"):
        lines.extend([
            "### 📉 Performance",
            f"- Daily P&L: {fmt_usd(p['daily_pnl'])}  |  Weekly: {fmt_usd(p['weekly_pnl'])}  |  Monthly: {fmt_usd(p['monthly_pnl'])}",
        ])
        if p.get("sharpe") is not None:
            lines.append(f"- Sharpe (est): {p['sharpe']:.2f}")
        lines.append("")

    lines.append("> *Rule of Acquisition #22: A wise man can hear profit in the wind.* 💰")
    return "\n".join(lines)


def render_json(d):
    return json.dumps(d, indent=2, default=str)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    mode = "full"
    if "--brief" in sys.argv:
        mode = "brief"
    elif "--json" in sys.argv:
        mode = "json"
    elif "--discord" in sys.argv:
        mode = "discord"

    d = collect_all()

    if mode == "brief":
        print(render_brief(d))
    elif mode == "json":
        print(render_json(d))
    elif mode == "discord":
        print(render_discord(d))
    else:
        print(render_full(d))


if __name__ == "__main__":
    main()
