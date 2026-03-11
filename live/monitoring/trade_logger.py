#!/usr/bin/env python3
"""
trade_logger.py — Trade logging and tax tracking for Pinch crypto trading.

Storage:
  logs/trades/trade_log.csv   — live trades (entry + exit)
  logs/trades/paper_trades.csv — paper trades separately
  logs/trades/daily_pnl.csv   — daily P&L snapshots

Usage:
  python3 trade_logger.py summary       # print daily summary
  python3 trade_logger.py history       # print recent trades (30d)
  python3 trade_logger.py tax 2026      # print tax report for year
"""

import csv
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, date, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Paths — resolve relative to repo root (two levels up from this file)
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[1]  # live/monitoring -> live -> repo root
LOGS_DIR = _REPO_ROOT / "logs" / "trades"

TRADE_LOG_CSV = LOGS_DIR / "trade_log.csv"
PAPER_TRADES_CSV = LOGS_DIR / "paper_trades.csv"
DAILY_PNL_CSV = LOGS_DIR / "daily_pnl.csv"

TRADE_LOG_HEADERS = [
    "trade_id", "type", "pair", "side", "size",
    "entry_date", "entry_price",
    "exit_date", "exit_price",
    "stop_loss", "target",
    "exit_reason", "pnl_usd", "pnl_pct",
    "fees", "hold_days", "rationale", "notes",
]

DAILY_PNL_HEADERS = ["date", "realized_pnl", "open_positions", "total_trades", "wins", "losses"]

TAX_CSV_HEADERS = ["date", "pair", "side", "amount", "cost_basis", "proceeds", "gain_loss"]


def _ensure_csv(path: Path, headers: List[str]) -> None:
    """Create CSV with headers if it doesn't exist."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with open(path, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=headers).writeheader()


def _read_csv(path: Path) -> List[Dict[str, str]]:
    """Read all rows from a CSV file."""
    if not path.exists():
        return []
    with open(path, "r", newline="") as f:
        return list(csv.DictReader(f))


def _append_row(path: Path, headers: List[str], row: Dict[str, Any]) -> None:
    """Append a single row to a CSV file."""
    _ensure_csv(path, headers)
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writerow(row)


def _update_row(path: Path, headers: List[str], trade_id: str, updates: Dict[str, Any]) -> bool:
    """Update a row in a CSV file by trade_id. Returns True if found."""
    rows = _read_csv(path)
    found = False
    for row in rows:
        if row.get("trade_id") == trade_id:
            row.update(updates)
            found = True
    if found:
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    return found


def _parse_float(val: Any) -> float:
    try:
        return float(val) if val not in (None, "", "None") else 0.0
    except (ValueError, TypeError):
        return 0.0


def _parse_date(val: str) -> Optional[datetime]:
    if not val or val in ("None", ""):
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            pass
    return None


class TradeLogger:
    """
    Logs live and paper trades to CSV files and provides P&L / tax reporting.
    """

    def __init__(self, logs_dir: Optional[Path] = None):
        global TRADE_LOG_CSV, PAPER_TRADES_CSV, DAILY_PNL_CSV, LOGS_DIR
        if logs_dir:
            LOGS_DIR = Path(logs_dir)
            TRADE_LOG_CSV = LOGS_DIR / "trade_log.csv"
            PAPER_TRADES_CSV = LOGS_DIR / "paper_trades.csv"
            DAILY_PNL_CSV = LOGS_DIR / "daily_pnl.csv"
        # Ensure all CSVs exist with proper headers
        _ensure_csv(TRADE_LOG_CSV, TRADE_LOG_HEADERS)
        _ensure_csv(PAPER_TRADES_CSV, TRADE_LOG_HEADERS)
        _ensure_csv(DAILY_PNL_CSV, DAILY_PNL_HEADERS)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _csv_path(self, is_paper: bool) -> Path:
        return PAPER_TRADES_CSV if is_paper else TRADE_LOG_CSV

    def _log_entry_internal(
        self,
        trade_id: str,
        pair: str,
        side: str,
        size: float,
        entry_price: float,
        stop_loss: float,
        target: float,
        rationale: str,
        trade_type: str = "live",
    ) -> Dict[str, Any]:
        row = {
            "trade_id": trade_id,
            "type": trade_type,
            "pair": pair.upper(),
            "side": side.upper(),
            "size": size,
            "entry_date": datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S"),
            "entry_price": entry_price,
            "exit_date": "",
            "exit_price": "",
            "stop_loss": stop_loss,
            "target": target,
            "exit_reason": "",
            "pnl_usd": "",
            "pnl_pct": "",
            "fees": 0.0,
            "hold_days": "",
            "rationale": rationale,
            "notes": "",
        }
        is_paper = trade_type == "paper"
        csv_path = self._csv_path(is_paper)
        _append_row(csv_path, TRADE_LOG_HEADERS, row)
        return row

    def _log_exit_internal(
        self,
        trade_id: str,
        exit_price: float,
        exit_reason: str,
        notes: str,
        is_paper: bool = False,
        fees: float = 0.0,
    ) -> Optional[Dict[str, Any]]:
        csv_path = self._csv_path(is_paper)
        rows = _read_csv(csv_path)
        target_row = None
        for row in rows:
            if row.get("trade_id") == trade_id:
                target_row = row
                break
        if not target_row:
            return None

        entry_price = _parse_float(target_row.get("entry_price"))
        size = _parse_float(target_row.get("size"))
        side = target_row.get("side", "BUY").upper()
        entry_date = _parse_date(target_row.get("entry_date", ""))
        exit_date = datetime.now(timezone.utc).replace(tzinfo=None)

        # P&L calculation
        if side == "BUY" or side == "LONG":
            pnl_usd = (exit_price - entry_price) * size - fees
        else:  # SHORT / SELL
            pnl_usd = (entry_price - exit_price) * size - fees

        pnl_pct = (pnl_usd / (entry_price * size)) * 100 if entry_price * size != 0 else 0.0
        hold_days = (exit_date - entry_date).days if entry_date else ""

        updates = {
            "exit_date": exit_date.strftime("%Y-%m-%d %H:%M:%S"),
            "exit_price": exit_price,
            "exit_reason": exit_reason,
            "pnl_usd": round(pnl_usd, 4),
            "pnl_pct": round(pnl_pct, 4),
            "fees": fees,
            "hold_days": hold_days,
            "notes": notes,
        }
        _update_row(csv_path, TRADE_LOG_HEADERS, trade_id, updates)
        target_row.update(updates)

        # Snapshot daily P&L
        self._snapshot_daily_pnl()
        return target_row

    def _snapshot_daily_pnl(self) -> None:
        """Append or update today's P&L snapshot in daily_pnl.csv."""
        today = date.today().isoformat()
        trades = _read_csv(TRADE_LOG_CSV)
        today_trades = [
            t for t in trades
            if t.get("exit_date", "").startswith(today) and t.get("pnl_usd") not in ("", None)
        ]
        realized_pnl = sum(_parse_float(t["pnl_usd"]) for t in today_trades)
        open_positions = len([t for t in trades if not t.get("exit_date")])
        wins = len([t for t in today_trades if _parse_float(t["pnl_usd"]) > 0])
        losses = len([t for t in today_trades if _parse_float(t["pnl_usd"]) <= 0])

        # Read existing daily rows
        daily_rows = _read_csv(DAILY_PNL_CSV)
        existing = [r for r in daily_rows if r.get("date") == today]
        new_row = {
            "date": today,
            "realized_pnl": round(realized_pnl, 4),
            "open_positions": open_positions,
            "total_trades": len(today_trades),
            "wins": wins,
            "losses": losses,
        }
        if existing:
            for r in daily_rows:
                if r.get("date") == today:
                    r.update(new_row)
            with open(DAILY_PNL_CSV, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=DAILY_PNL_HEADERS)
                writer.writeheader()
                writer.writerows(daily_rows)
        else:
            _append_row(DAILY_PNL_CSV, DAILY_PNL_HEADERS, new_row)

    # ------------------------------------------------------------------
    # Public API — trade entry / exit
    # ------------------------------------------------------------------

    def log_entry(
        self,
        trade_id: str,
        pair: str,
        side: str,
        size: float,
        entry_price: float,
        stop_loss: float,
        target: float,
        rationale: str,
    ) -> Dict[str, Any]:
        """Log a new live trade entry."""
        return self._log_entry_internal(
            trade_id, pair, side, size, entry_price, stop_loss, target, rationale, trade_type="live"
        )

    def log_exit(
        self,
        trade_id: str,
        exit_price: float,
        exit_reason: str,
        notes: str = "",
        fees: float = 0.0,
    ) -> Optional[Dict[str, Any]]:
        """Log trade exit with P&L calculation."""
        return self._log_exit_internal(trade_id, exit_price, exit_reason, notes, is_paper=False, fees=fees)

    def log_paper_trade(
        self,
        trade_id: str,
        pair: str,
        side: str,
        size: float,
        entry_price: float,
        stop_loss: float,
        target: float,
        rationale: str,
        exit_price: Optional[float] = None,
        exit_reason: str = "",
        notes: str = "",
    ) -> Dict[str, Any]:
        """Log a paper trade entry (and optionally exit in one call)."""
        row = self._log_entry_internal(
            trade_id, pair, side, size, entry_price, stop_loss, target, rationale, trade_type="paper"
        )
        if exit_price is not None:
            self._log_exit_internal(trade_id, exit_price, exit_reason, notes, is_paper=True)
        return row

    def log_paper_exit(
        self,
        trade_id: str,
        exit_price: float,
        exit_reason: str,
        notes: str = "",
        fees: float = 0.0,
    ) -> Optional[Dict[str, Any]]:
        """Log exit for a paper trade."""
        return self._log_exit_internal(trade_id, exit_price, exit_reason, notes, is_paper=True, fees=fees)

    # ------------------------------------------------------------------
    # Public API — queries
    # ------------------------------------------------------------------

    def get_open_trades(self, include_paper: bool = False) -> List[Dict[str, str]]:
        """Return all currently open (not yet exited) trades."""
        trades = _read_csv(TRADE_LOG_CSV)
        if include_paper:
            trades += _read_csv(PAPER_TRADES_CSV)
        return [t for t in trades if not t.get("exit_date")]

    def get_trade_history(self, days: int = 30, include_paper: bool = False) -> List[Dict[str, str]]:
        """Return trades entered within the last `days` days."""
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
        trades = _read_csv(TRADE_LOG_CSV)
        if include_paper:
            trades += _read_csv(PAPER_TRADES_CSV)
        result = []
        for t in trades:
            dt = _parse_date(t.get("entry_date", ""))
            if dt and dt >= cutoff:
                result.append(t)
        return sorted(result, key=lambda x: x.get("entry_date", ""), reverse=True)

    def get_daily_summary(self) -> Dict[str, Any]:
        """Return today's P&L, open positions, and account status."""
        today = date.today().isoformat()
        trades = _read_csv(TRADE_LOG_CSV)

        today_closed = [
            t for t in trades
            if t.get("exit_date", "").startswith(today) and t.get("pnl_usd") not in ("", None)
        ]
        open_trades = [t for t in trades if not t.get("exit_date")]
        realized_pnl = sum(_parse_float(t["pnl_usd"]) for t in today_closed)
        wins = [t for t in today_closed if _parse_float(t["pnl_usd"]) > 0]
        losses = [t for t in today_closed if _parse_float(t["pnl_usd"]) <= 0]

        unrealized = 0.0  # Placeholder — would need live prices to compute

        return {
            "date": today,
            "realized_pnl_usd": round(realized_pnl, 4),
            "unrealized_pnl_usd": unrealized,
            "open_positions": len(open_trades),
            "open_trades": open_trades,
            "trades_today": len(today_closed),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_pct": round(len(wins) / len(today_closed) * 100, 1) if today_closed else 0.0,
            "best_trade_usd": max((_parse_float(t["pnl_usd"]) for t in today_closed), default=0.0),
            "worst_trade_usd": min((_parse_float(t["pnl_usd"]) for t in today_closed), default=0.0),
        }

    def get_weekly_summary(self) -> Dict[str, Any]:
        """Return weekly win/loss, total P&L, best/worst trade."""
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)
        trades = _read_csv(TRADE_LOG_CSV)
        week_closed = [
            t for t in trades
            if _parse_date(t.get("exit_date", "")) and _parse_date(t["exit_date"]) >= cutoff
            and t.get("pnl_usd") not in ("", None)
        ]
        pnls = [_parse_float(t["pnl_usd"]) for t in week_closed]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        return {
            "period": f"{(date.today() - timedelta(days=6)).isoformat()} to {date.today().isoformat()}",
            "total_trades": len(week_closed),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_pct": round(len(wins) / len(week_closed) * 100, 1) if week_closed else 0.0,
            "total_pnl_usd": round(sum(pnls), 4),
            "avg_win_usd": round(sum(wins) / len(wins), 4) if wins else 0.0,
            "avg_loss_usd": round(sum(losses) / len(losses), 4) if losses else 0.0,
            "best_trade_usd": max(pnls, default=0.0),
            "worst_trade_usd": min(pnls, default=0.0),
            "profit_factor": round(abs(sum(wins) / sum(losses)), 2) if losses and sum(losses) != 0 else None,
        }

    def get_monthly_report(self, year: Optional[int] = None, month: Optional[int] = None) -> Dict[str, Any]:
        """Full monthly performance report."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        year = year or now.year
        month = month or now.month
        prefix = f"{year}-{month:02d}"

        trades = _read_csv(TRADE_LOG_CSV)
        month_closed = [
            t for t in trades
            if t.get("exit_date", "").startswith(prefix) and t.get("pnl_usd") not in ("", None)
        ]
        month_opened = [
            t for t in trades
            if t.get("entry_date", "").startswith(prefix)
        ]
        pnls = [_parse_float(t["pnl_usd"]) for t in month_closed]
        wins = [p for p in pnls if p > 0]
        losses_val = [p for p in pnls if p <= 0]

        # Group by pair
        by_pair: Dict[str, List[float]] = defaultdict(list)
        for t in month_closed:
            by_pair[t.get("pair", "?")].append(_parse_float(t["pnl_usd"]))

        pair_summary = {pair: {"trades": len(vals), "pnl": round(sum(vals), 4)} for pair, vals in by_pair.items()}

        hold_days = [_parse_float(t["hold_days"]) for t in month_closed if t.get("hold_days") not in ("", None)]

        return {
            "period": f"{year}-{month:02d}",
            "trades_opened": len(month_opened),
            "trades_closed": len(month_closed),
            "wins": len(wins),
            "losses": len(losses_val),
            "win_rate_pct": round(len(wins) / len(month_closed) * 100, 1) if month_closed else 0.0,
            "total_pnl_usd": round(sum(pnls), 4),
            "total_fees_usd": round(sum(_parse_float(t.get("fees", 0)) for t in month_closed), 4),
            "avg_win_usd": round(sum(wins) / len(wins), 4) if wins else 0.0,
            "avg_loss_usd": round(sum(losses_val) / len(losses_val), 4) if losses_val else 0.0,
            "best_trade_usd": max(pnls, default=0.0),
            "worst_trade_usd": min(pnls, default=0.0),
            "profit_factor": round(abs(sum(wins) / sum(losses_val)), 2) if losses_val and sum(losses_val) != 0 else None,
            "avg_hold_days": round(sum(hold_days) / len(hold_days), 1) if hold_days else 0.0,
            "by_pair": pair_summary,
        }

    # ------------------------------------------------------------------
    # Tax tracking
    # ------------------------------------------------------------------

    def get_realized_gains(self, year: int) -> Dict[str, Any]:
        """Return total realized gains/losses for a tax year."""
        prefix = str(year)
        trades = _read_csv(TRADE_LOG_CSV)
        year_trades = [
            t for t in trades
            if t.get("exit_date", "").startswith(prefix) and t.get("pnl_usd") not in ("", None)
        ]
        pnls = [_parse_float(t["pnl_usd"]) for t in year_trades]
        gains = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

        return {
            "tax_year": year,
            "total_trades": len(year_trades),
            "total_realized_pnl_usd": round(sum(pnls), 4),
            "total_gains_usd": round(sum(gains), 4),
            "total_losses_usd": round(sum(losses), 4),
            "net_gain_loss_usd": round(sum(pnls), 4),
            "total_fees_usd": round(sum(_parse_float(t.get("fees", 0)) for t in year_trades), 4),
        }

    def get_cost_basis_report(self) -> List[Dict[str, Any]]:
        """
        FIFO cost basis for all closed trades.
        Returns a list of records with cost basis, proceeds, and gain/loss.
        """
        trades = _read_csv(TRADE_LOG_CSV)
        closed = [t for t in trades if t.get("exit_date") and t.get("exit_price")]
        closed_sorted = sorted(closed, key=lambda x: x.get("entry_date", ""))

        report = []
        for t in closed_sorted:
            size = _parse_float(t["size"])
            entry_price = _parse_float(t["entry_price"])
            exit_price = _parse_float(t["exit_price"])
            fees = _parse_float(t.get("fees", 0))

            cost_basis = entry_price * size
            proceeds = exit_price * size - fees
            gain_loss = proceeds - cost_basis

            report.append({
                "trade_id": t["trade_id"],
                "pair": t["pair"],
                "side": t["side"],
                "size": size,
                "entry_date": t["entry_date"],
                "exit_date": t["exit_date"],
                "cost_basis_usd": round(cost_basis, 4),
                "proceeds_usd": round(proceeds, 4),
                "gain_loss_usd": round(gain_loss, 4),
                "fees": fees,
                "method": "FIFO",
            })
        return report

    def export_tax_csv(self, year: int, filepath: str) -> str:
        """
        Export tax-ready CSV for a given year.
        Columns: date, pair, side, amount, cost_basis, proceeds, gain_loss
        """
        prefix = str(year)
        trades = _read_csv(TRADE_LOG_CSV)
        year_trades = sorted(
            [t for t in trades if t.get("exit_date", "").startswith(prefix) and t.get("exit_price")],
            key=lambda x: x.get("exit_date", ""),
        )

        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=TAX_CSV_HEADERS)
            writer.writeheader()
            for t in year_trades:
                size = _parse_float(t["size"])
                entry_price = _parse_float(t["entry_price"])
                exit_price = _parse_float(t["exit_price"])
                fees = _parse_float(t.get("fees", 0))
                cost_basis = entry_price * size
                proceeds = exit_price * size - fees
                gain_loss = proceeds - cost_basis
                writer.writerow({
                    "date": t["exit_date"],
                    "pair": t["pair"],
                    "side": t["side"],
                    "amount": size,
                    "cost_basis": round(cost_basis, 4),
                    "proceeds": round(proceeds, 4),
                    "gain_loss": round(gain_loss, 4),
                })
        return str(filepath)

    # ------------------------------------------------------------------
    # Pretty-print helpers
    # ------------------------------------------------------------------

    def print_daily_summary(self) -> None:
        s = self.get_daily_summary()
        print("=" * 60)
        print(f"  DAILY SUMMARY — {s['date']}")
        print("=" * 60)
        print(f"  Realized P&L:    ${s['realized_pnl_usd']:>10.2f}")
        print(f"  Open Positions:  {s['open_positions']:>10}")
        print(f"  Trades Today:    {s['trades_today']:>10}")
        print(f"  Wins / Losses:   {s['wins']} / {s['losses']}")
        print(f"  Win Rate:        {s['win_rate_pct']:>9.1f}%")
        print(f"  Best Trade:      ${s['best_trade_usd']:>10.2f}")
        print(f"  Worst Trade:     ${s['worst_trade_usd']:>10.2f}")
        if s["open_trades"]:
            print(f"\n  Open Trades:")
            for t in s["open_trades"]:
                print(f"    [{t['trade_id']}] {t['pair']} {t['side']} {t['size']} @ {t['entry_price']}")
        print("=" * 60)

    def print_history(self, days: int = 30) -> None:
        trades = self.get_trade_history(days=days)
        print("=" * 80)
        print(f"  TRADE HISTORY — last {days} days ({len(trades)} trades)")
        print("=" * 80)
        if not trades:
            print("  No trades found.")
        else:
            print(f"  {'ID':<12} {'Pair':<10} {'Side':<5} {'Size':>8} {'Entry':>10} {'Exit':>10} {'P&L':>9} {'Status':<8}")
            print("  " + "-" * 76)
            for t in trades:
                status = "OPEN" if not t.get("exit_date") else "CLOSED"
                pnl = f"${_parse_float(t['pnl_usd']):>8.2f}" if t.get("pnl_usd") else "       —"
                print(
                    f"  {t['trade_id']:<12} {t['pair']:<10} {t['side']:<5} "
                    f"{_parse_float(t['size']):>8.4f} {_parse_float(t['entry_price']):>10.4f} "
                    f"{_parse_float(t.get('exit_price', 0)):>10.4f} {pnl} {status:<8}"
                )
        print("=" * 80)

    def print_tax_report(self, year: int) -> None:
        gains = self.get_realized_gains(year)
        basis = self.get_cost_basis_report()
        year_basis = [r for r in basis if str(year) in r.get("exit_date", "")]

        print("=" * 60)
        print(f"  TAX REPORT — {year}")
        print("=" * 60)
        print(f"  Total Trades:      {gains['total_trades']:>8}")
        print(f"  Total Gains:       ${gains['total_gains_usd']:>10.2f}")
        print(f"  Total Losses:      ${gains['total_losses_usd']:>10.2f}")
        print(f"  Net Gain/Loss:     ${gains['net_gain_loss_usd']:>10.2f}")
        print(f"  Total Fees:        ${gains['total_fees_usd']:>10.2f}")
        print(f"  Cost Basis Method: FIFO")
        if year_basis:
            print(f"\n  {'Trade ID':<14} {'Pair':<10} {'Cost Basis':>12} {'Proceeds':>12} {'Gain/Loss':>12}")
            print("  " + "-" * 64)
            for r in year_basis:
                print(
                    f"  {r['trade_id']:<14} {r['pair']:<10} "
                    f"${r['cost_basis_usd']:>11.2f} ${r['proceeds_usd']:>11.2f} ${r['gain_loss_usd']:>11.2f}"
                )
        print("=" * 60)
        print(f"  Rule #95: Expand or die.")
        print("=" * 60)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    logger = TradeLogger()
    args = sys.argv[1:]

    if not args:
        print("Usage: python3 trade_logger.py [summary|history|tax <year>]")
        sys.exit(0)

    cmd = args[0].lower()

    if cmd == "summary":
        logger.print_daily_summary()

    elif cmd == "history":
        days = int(args[1]) if len(args) > 1 else 30
        logger.print_history(days=days)

    elif cmd == "tax":
        year = int(args[1]) if len(args) > 1 else datetime.now(timezone.utc).replace(tzinfo=None).year
        logger.print_tax_report(year)

    else:
        print(f"Unknown command: {cmd}")
        print("Usage: python3 trade_logger.py [summary|history|tax <year>]")
        sys.exit(1)


if __name__ == "__main__":
    main()
