#!/usr/bin/env python3
"""
rsi_overlay.py — RSI Timing Overlay for Macro Swing Strategy

Adds RSI-based entry timing on top of the macro swing strategy signals.
Two modes:
  BASELINE   - Enter on signal day (original behavior)
  RSI_FILTER - When signal fires, wait up to 5 days for RSI < 35 confirmation.
               If confirmed: full size entry. If not by day 5: enter at 50% size.

Supports configurable RSI periods (default 14, also tested 7 and 21).
"""

import csv
import datetime
import math
from dataclasses import dataclass, field
from typing import Optional

from backtest.strategies.macro_swing import (
    Trade, BacktestState, COST_RT, STOP_LOSS_PCT, TP_RATIO, TP_FRACTION,
    MAX_HOLD_DAYS, load_price_data, load_macro_events,
    compute_signal_score, get_position_size, days_between,
)


# ─── RSI Calculation ─────────────────────────────────────────────────────────

def calculate_rsi(price_data: dict, period: int = 14) -> dict:
    """
    Calculate RSI for all dates in price_data using Wilder's smoothing.
    Returns dict: date_str → rsi_value (or None if insufficient data).
    """
    dates = sorted(price_data.keys())
    closes = [price_data[d]["close"] for d in dates]

    rsi = {}
    if len(closes) < period + 1:
        for d in dates:
            rsi[d] = None
        return rsi

    # Initial averages over first `period` changes
    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(c, 0) for c in changes]
    losses = [abs(min(c, 0)) for c in changes]

    # First RSI uses simple average
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    # Dates without RSI (not enough data)
    for d in dates[:period]:
        rsi[d] = None

    # First RSI value
    def _rsi_from_avgs(ag, al):
        if al == 0:
            return 100.0
        rs = ag / al
        return 100.0 - (100.0 / (1.0 + rs))

    rsi[dates[period]] = _rsi_from_avgs(avg_gain, avg_loss)

    # Wilder smoothing for subsequent values
    for i in range(period + 1, len(dates)):
        g = gains[i - 1]
        l = losses[i - 1]
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period
        rsi[dates[i]] = _rsi_from_avgs(avg_gain, avg_loss)

    return rsi


# ─── Pending Signal Tracker ───────────────────────────────────────────────────

@dataclass
class PendingSignal:
    """Tracks a macro signal waiting for RSI confirmation."""
    signal_date: str
    score: int
    position_size_full: float
    days_waited: int = 0
    confirmed: bool = False


# ─── Strategy Runner ──────────────────────────────────────────────────────────

def run_strategy_with_rsi(
    price_data: dict,
    macro_events: dict,
    start_date: str,
    end_date: str,
    rsi_period: int = 14,
    rsi_threshold: float = 35.0,
    max_wait_days: int = 5,
    mode: str = "rsi_filter",   # "baseline" or "rsi_filter"
    initial_capital: float = 100000.0,
) -> tuple["BacktestState", list[str]]:
    """
    Run macro swing strategy with optional RSI timing overlay.

    mode="baseline"  → enter on signal day (mirrors original macro_swing behavior)
    mode="rsi_filter" → wait up to max_wait_days for RSI < rsi_threshold;
                        enter full size if confirmed, 50% size if not confirmed.
    """
    state = BacktestState(account_value=initial_capital)
    log_lines = []

    # Pre-calculate RSI for all dates
    rsi_values = calculate_rsi(price_data, period=rsi_period)

    all_dates = sorted([d for d in price_data.keys() if start_date <= d <= end_date])
    if not all_dates:
        return state, log_lines

    pending: Optional[PendingSignal] = None  # RSI-mode only

    def close_position(trade: Trade, close_price: float, date: str, reason: str):
        """Close position and update account (mirrors macro_swing logic)."""
        trade.exit_date = date
        trade.exit_price = close_price
        trade.exit_reason = reason
        entry = trade.entry_price

        if trade.direction == "long":
            if trade.partial_tp_taken and trade.partial_tp_price is not None:
                remaining_frac = 1.0 - TP_FRACTION
                rem_return = (close_price / entry - 1.0) - COST_RT / 2
                trade.pnl_pct = (
                    TP_FRACTION * ((trade.partial_tp_price / entry - 1.0) - COST_RT / 2)
                    + remaining_frac * rem_return
                )
            else:
                trade.pnl_pct = (close_price / entry - 1.0) - COST_RT
        else:
            trade.pnl_pct = 0.0

        position_value = trade.account_value_before * trade.position_size_pct
        if trade.partial_tp_taken:
            remaining_value = position_value * (1.0 - TP_FRACTION)
            rem_return = (close_price / entry - 1.0) - COST_RT / 2
            pnl_dollars = remaining_value * rem_return
            new_account = state.account_value + pnl_dollars
        else:
            new_account = (
                trade.account_value_before
                - position_value
                + position_value * (1.0 + trade.pnl_pct)
            )

        trade.account_value_after = new_account
        state.account_value = new_account
        state.trades.append(trade)
        state.current_position = None
        log_lines.append(
            f"CLOSE {date} | {reason} | entry={entry:.2f} exit={close_price:.2f} "
            f"| PnL={trade.pnl_pct*100:.2f}% | Account={new_account:.2f}"
        )

    def open_position(date: str, entry_price: float, score: int, pos_size: float):
        """Open a new long position."""
        sl_price = entry_price * (1.0 - STOP_LOSS_PCT)
        tp_price = entry_price * (1.0 + STOP_LOSS_PCT * TP_RATIO)
        trade = Trade(
            entry_date=date,
            entry_price=entry_price,
            direction="long",
            score=score,
            position_size_pct=pos_size,
            stop_loss=sl_price,
            take_profit=tp_price,
            account_value_before=state.account_value,
        )
        state.current_position = trade
        log_lines.append(
            f"OPEN {date} | score={score:+d} | LONG {pos_size*100:.0f}% "
            f"| entry={entry_price:.2f} SL={sl_price:.2f} TP={tp_price:.2f} "
            f"| RSI={rsi_values.get(date, 'N/A')} | Account={state.account_value:.2f}"
        )

    for date in all_dates:
        bar = price_data[date]
        open_p = bar["open"]
        high_p = bar["high"]
        low_p = bar["low"]
        close_p = bar["close"]
        rsi_today = rsi_values.get(date)

        day_events = macro_events.get(date, [])

        # Update Fed rate
        for ev in day_events:
            if ev.get("event_type", "").upper() == "FOMC":
                rate_str = ev.get("rate_after", "")
                if rate_str:
                    try:
                        state.current_rate = float(rate_str)
                    except ValueError:
                        pass

        # ── Manage existing position ──────────────────────────────────────────
        if state.current_position is not None:
            pos = state.current_position
            entry = pos.entry_price
            sl = pos.stop_loss
            tp = pos.take_profit
            hold_days = days_between(pos.entry_date, date)

            if pos.direction == "long":
                if low_p <= sl:
                    close_position(pos, sl, date, "stop_loss")
                elif not pos.partial_tp_taken and high_p >= tp:
                    tp_price = tp
                    pos.partial_tp_taken = True
                    pos.partial_tp_price = tp_price
                    partial_pnl = (tp_price / entry - 1.0) - COST_RT / 2
                    partial_dollars = (
                        pos.account_value_before * pos.position_size_pct
                        * TP_FRACTION * partial_pnl
                    )
                    state.account_value += partial_dollars
                    log_lines.append(
                        f"PARTIAL_TP {date} | price={tp_price:.2f} | 60% taken "
                        f"| partial_pnl={partial_pnl*100:.2f}% | Account={state.account_value:.2f}"
                    )
                    pos.stop_loss = entry * (1.0 + COST_RT)
                elif hold_days >= MAX_HOLD_DAYS:
                    close_position(pos, close_p, date, "time_stop")

        # ── Generate signal from today's events ───────────────────────────────
        if day_events:
            score, signals = compute_signal_score(day_events, state.current_rate)
            if signals:
                log_lines.append(
                    f"SIGNAL {date} | score={score:+d} | {' | '.join(signals)}"
                )

            if mode == "baseline":
                # Original behavior: enter immediately on signal day
                if score >= 2 and state.current_position is None:
                    pos_size = get_position_size(score)
                    open_position(date, close_p, score, pos_size)
                elif score <= -2 and state.current_position is not None:
                    close_position(state.current_position, close_p, date, "signal")

            elif mode == "rsi_filter":
                if score >= 2 and state.current_position is None and pending is None:
                    # Set up pending signal to wait for RSI confirmation
                    pos_size = get_position_size(score)
                    pending = PendingSignal(
                        signal_date=date,
                        score=score,
                        position_size_full=pos_size,
                    )
                    rsi_str = f"{rsi_today:.1f}" if rsi_today is not None else "N/A"
                    log_lines.append(
                        f"PENDING {date} | score={score:+d} | Waiting for RSI<{rsi_threshold:.0f} "
                        f"(current RSI={rsi_str})"
                    )
                elif score <= -2 and state.current_position is not None:
                    close_position(state.current_position, close_p, date, "signal")
                    pending = None  # Cancel pending if any

        # ── Process pending RSI-filtered signal ───────────────────────────────
        if mode == "rsi_filter" and pending is not None and state.current_position is None:
            pending.days_waited += 1

            rsi_val = rsi_values.get(date)
            if rsi_val is not None and rsi_val < rsi_threshold:
                # RSI confirmed: enter full size
                log_lines.append(
                    f"RSI_CONFIRM {date} | RSI={rsi_val:.1f} < {rsi_threshold:.0f} "
                    f"| day {pending.days_waited} of {max_wait_days}"
                )
                open_position(date, close_p, pending.score, pending.position_size_full)
                pending = None
            elif pending.days_waited >= max_wait_days:
                # Timeout: enter at 50% size
                half_size = pending.position_size_full * 0.5
                rsi_timeout_str = f"{rsi_val:.1f}" if rsi_val is not None else "N/A"
                log_lines.append(
                    f"RSI_TIMEOUT {date} | RSI={rsi_timeout_str} "
                    f"| No confirmation after {max_wait_days} days → entering at 50% size"
                )
                open_position(date, close_p, pending.score, half_size)
                pending = None

    # Close any open position at end
    if state.current_position is not None:
        last_date = all_dates[-1]
        last_close = price_data[last_date]["close"]
        close_position(state.current_position, last_close, last_date, "eod")

    return state, log_lines


def compute_rsi_metrics(
    state: BacktestState,
    initial_capital: float,
    start_date: str,
    end_date: str,
    price_data: dict,
    rsi_values: dict,
) -> dict:
    """Extended metrics including RSI-specific stats."""
    trades = state.trades
    final_value = state.account_value
    total_return = final_value / initial_capital - 1.0

    d1 = datetime.datetime.strptime(start_date, "%Y-%m-%d")
    d2 = datetime.datetime.strptime(end_date, "%Y-%m-%d")
    years = (d2 - d1).days / 365.25
    ann_return = (
        (final_value / initial_capital) ** (1.0 / years) - 1.0
        if years > 0 and final_value > 0
        else 0.0
    )

    winning = [t for t in trades if t.pnl_pct is not None and t.pnl_pct > 0]
    losing = [t for t in trades if t.pnl_pct is not None and t.pnl_pct <= 0]
    n_trades = len(trades)
    win_rate = len(winning) / n_trades if n_trades else 0.0
    avg_win = sum(t.pnl_pct for t in winning) / len(winning) if winning else 0.0
    avg_loss = sum(t.pnl_pct for t in losing) / len(losing) if losing else 0.0

    gross_profit = sum(t.pnl_pct for t in winning)
    gross_loss = abs(sum(t.pnl_pct for t in losing))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Max drawdown
    account_series = [initial_capital] + [t.account_value_after for t in trades]
    peak = account_series[0]
    max_dd = 0.0
    for v in account_series:
        if v > peak:
            peak = v
        dd = (peak - v) / peak
        if dd > max_dd:
            max_dd = dd

    # Average entry RSI
    entry_rsis = []
    for t in trades:
        rv = rsi_values.get(t.entry_date)
        if rv is not None:
            entry_rsis.append(rv)
    avg_entry_rsi = sum(entry_rsis) / len(entry_rsis) if entry_rsis else None

    # Average entry price
    avg_entry_price = (
        sum(t.entry_price for t in trades) / n_trades if n_trades else None
    )

    # Sharpe
    if n_trades >= 2:
        returns = [t.pnl_pct for t in trades if t.pnl_pct is not None]
        mean_r = sum(returns) / len(returns)
        variance = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
        std_r = math.sqrt(variance) if variance > 0 else 0.0001
        ann_factor = math.sqrt(365.25 / 14)
        sharpe = (mean_r / std_r) * ann_factor
    else:
        sharpe = 0.0

    return {
        "initial_capital": initial_capital,
        "final_value": final_value,
        "total_return": total_return,
        "annualized_return": ann_return,
        "max_drawdown": max_dd,
        "n_trades": n_trades,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "sharpe": sharpe,
        "avg_entry_rsi": avg_entry_rsi,
        "avg_entry_price": avg_entry_price,
        "years": years,
    }
