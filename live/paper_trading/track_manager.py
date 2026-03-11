#!/usr/bin/env python3
"""
Track Manager — Issue #35
Manages 3 parallel paper trading tracks (A: Macro Swing, B: Grid, C: Hybrid).
Stores state in state/paper_tracks.json. No external dependencies.
"""

import json
import math
import os
import sys
from datetime import datetime, timezone

# ── Config ────────────────────────────────────────────────────────────────────
STATE_DIR   = os.path.join(os.path.dirname(__file__), "state")
STATE_FILE  = os.path.join(STATE_DIR, "paper_tracks.json")
LOGS_DIR    = os.path.join(os.path.dirname(__file__), "..", "..", "logs", "paper_trades")

START_DATE  = "2026-03-11"

DEFAULT_STATE = {
    "tracks": {
        "A": {
            "name":              "Macro Swing v2",
            "start_date":        START_DATE,
            "starting_capital":  752.00,
            "current_value":     752.00,
            "allocated_capital": 376.00,
            "cash":              376.00,
            "trades":            [],
            "daily_snapshots":   [],
        },
        "B": {
            "name":             "Grid Trading",
            "start_date":       START_DATE,
            "starting_capital": 376.00,
            "current_value":    376.00,
            "trades":           [],
            "daily_snapshots":  [],
        },
        "C": {
            "name":             "Full Hybrid",
            "start_date":       START_DATE,
            "starting_capital": 752.00,
            "current_value":    752.00,
            "trades":           [],
            "daily_snapshots":  [],
        },
    }
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _r2(v: float) -> float:
    return round(v, 2)


# ── TrackManager ──────────────────────────────────────────────────────────────

class TrackManager:
    """Manages 3 parallel paper trading tracks with comparison metrics."""

    def __init__(self):
        os.makedirs(STATE_DIR, exist_ok=True)
        os.makedirs(LOGS_DIR,  exist_ok=True)
        self.state = self._load_state()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load_state(self) -> dict:
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE) as f:
                    return json.load(f)
            except Exception as e:
                print(f"[WARN] Could not load track state: {e}. Using defaults.")
        # First run — write defaults
        self._write_state(DEFAULT_STATE)
        return DEFAULT_STATE

    def _write_state(self, state: dict):
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)

    def _save(self):
        self._write_state(self.state)

    def _track(self, track_id: str) -> dict:
        track_id = track_id.upper()
        if track_id not in self.state["tracks"]:
            raise ValueError(f"Unknown track '{track_id}'. Valid: A, B, C")
        return self.state["tracks"][track_id]

    # ── Trade logging ─────────────────────────────────────────────────────────

    def log_trade(self, track_id: str, trade_data: dict):
        """
        Log a trade to a specific track.
        trade_data expected keys: side, symbol, price, qty, pnl (optional),
                                  fee, timestamp (optional), notes (optional)
        """
        track = self._track(track_id)
        trade = {
            "id":        len(track["trades"]) + 1,
            "timestamp": trade_data.get("timestamp", _now()),
            "side":      trade_data.get("side", "?"),
            "symbol":    trade_data.get("symbol", "ETHUSD"),
            "price":     _r2(float(trade_data.get("price", 0))),
            "qty":       float(trade_data.get("qty", 0)),
            "fee":       _r2(float(trade_data.get("fee", 0))),
            "pnl":       _r2(float(trade_data.get("pnl", 0))),
            "notes":     trade_data.get("notes", ""),
        }
        track["trades"].append(trade)

        # Update current_value
        track["current_value"] = _r2(
            track.get("current_value", track["starting_capital"]) + trade["pnl"]
        )
        self._save()

        # Also write to CSV log
        self._log_to_csv(track_id, trade)
        print(f"✅ Trade logged to Track {track_id}: {trade['side']} {trade['qty']} @ ${trade['price']:,.2f}  pnl=${trade['pnl']:+.2f}")

    def _log_to_csv(self, track_id: str, trade: dict):
        csv_path = os.path.join(LOGS_DIR, f"track_{track_id.lower()}_trades.csv")
        write_header = not os.path.exists(csv_path)
        with open(csv_path, "a") as f:
            if write_header:
                f.write("id,timestamp,side,symbol,price,qty,fee,pnl,notes\n")
            f.write(
                f"{trade['id']},{trade['timestamp']},{trade['side']},"
                f"{trade['symbol']},{trade['price']},{trade['qty']},"
                f"{trade['fee']},{trade['pnl']},{trade['notes']}\n"
            )

    # ── Daily snapshot ────────────────────────────────────────────────────────

    def take_daily_snapshot(self, prices: dict = None):
        """
        Capture current value of all tracks.
        prices: optional {symbol: price} dict for mark-to-market (e.g. {"ETHUSD": 2100})
        """
        today = _today()
        for tid, track in self.state["tracks"].items():
            snapshot = {
                "date":          today,
                "current_value": _r2(track.get("current_value", track["starting_capital"])),
                "starting_capital": track["starting_capital"],
                "return_pct":    _r2(
                    (track.get("current_value", track["starting_capital"]) - track["starting_capital"])
                    / track["starting_capital"] * 100
                ),
                "trade_count":   len(track.get("trades", [])),
                "timestamp":     _now(),
            }
            if prices:
                snapshot["prices"] = prices

            # Avoid duplicate for same date
            snaps = track.setdefault("daily_snapshots", [])
            existing = [s for s in snaps if s["date"] == today]
            if existing:
                # Update the existing snapshot
                idx = snaps.index(existing[-1])
                snaps[idx] = snapshot
            else:
                snaps.append(snapshot)

        self._save()
        print(f"📸 Daily snapshot taken for {today}")
        for tid, track in self.state["tracks"].items():
            val   = track.get("current_value", track["starting_capital"])
            start = track["starting_capital"]
            ret   = _r2((val - start) / start * 100)
            print(f"   Track {tid} ({track['name']}): ${val:,.2f}  ({ret:+.2f}%)")

    # ── Metrics ───────────────────────────────────────────────────────────────

    def _compute_metrics(self, track: dict) -> dict:
        trades  = track.get("trades", [])
        snaps   = track.get("daily_snapshots", [])
        start   = track["starting_capital"]
        current = track.get("current_value", start)

        total_return_pct = _r2((current - start) / start * 100)
        trade_count      = len(trades)

        # Win rate
        closed = [t for t in trades if t["pnl"] != 0]
        wins   = [t for t in closed if t["pnl"] > 0]
        win_rate = _r2(len(wins) / len(closed) * 100) if closed else 0.0

        # Best / worst trade
        best_trade  = max((t["pnl"] for t in closed), default=0.0)
        worst_trade = min((t["pnl"] for t in closed), default=0.0)

        # Max drawdown (from daily snapshots)
        max_dd = 0.0
        peak   = start
        for snap in snaps:
            val  = snap["current_value"]
            peak = max(peak, val)
            dd   = (peak - val) / peak * 100 if peak > 0 else 0
            max_dd = max(max_dd, dd)

        # Sharpe (annualised, daily returns, needs ≥2 snapshots)
        sharpe = None
        if len(snaps) >= 2:
            daily_rets = []
            for i in range(1, len(snaps)):
                prev = snaps[i - 1]["current_value"]
                curr = snaps[i]["current_value"]
                if prev > 0:
                    daily_rets.append((curr - prev) / prev)
            if len(daily_rets) >= 2:
                mean_r = sum(daily_rets) / len(daily_rets)
                var_r  = sum((r - mean_r) ** 2 for r in daily_rets) / (len(daily_rets) - 1)
                std_r  = math.sqrt(var_r) if var_r > 0 else 0
                if std_r > 0:
                    sharpe = _r2(mean_r / std_r * math.sqrt(365))

        # Capital utilisation
        allocated = track.get("allocated_capital", start)
        cap_util  = _r2(allocated / start * 100)

        return {
            "total_return_pct": total_return_pct,
            "current_value":    _r2(current),
            "starting_capital": _r2(start),
            "max_drawdown_pct": _r2(max_dd),
            "win_rate_pct":     win_rate,
            "trade_count":      trade_count,
            "closed_trades":    len(closed),
            "cap_utilisation_pct": cap_util,
            "sharpe_ratio":     sharpe,
            "best_trade_pnl":   _r2(best_trade),
            "worst_trade_pnl":  _r2(worst_trade),
        }

    # ── Public API ────────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        """Returns all tracks with current P&L, win rate, trade count."""
        result = {}
        for tid, track in self.state["tracks"].items():
            result[tid] = {
                "name":    track["name"],
                **self._compute_metrics(track),
            }
        return result

    def get_comparison(self) -> str:
        """Side-by-side A vs B vs C comparison table (Markdown)."""
        metrics = {tid: self._compute_metrics(t) for tid, t in self.state["tracks"].items()}
        names   = {tid: t["name"] for tid, t in self.state["tracks"].items()}

        rows = [
            ("Metric",             "A",  "B",  "C"),
            ("Name",
                names["A"], names["B"], names["C"]),
            ("Starting Capital",
                f"${metrics['A']['starting_capital']:,.2f}",
                f"${metrics['B']['starting_capital']:,.2f}",
                f"${metrics['C']['starting_capital']:,.2f}"),
            ("Current Value",
                f"${metrics['A']['current_value']:,.2f}",
                f"${metrics['B']['current_value']:,.2f}",
                f"${metrics['C']['current_value']:,.2f}"),
            ("Total Return %",
                f"{metrics['A']['total_return_pct']:+.2f}%",
                f"{metrics['B']['total_return_pct']:+.2f}%",
                f"{metrics['C']['total_return_pct']:+.2f}%"),
            ("Max Drawdown %",
                f"{metrics['A']['max_drawdown_pct']:.2f}%",
                f"{metrics['B']['max_drawdown_pct']:.2f}%",
                f"{metrics['C']['max_drawdown_pct']:.2f}%"),
            ("Win Rate %",
                f"{metrics['A']['win_rate_pct']:.1f}%",
                f"{metrics['B']['win_rate_pct']:.1f}%",
                f"{metrics['C']['win_rate_pct']:.1f}%"),
            ("Trade Count",
                str(metrics['A']['trade_count']),
                str(metrics['B']['trade_count']),
                str(metrics['C']['trade_count'])),
            ("Cap Utilisation",
                f"{metrics['A']['cap_utilisation_pct']:.1f}%",
                f"{metrics['B']['cap_utilisation_pct']:.1f}%",
                f"{metrics['C']['cap_utilisation_pct']:.1f}%"),
            ("Sharpe Ratio",
                str(metrics['A']['sharpe_ratio'] or "n/a"),
                str(metrics['B']['sharpe_ratio'] or "n/a"),
                str(metrics['C']['sharpe_ratio'] or "n/a")),
            ("Best Trade P&L",
                f"${metrics['A']['best_trade_pnl']:+.2f}",
                f"${metrics['B']['best_trade_pnl']:+.2f}",
                f"${metrics['C']['best_trade_pnl']:+.2f}"),
            ("Worst Trade P&L",
                f"${metrics['A']['worst_trade_pnl']:+.2f}",
                f"${metrics['B']['worst_trade_pnl']:+.2f}",
                f"${metrics['C']['worst_trade_pnl']:+.2f}"),
        ]

        # Column widths
        col_w = [max(len(str(r[i])) for r in rows) for i in range(4)]
        sep   = "| " + " | ".join("-" * w for w in col_w) + " |"

        lines = []
        for i, row in enumerate(rows):
            line = "| " + " | ".join(str(row[j]).ljust(col_w[j]) for j in range(4)) + " |"
            lines.append(line)
            if i == 0:
                lines.append(sep)
        return "\n".join(lines)

    def get_daily_brief_section(self) -> str:
        """Formatted markdown section for Pinch's daily brief."""
        status  = self.get_status()
        today   = _today()
        lines   = [
            "## 📈 Paper Trading Tracks",
            f"*As of {today}*",
            "",
        ]

        for tid in ("A", "B", "C"):
            t = status[tid]
            sharpe_str = f"  |  Sharpe: {t['sharpe_ratio']:.2f}" if t["sharpe_ratio"] else ""
            lines += [
                f"### Track {tid}: {t['name']}",
                f"- **Value:** ${t['current_value']:,.2f}  ({t['total_return_pct']:+.2f}%)",
                f"- **Trades:** {t['trade_count']}  |  **Win Rate:** {t['win_rate_pct']:.1f}%"
                f"  |  **Max DD:** {t['max_drawdown_pct']:.2f}%{sharpe_str}",
                f"- **Best:** ${t['best_trade_pnl']:+.2f}  |  **Worst:** ${t['worst_trade_pnl']:+.2f}",
                "",
            ]

        lines.append("### Comparison Table")
        lines.append(self.get_comparison())
        return "\n".join(lines)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    tm  = TrackManager()

    if cmd == "status":
        status = tm.get_status()
        print(f"{'Track':<6} {'Name':<22} {'Value':>10} {'Return':>8} {'Trades':>7} {'Win%':>6} {'MaxDD':>7}")
        print("-" * 70)
        for tid in ("A", "B", "C"):
            t = status[tid]
            print(
                f"  {tid}    {t['name']:<22} ${t['current_value']:>9,.2f} "
                f"{t['total_return_pct']:>+7.2f}% {t['trade_count']:>7}  "
                f"{t['win_rate_pct']:>5.1f}%  {t['max_drawdown_pct']:>6.2f}%"
            )

    elif cmd == "compare":
        print(tm.get_comparison())

    elif cmd == "snapshot":
        tm.take_daily_snapshot()

    elif cmd == "brief":
        print(tm.get_daily_brief_section())

    elif cmd == "log":
        # Quick CLI for logging a trade:
        # python3 track_manager.py log A buy ETHUSD 2000 0.05 1.60 5.00
        # track side symbol price qty fee pnl
        if len(sys.argv) < 9:
            print("Usage: track_manager.py log <track> <side> <symbol> <price> <qty> <fee> <pnl> [notes]")
            sys.exit(1)
        _, _, track_id, side, symbol, price, qty, fee, pnl = sys.argv[:9]
        notes = sys.argv[9] if len(sys.argv) > 9 else ""
        tm.log_trade(track_id, {
            "side": side, "symbol": symbol,
            "price": price, "qty": qty,
            "fee": fee, "pnl": pnl, "notes": notes,
        })

    else:
        print(f"Unknown command: {cmd}")
        print("Usage: python3 track_manager.py [status|compare|snapshot|brief|log]")
        sys.exit(1)


if __name__ == "__main__":
    main()
