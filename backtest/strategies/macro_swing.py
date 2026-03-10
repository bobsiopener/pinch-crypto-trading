#!/usr/bin/env python3
"""
macro_swing.py — Macro Swing Strategy Engine

Strategy: Trade BTC based on macro event signals (CPI, FOMC, NFP).
Signal scoring → position sizing → risk management (stop-loss, take-profit, time stop).
"""

import csv
import os
import datetime
import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Trade:
    entry_date: str
    entry_price: float
    direction: str          # 'long' or 'cash'
    score: int
    position_size_pct: float
    stop_loss: float
    take_profit: float
    exit_date: Optional[str] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None  # 'stop_loss', 'take_profit', 'time_stop', 'signal', 'eod'
    pnl_pct: Optional[float] = None
    account_value_before: float = 0.0
    account_value_after: float = 0.0
    partial_tp_taken: bool = False
    partial_tp_price: Optional[float] = None
    partial_tp_fraction: float = 0.60  # 60% taken at 2:1 R:R


@dataclass
class BacktestState:
    account_value: float = 100000.0
    current_position: Optional[Trade] = None
    trades: list = field(default_factory=list)
    current_rate: float = 5.50  # Fed funds rate


COST_RT = 0.0040          # 0.40% round-trip
STOP_LOSS_PCT = 0.08      # 8% stop loss
TP_RATIO = 2.0            # 2:1 reward/risk → take profit at 16% gain
TP_FRACTION = 0.60        # 60% taken at TP
MAX_HOLD_DAYS = 14        # time stop


def load_price_data(csv_path: str) -> dict:
    """Load price CSV into dict: date_str → row_dict."""
    prices = {}
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            prices[row["date"]] = {
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            }
    return prices


def load_macro_events(csv_path: str) -> dict:
    """Load macro events into dict: date_str → list of event_dicts."""
    events = {}
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            date = row["date"]
            if date not in events:
                events[date] = []
            events[date].append(dict(row))
    return events


def compute_signal_score(events: list, current_rate: float) -> tuple[int, list]:
    """
    Given a list of events on a date, compute composite signal score.
    Returns (score, list_of_signals_applied)
    """
    score = 0
    signals = []

    for event in events:
        etype = event.get("event_type", "").upper()
        surprise = event.get("surprise", "").lower().strip()

        if etype == "CPI":
            actual = float(event.get("actual", 0) or 0)
            expected = float(event.get("expected", 0) or 0)
            diff = actual - expected
            if surprise == "hot" or diff >= 0.2:
                score -= 2
                signals.append(f"CPI hot ({actual:.1f} vs {expected:.1f}): -2")
            elif surprise == "cool" or diff <= -0.2:
                score += 2
                signals.append(f"CPI cool ({actual:.1f} vs {expected:.1f}): +2")
            else:
                signals.append(f"CPI neutral ({actual:.1f} vs {expected:.1f}): 0")

        elif etype == "FOMC":
            action = event.get("action", "").lower()
            rate_after_str = event.get("rate_after", "")
            if rate_after_str:
                try:
                    new_rate = float(rate_after_str)
                except ValueError:
                    new_rate = current_rate
            else:
                new_rate = current_rate

            if surprise == "dovish":
                score += 3
                signals.append(f"FOMC dovish ({action}, rate→{new_rate}%): +3")
            elif surprise == "hawkish":
                score -= 3
                signals.append(f"FOMC hawkish ({action}, rate→{new_rate}%): -3")
            else:
                signals.append(f"FOMC neutral ({action}, rate→{new_rate}%): 0")

        elif etype == "NFP":
            if surprise == "weak":
                if current_rate > 4.0:
                    score += 1
                    signals.append(f"NFP weak (rate {current_rate:.2f}% > 4%): +1")
                else:
                    score -= 1
                    signals.append(f"NFP weak (rate {current_rate:.2f}% < 4%): -1")
            elif surprise == "strong":
                score -= 1
                signals.append(f"NFP strong: -1")
            else:
                signals.append(f"NFP neutral: 0")

    return score, signals


def get_position_size(score: int) -> float:
    """Return fraction of account to deploy."""
    abs_score = abs(score)
    if abs_score >= 3:
        return 0.30
    elif abs_score >= 2:
        return 0.20
    return 0.0


def days_between(d1: str, d2: str) -> int:
    """Days between two date strings YYYY-MM-DD."""
    dt1 = datetime.datetime.strptime(d1, "%Y-%m-%d")
    dt2 = datetime.datetime.strptime(d2, "%Y-%m-%d")
    return (dt2 - dt1).days


def run_strategy(
    price_data: dict,
    macro_events: dict,
    start_date: str,
    end_date: str,
    initial_capital: float = 100000.0,
) -> tuple[BacktestState, list[str]]:
    """
    Run macro swing strategy on BTC price data.
    Returns (final_state, trade_log_lines).
    """
    state = BacktestState(account_value=initial_capital)
    log_lines = []

    # Get sorted dates in range
    all_dates = sorted([d for d in price_data.keys() if start_date <= d <= end_date])
    if not all_dates:
        print(f"ERROR: No price data in range {start_date} to {end_date}")
        return state, log_lines

    def close_position(trade: Trade, close_price: float, date: str, reason: str):
        """Close a position and update account."""
        trade.exit_date = date
        trade.exit_price = close_price
        trade.exit_reason = reason

        entry = trade.entry_price
        entry_cost = 1.0 + COST_RT / 2  # half round-trip on entry

        if trade.direction == "long":
            if trade.partial_tp_taken and trade.partial_tp_price is not None:
                # Already took 60% at TP price, now close remaining 40%
                remaining_frac = 1.0 - TP_FRACTION
                # PnL from partial TP (already booked into account via partial logic)
                # PnL from remainder
                rem_return = (close_price / entry - 1.0) - COST_RT / 2
                trade.pnl_pct = (
                    TP_FRACTION * ((trade.partial_tp_price / entry - 1.0) - COST_RT / 2)
                    + remaining_frac * rem_return
                )
            else:
                trade.pnl_pct = (close_price / entry - 1.0) - COST_RT
        else:
            trade.pnl_pct = 0.0

        # Apply PnL to account
        position_value = trade.account_value_before * trade.position_size_pct
        pnl_dollars = position_value * trade.pnl_pct
        # If partial TP was already applied, we need to only add remaining PnL
        if trade.partial_tp_taken:
            # Partial TP was already added to account_value_before (of the remaining position)
            remaining_value = position_value * (1.0 - TP_FRACTION)
            rem_return = (close_price / entry - 1.0) - COST_RT / 2
            pnl_dollars = remaining_value * rem_return
            # Don't double-count the partial TP that was already booked
            new_account = state.account_value + pnl_dollars
        else:
            new_account = trade.account_value_before - position_value + position_value * (1.0 + trade.pnl_pct)

        trade.account_value_after = new_account
        state.account_value = new_account
        state.trades.append(trade)
        state.current_position = None
        log_lines.append(
            f"CLOSE {date} | {reason} | entry={entry:.2f} exit={close_price:.2f} "
            f"| PnL={trade.pnl_pct*100:.2f}% | Account={new_account:.2f}"
        )

    for date in all_dates:
        bar = price_data[date]
        open_p = bar["open"]
        high_p = bar["high"]
        low_p = bar["low"]
        close_p = bar["close"]

        # --- Check events on this date ---
        day_events = macro_events.get(date, [])

        # Update Fed rate from FOMC events
        for ev in day_events:
            if ev.get("event_type", "").upper() == "FOMC":
                rate_str = ev.get("rate_after", "")
                if rate_str:
                    try:
                        state.current_rate = float(rate_str)
                    except ValueError:
                        pass

        # --- Manage existing position first ---
        if state.current_position is not None:
            pos = state.current_position
            entry = pos.entry_price
            sl = pos.stop_loss
            tp = pos.take_profit
            hold_days = days_between(pos.entry_date, date)

            if pos.direction == "long":
                # Check stop loss (intraday low)
                if low_p <= sl:
                    close_position(pos, sl, date, "stop_loss")
                # Check take profit (intraday high) — partial TP
                elif not pos.partial_tp_taken and high_p >= tp:
                    # Take 60% off at TP
                    tp_price = tp
                    pos.partial_tp_taken = True
                    pos.partial_tp_price = tp_price
                    partial_pnl = (tp_price / entry - 1.0) - COST_RT / 2
                    partial_dollars = pos.account_value_before * pos.position_size_pct * TP_FRACTION * partial_pnl
                    state.account_value += partial_dollars
                    log_lines.append(
                        f"PARTIAL_TP {date} | price={tp_price:.2f} | 60% taken "
                        f"| partial_pnl={partial_pnl*100:.2f}% | Account={state.account_value:.2f}"
                    )
                    # Adjust stop to break-even on remainder
                    pos.stop_loss = entry * (1.0 + COST_RT)
                # Time stop
                elif hold_days >= MAX_HOLD_DAYS:
                    close_position(pos, close_p, date, "time_stop")

        # --- Generate signal from today's events ---
        if day_events:
            score, signals = compute_signal_score(day_events, state.current_rate)

            if signals:
                log_lines.append(
                    f"SIGNAL {date} | score={score:+d} | {' | '.join(signals)}"
                )

            # Act on signal at next open (use today's close as proxy for signal timing)
            if score >= 2 and state.current_position is None:
                # BUY signal
                pos_size = get_position_size(score)
                entry_price = close_p  # Enter at close on signal day (simplified)
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
                    f"| Account={state.account_value:.2f}"
                )

            elif score <= -2 and state.current_position is not None:
                # SELL/EXIT signal
                close_position(state.current_position, close_p, date, "signal")

    # Close any open position at end of backtest
    if state.current_position is not None:
        last_date = all_dates[-1]
        last_close = price_data[last_date]["close"]
        close_position(state.current_position, last_close, last_date, "eod")

    return state, log_lines


def compute_metrics(state: BacktestState, initial_capital: float, start_date: str, end_date: str) -> dict:
    """Compute performance metrics from completed backtest state."""
    trades = state.trades
    final_value = state.account_value
    total_return = (final_value / initial_capital - 1.0)

    # Annualized return
    d1 = datetime.datetime.strptime(start_date, "%Y-%m-%d")
    d2 = datetime.datetime.strptime(end_date, "%Y-%m-%d")
    years = (d2 - d1).days / 365.25
    if years > 0 and final_value > 0:
        ann_return = (final_value / initial_capital) ** (1.0 / years) - 1.0
    else:
        ann_return = 0.0

    # Win/loss stats
    winning = [t for t in trades if t.pnl_pct is not None and t.pnl_pct > 0]
    losing = [t for t in trades if t.pnl_pct is not None and t.pnl_pct <= 0]
    n_trades = len(trades)
    win_rate = len(winning) / n_trades if n_trades > 0 else 0.0
    avg_win = sum(t.pnl_pct for t in winning) / len(winning) if winning else 0.0
    avg_loss = sum(t.pnl_pct for t in losing) / len(losing) if losing else 0.0
    gross_profit = sum(t.pnl_pct for t in winning)
    gross_loss = abs(sum(t.pnl_pct for t in losing))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Max drawdown (account value series)
    # Reconstruct account value series
    account_series = [initial_capital]
    for t in trades:
        account_series.append(t.account_value_after)
    peak = account_series[0]
    max_dd = 0.0
    for v in account_series:
        if v > peak:
            peak = v
        dd = (peak - v) / peak
        if dd > max_dd:
            max_dd = dd

    # Sharpe ratio (simplified: use trade returns)
    if n_trades >= 2:
        returns = [t.pnl_pct for t in trades if t.pnl_pct is not None]
        mean_r = sum(returns) / len(returns)
        variance = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
        std_r = math.sqrt(variance) if variance > 0 else 0.0001
        # Annualize: assume average ~14 days per trade
        ann_factor = math.sqrt(365.25 / 14)
        sharpe = (mean_r / std_r) * ann_factor if std_r > 0 else 0.0
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
        "years": years,
    }


def compute_buy_hold(price_data: dict, start_date: str, end_date: str, initial_capital: float) -> dict:
    """Compute buy-and-hold BTC benchmark metrics."""
    dates = sorted([d for d in price_data.keys() if start_date <= d <= end_date])
    if not dates:
        return {}
    start_price = price_data[dates[0]]["close"]
    end_price = price_data[dates[-1]]["close"]
    total_return = end_price / start_price - 1.0
    years = (
        datetime.datetime.strptime(dates[-1], "%Y-%m-%d")
        - datetime.datetime.strptime(dates[0], "%Y-%m-%d")
    ).days / 365.25
    ann_return = (end_price / start_price) ** (1.0 / years) - 1.0 if years > 0 else 0.0

    # Max drawdown for BH
    peak = start_price
    max_dd = 0.0
    for d in dates:
        p = price_data[d]["close"]
        if p > peak:
            peak = p
        dd = (peak - p) / peak
        if dd > max_dd:
            max_dd = dd

    return {
        "start_price": start_price,
        "end_price": end_price,
        "total_return": total_return,
        "annualized_return": ann_return,
        "max_drawdown": max_dd,
        "final_value": initial_capital * (1.0 + total_return),
    }
