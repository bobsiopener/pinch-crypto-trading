#!/usr/bin/env python3
"""
run_candlestick_backtest.py — Candlestick Pattern Filter Backtest

Runs the macro swing strategy TWO ways:
  BASELINE : Enter on signal day (current behavior — close price of signal day)
  FILTERED : When macro signal fires (score ≥ 2), wait up to 3 trading days
             for a bullish candlestick confirmation (engulfing, hammer, morning star).
             If found → enter that day.
             If not found by day 3 → enter on day 3 anyway.

Compares: win rate, average entry price improvement, total return, drawdown.
Saves results to backtest/results/candlestick_filter_results.md

Usage: python3 backtest/run_candlestick_backtest.py
"""

import csv
import os
import sys
import datetime
import math
from dataclasses import dataclass, field
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from strategies.macro_swing import (
    load_price_data,
    load_macro_events,
    compute_signal_score,
    get_position_size,
    compute_buy_hold,
    days_between,
    Trade,
    BacktestState,
    COST_RT,
    STOP_LOSS_PCT,
    TP_RATIO,
    TP_FRACTION,
    MAX_HOLD_DAYS,
)
from strategies.candlestick_filter import (
    is_bullish_confirmation,
    PatternResult,
)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

BTC_CSV = os.path.join(DATA_DIR, "btc_daily.csv")
MACRO_CSV = os.path.join(DATA_DIR, "macro_events.csv")
RESULTS_MD = os.path.join(RESULTS_DIR, "candlestick_filter_results.md")

BACKTEST_START = "2022-01-01"
BACKTEST_END = "2026-03-01"
INITIAL_CAPITAL = 100_000.0
CONFIRMATION_WINDOW = 3  # Trading days to wait for candlestick confirmation


# ---------------------------------------------------------------------------
# Extended Trade dataclass with candlestick metadata
# ---------------------------------------------------------------------------

@dataclass
class CSFilterTrade(Trade):
    candlestick_confirmed: bool = False
    candlestick_pattern: str = ""
    signal_date: str = ""        # Date macro signal fired
    days_waited: int = 0         # Trading days between signal and entry


# ---------------------------------------------------------------------------
# Strategy runners
# ---------------------------------------------------------------------------

def run_baseline(
    price_data: dict,
    macro_events: dict,
    start_date: str,
    end_date: str,
    initial_capital: float = 100_000.0,
) -> tuple[BacktestState, list[CSFilterTrade], list[str]]:
    """
    BASELINE: Enter on the signal day close (original behavior).
    Returns identical logic to macro_swing.run_strategy but with CSFilterTrade.
    """
    state = BacktestState(account_value=initial_capital)
    trades: list[CSFilterTrade] = []
    log_lines: list[str] = []

    all_dates = sorted([d for d in price_data.keys() if start_date <= d <= end_date])

    def close_position(trade: CSFilterTrade, close_price: float, date: str, reason: str):
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
            new_account = trade.account_value_before - position_value + position_value * (1.0 + trade.pnl_pct)

        trade.account_value_after = new_account
        state.account_value = new_account
        trades.append(trade)
        state.current_position = None
        log_lines.append(
            f"CLOSE {date} | {reason} | entry={entry:.2f} exit={close_price:.2f} "
            f"| PnL={trade.pnl_pct*100:.2f}% | Account={new_account:.2f}"
        )

    for date in all_dates:
        bar = price_data[date]
        open_p, high_p, low_p, close_p = bar["open"], bar["high"], bar["low"], bar["close"]

        day_events = macro_events.get(date, [])
        for ev in day_events:
            if ev.get("event_type", "").upper() == "FOMC":
                rate_str = ev.get("rate_after", "")
                if rate_str:
                    try:
                        state.current_rate = float(rate_str)
                    except ValueError:
                        pass

        # Manage existing position
        if state.current_position is not None:
            pos = state.current_position
            entry = pos.entry_price
            sl, tp = pos.stop_loss, pos.take_profit
            hold_days = days_between(pos.entry_date, date)

            if pos.direction == "long":
                if low_p <= sl:
                    close_position(pos, sl, date, "stop_loss")
                elif not pos.partial_tp_taken and high_p >= tp:
                    pos.partial_tp_taken = True
                    pos.partial_tp_price = tp
                    partial_pnl = (tp / entry - 1.0) - COST_RT / 2
                    partial_dollars = pos.account_value_before * pos.position_size_pct * TP_FRACTION * partial_pnl
                    state.account_value += partial_dollars
                    pos.stop_loss = entry * (1.0 + COST_RT)
                    log_lines.append(
                        f"PARTIAL_TP {date} | price={tp:.2f} | 60% taken "
                        f"| partial_pnl={partial_pnl*100:.2f}% | Account={state.account_value:.2f}"
                    )
                elif hold_days >= MAX_HOLD_DAYS:
                    close_position(pos, close_p, date, "time_stop")

        # Generate signal
        if day_events:
            score, signals = compute_signal_score(day_events, state.current_rate)
            if signals:
                log_lines.append(f"SIGNAL {date} | score={score:+d} | {' | '.join(signals)}")

            if score >= 2 and state.current_position is None:
                pos_size = get_position_size(score)
                entry_price = close_p
                sl_price = entry_price * (1.0 - STOP_LOSS_PCT)
                tp_price = entry_price * (1.0 + STOP_LOSS_PCT * TP_RATIO)
                trade = CSFilterTrade(
                    entry_date=date,
                    entry_price=entry_price,
                    direction="long",
                    score=score,
                    position_size_pct=pos_size,
                    stop_loss=sl_price,
                    take_profit=tp_price,
                    account_value_before=state.account_value,
                    signal_date=date,
                    candlestick_confirmed=False,
                    candlestick_pattern="(baseline — no filter)",
                    days_waited=0,
                )
                state.current_position = trade
                log_lines.append(
                    f"OPEN {date} | score={score:+d} | LONG {pos_size*100:.0f}% "
                    f"| entry={entry_price:.2f} SL={sl_price:.2f} TP={tp_price:.2f}"
                )

            elif score <= -2 and state.current_position is not None:
                close_position(state.current_position, close_p, date, "signal")

    if state.current_position is not None:
        last_date = all_dates[-1]
        last_close = price_data[last_date]["close"]
        close_position(state.current_position, last_close, last_date, "eod")

    state.trades = trades
    return state, trades, log_lines


def run_filtered(
    price_data: dict,
    macro_events: dict,
    start_date: str,
    end_date: str,
    initial_capital: float = 100_000.0,
    confirmation_window: int = CONFIRMATION_WINDOW,
) -> tuple[BacktestState, list[CSFilterTrade], list[str]]:
    """
    FILTERED: When macro signal fires (score ≥ 2), wait up to `confirmation_window`
    trading days for a bullish candlestick pattern. Enter on confirmation day or
    on the last day of the window (whichever comes first).
    """
    state = BacktestState(account_value=initial_capital)
    trades: list[CSFilterTrade] = []
    log_lines: list[str] = []

    all_dates = sorted([d for d in price_data.keys() if start_date <= d <= end_date])

    # Pending entry state
    pending: Optional[dict] = None  # {signal_date, score, pos_size, days_left}

    def close_position(trade: CSFilterTrade, close_price: float, date: str, reason: str):
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
            new_account = trade.account_value_before - position_value + position_value * (1.0 + trade.pnl_pct)

        trade.account_value_after = new_account
        state.account_value = new_account
        trades.append(trade)
        state.current_position = None
        log_lines.append(
            f"CLOSE {date} | {reason} | entry={entry:.2f} exit={close_price:.2f} "
            f"| PnL={trade.pnl_pct*100:.2f}% | Account={new_account:.2f}"
        )

    def open_position(date: str, close_p: float, score: int, pos_size: float,
                      confirmed: bool, pattern_str: str, signal_date: str, days_waited: int):
        entry_price = close_p
        sl_price = entry_price * (1.0 - STOP_LOSS_PCT)
        tp_price = entry_price * (1.0 + STOP_LOSS_PCT * TP_RATIO)
        trade = CSFilterTrade(
            entry_date=date,
            entry_price=entry_price,
            direction="long",
            score=score,
            position_size_pct=pos_size,
            stop_loss=sl_price,
            take_profit=tp_price,
            account_value_before=state.account_value,
            signal_date=signal_date,
            candlestick_confirmed=confirmed,
            candlestick_pattern=pattern_str,
            days_waited=days_waited,
        )
        state.current_position = trade
        conf_label = "CONFIRMED" if confirmed else "TIMEOUT (no confirmation)"
        log_lines.append(
            f"OPEN {date} | score={score:+d} | LONG {pos_size*100:.0f}% "
            f"| entry={entry_price:.2f} SL={sl_price:.2f} TP={tp_price:.2f} "
            f"| CS={conf_label} pattern={pattern_str} waited={days_waited}d"
        )

    for i, date in enumerate(all_dates):
        bar = price_data[date]
        open_p, high_p, low_p, close_p = bar["open"], bar["high"], bar["low"], bar["close"]

        day_events = macro_events.get(date, [])
        for ev in day_events:
            if ev.get("event_type", "").upper() == "FOMC":
                rate_str = ev.get("rate_after", "")
                if rate_str:
                    try:
                        state.current_rate = float(rate_str)
                    except ValueError:
                        pass

        # --- Manage existing position ---
        if state.current_position is not None:
            pos = state.current_position
            entry = pos.entry_price
            sl, tp = pos.stop_loss, pos.take_profit
            hold_days = days_between(pos.entry_date, date)

            if pos.direction == "long":
                if low_p <= sl:
                    close_position(pos, sl, date, "stop_loss")
                elif not pos.partial_tp_taken and high_p >= tp:
                    pos.partial_tp_taken = True
                    pos.partial_tp_price = tp
                    partial_pnl = (tp / entry - 1.0) - COST_RT / 2
                    partial_dollars = pos.account_value_before * pos.position_size_pct * TP_FRACTION * partial_pnl
                    state.account_value += partial_dollars
                    pos.stop_loss = entry * (1.0 + COST_RT)
                    log_lines.append(
                        f"PARTIAL_TP {date} | price={tp:.2f} | 60% taken "
                        f"| partial_pnl={partial_pnl*100:.2f}% | Account={state.account_value:.2f}"
                    )
                elif hold_days >= MAX_HOLD_DAYS:
                    close_position(pos, close_p, date, "time_stop")

        # --- Check for pending entry (candlestick confirmation window) ---
        if pending is not None and state.current_position is None:
            sig_date = pending["signal_date"]
            score = pending["score"]
            pos_size = pending["pos_size"]
            days_waited = pending["days_waited"]

            # Check candlestick confirmation on this day
            confirmed, pattern_result = is_bullish_confirmation(date, price_data, all_dates)

            pending["days_waited"] += 1
            days_waited = pending["days_waited"]
            last_chance = days_waited >= confirmation_window

            pattern_str = str(pattern_result)

            if confirmed:
                log_lines.append(
                    f"CS_CONFIRM {date} | {pattern_str} | signal was {sig_date} | waited {days_waited}d"
                )
                open_position(date, close_p, score, pos_size, True, pattern_str, sig_date, days_waited)
                pending = None
            elif last_chance:
                log_lines.append(
                    f"CS_TIMEOUT {date} | no pattern in {confirmation_window}d | entering anyway"
                )
                open_position(date, close_p, score, pos_size, False, "[timeout]", sig_date, days_waited)
                pending = None

        # --- Generate signal from today's events ---
        if day_events:
            score, signals = compute_signal_score(day_events, state.current_rate)
            if signals:
                log_lines.append(f"SIGNAL {date} | score={score:+d} | {' | '.join(signals)}")

            if score >= 2 and state.current_position is None and pending is None:
                pos_size = get_position_size(score)
                log_lines.append(
                    f"PENDING {date} | score={score:+d} | Waiting up to {confirmation_window}d "
                    f"for candlestick confirmation..."
                )
                pending = {
                    "signal_date": date,
                    "score": score,
                    "pos_size": pos_size,
                    "days_waited": 0,
                }

            elif score <= -2 and state.current_position is not None:
                close_position(state.current_position, close_p, date, "signal")
                # Cancel any pending entry too
                pending = None

    # Close any open position at end of backtest
    if state.current_position is not None:
        last_date = all_dates[-1]
        last_close = price_data[last_date]["close"]
        close_position(state.current_position, last_close, last_date, "eod")

    # If we had a pending entry at EOD, cancel it (no entry)
    if pending is not None:
        log_lines.append(f"PENDING_CANCELLED | signal {pending['signal_date']} | EOD reached without entry")

    state.trades = trades
    return state, trades, log_lines


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_metrics_ext(
    trades: list[CSFilterTrade],
    initial_capital: float,
    start_date: str,
    end_date: str,
) -> dict:
    final_value = initial_capital
    if trades:
        final_value = trades[-1].account_value_after

    d1 = datetime.datetime.strptime(start_date, "%Y-%m-%d")
    d2 = datetime.datetime.strptime(end_date, "%Y-%m-%d")
    years = (d2 - d1).days / 365.25

    total_return = final_value / initial_capital - 1.0
    ann_return = (final_value / initial_capital) ** (1.0 / years) - 1.0 if years > 0 else 0.0

    winning = [t for t in trades if t.pnl_pct is not None and t.pnl_pct > 0]
    losing = [t for t in trades if t.pnl_pct is not None and t.pnl_pct <= 0]
    n = len(trades)
    win_rate = len(winning) / n if n > 0 else 0.0
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

    # Sharpe
    if n >= 2:
        returns = [t.pnl_pct for t in trades if t.pnl_pct is not None]
        mean_r = sum(returns) / len(returns)
        variance = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
        std_r = math.sqrt(variance) if variance > 0 else 0.0001
        ann_factor = math.sqrt(365.25 / 14)
        sharpe = (mean_r / std_r) * ann_factor
    else:
        sharpe = 0.0

    # Candlestick confirmation stats
    cs_trades = [t for t in trades if hasattr(t, "candlestick_confirmed")]
    confirmed_trades = [t for t in cs_trades if t.candlestick_confirmed]
    unconfirmed_trades = [t for t in cs_trades if not t.candlestick_confirmed]

    confirmed_win_rate = (
        len([t for t in confirmed_trades if t.pnl_pct and t.pnl_pct > 0]) / len(confirmed_trades)
        if confirmed_trades else 0.0
    )
    unconfirmed_win_rate = (
        len([t for t in unconfirmed_trades if t.pnl_pct and t.pnl_pct > 0]) / len(unconfirmed_trades)
        if unconfirmed_trades else 0.0
    )

    return {
        "initial_capital": initial_capital,
        "final_value": final_value,
        "total_return": total_return,
        "annualized_return": ann_return,
        "max_drawdown": max_dd,
        "sharpe": sharpe,
        "n_trades": n,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "years": years,
        "n_confirmed": len(confirmed_trades),
        "n_unconfirmed": len(unconfirmed_trades),
        "confirmed_win_rate": confirmed_win_rate,
        "unconfirmed_win_rate": unconfirmed_win_rate,
    }


def avg_entry_price_improvement(baseline_trades: list, filtered_trades: list, price_data: dict) -> dict:
    """
    Compare average entry prices for matched signals.
    For each filtered trade, compute how the entry price compares to what baseline
    would have entered (signal day close).
    Returns improvement stats.
    """
    improvements = []
    for ft in filtered_trades:
        if not hasattr(ft, "signal_date") or not ft.signal_date:
            continue
        signal_close = price_data.get(ft.signal_date, {}).get("close")
        if signal_close is None:
            continue
        if ft.days_waited == 0:
            continue  # Entered same day — no difference
        # Positive = entered lower (better for long), negative = entered higher (worse)
        pct_diff = (ft.entry_price - signal_close) / signal_close
        improvements.append({
            "signal_date": ft.signal_date,
            "entry_date": ft.entry_date,
            "days_waited": ft.days_waited,
            "signal_close": signal_close,
            "entry_price": ft.entry_price,
            "pct_diff": pct_diff,
            "confirmed": ft.candlestick_confirmed,
        })

    if not improvements:
        return {"n": 0, "avg_pct_diff": 0.0, "positive_count": 0, "negative_count": 0}

    avg_diff = sum(r["pct_diff"] for r in improvements) / len(improvements)
    positive = [r for r in improvements if r["pct_diff"] < 0]  # entered lower = better
    negative = [r for r in improvements if r["pct_diff"] >= 0]  # entered higher = worse

    return {
        "n": len(improvements),
        "avg_pct_diff": avg_diff,
        "avg_pct_improvement": -avg_diff,  # positive = better entry
        "positive_count": len(positive),  # trades that got lower entry
        "negative_count": len(negative),  # trades that got higher entry
        "details": improvements,
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def fmt_pct(v: float) -> str:
    return f"{v*100:.2f}%"

def fmt_dollar(v: float) -> str:
    return f"${v:,.2f}"


def save_results_md(
    baseline_metrics: dict,
    filtered_metrics: dict,
    bh: dict,
    baseline_trades: list[CSFilterTrade],
    filtered_trades: list[CSFilterTrade],
    entry_improvement: dict,
    path: str,
):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # Build pattern frequency table for filtered trades
    pattern_counts: dict[str, int] = {}
    for t in filtered_trades:
        pat = t.candlestick_pattern if t.candlestick_pattern else "[none]"
        pattern_counts[pat] = pattern_counts.get(pat, 0) + 1

    # Exit reason breakdown
    def exit_breakdown(trades):
        counts = {}
        for t in trades:
            r = t.exit_reason or "unknown"
            counts[r] = counts.get(r, 0) + 1
        return counts

    baseline_exits = exit_breakdown(baseline_trades)
    filtered_exits = exit_breakdown(filtered_trades)

    # Improvement sign: negative pct_diff = entered lower = better for longs
    avg_improvement_pct = entry_improvement.get("avg_pct_improvement", 0.0) * 100
    improvement_label = f"{avg_improvement_pct:+.2f}%"
    if avg_improvement_pct > 0:
        improvement_note = "✅ Filtered strategy entered at a **lower** average price"
    elif avg_improvement_pct < 0:
        improvement_note = "⚠️ Filtered strategy entered at a **higher** average price (market ran away)"
    else:
        improvement_note = "➡️ No material entry price difference"

    md = f"""# Candlestick Pattern Filter — Backtest Results

**Generated:** {now}  
**Period:** {BACKTEST_START} → {BACKTEST_END}  
**Initial Capital:** {fmt_dollar(INITIAL_CAPITAL)}  
**Confirmation Window:** Up to {CONFIRMATION_WINDOW} trading days  

---

## Summary: Baseline vs Filtered

| Metric | BASELINE | FILTERED | Δ |
|--------|----------|----------|---|
| Final Value | {fmt_dollar(baseline_metrics['final_value'])} | {fmt_dollar(filtered_metrics['final_value'])} | {fmt_dollar(filtered_metrics['final_value'] - baseline_metrics['final_value'])} |
| Total Return | {fmt_pct(baseline_metrics['total_return'])} | {fmt_pct(filtered_metrics['total_return'])} | {fmt_pct(filtered_metrics['total_return'] - baseline_metrics['total_return'])} |
| Annualized Return | {fmt_pct(baseline_metrics['annualized_return'])} | {fmt_pct(filtered_metrics['annualized_return'])} | {fmt_pct(filtered_metrics['annualized_return'] - baseline_metrics['annualized_return'])} |
| Max Drawdown | {fmt_pct(baseline_metrics['max_drawdown'])} | {fmt_pct(filtered_metrics['max_drawdown'])} | {fmt_pct(filtered_metrics['max_drawdown'] - baseline_metrics['max_drawdown'])} |
| Sharpe Ratio | {baseline_metrics['sharpe']:.3f} | {filtered_metrics['sharpe']:.3f} | {filtered_metrics['sharpe'] - baseline_metrics['sharpe']:+.3f} |
| Number of Trades | {baseline_metrics['n_trades']} | {filtered_metrics['n_trades']} | — |
| Win Rate | {fmt_pct(baseline_metrics['win_rate'])} | {fmt_pct(filtered_metrics['win_rate'])} | {fmt_pct(filtered_metrics['win_rate'] - baseline_metrics['win_rate'])} |
| Avg Win | {fmt_pct(baseline_metrics['avg_win'])} | {fmt_pct(filtered_metrics['avg_win'])} | {fmt_pct(filtered_metrics['avg_win'] - baseline_metrics['avg_win'])} |
| Avg Loss | {fmt_pct(baseline_metrics['avg_loss'])} | {fmt_pct(filtered_metrics['avg_loss'])} | {fmt_pct(filtered_metrics['avg_loss'] - baseline_metrics['avg_loss'])} |
| Profit Factor | {baseline_metrics['profit_factor']:.3f} | {filtered_metrics['profit_factor']:.3f} | {filtered_metrics['profit_factor'] - baseline_metrics['profit_factor']:+.3f} |

**Buy & Hold BTC:** {fmt_pct(bh.get('total_return', 0))} ({fmt_dollar(bh.get('final_value', 0))})

---

## Entry Price Improvement Analysis

> When the filtered strategy waits for candlestick confirmation, does it get a better entry price?

| Metric | Value |
|--------|-------|
| Trades that waited (delayed entry) | {entry_improvement.get('n', 0)} |
| Average entry price change vs signal day | {improvement_label} |
| Entered at lower price (better) | {entry_improvement.get('positive_count', 0)} trades |
| Entered at higher price (market ran) | {entry_improvement.get('negative_count', 0)} trades |

{improvement_note}

---

## Candlestick Confirmation Stats (Filtered)

| Metric | Value |
|--------|-------|
| Trades with confirmation | {filtered_metrics.get('n_confirmed', 0)} |
| Trades without (timeout) | {filtered_metrics.get('n_unconfirmed', 0)} |
| Win Rate (confirmed) | {fmt_pct(filtered_metrics.get('confirmed_win_rate', 0))} |
| Win Rate (timed out) | {fmt_pct(filtered_metrics.get('unconfirmed_win_rate', 0))} |

### Pattern Frequencies
{chr(10).join(f'- `{k}`: {v}' for k, v in sorted(pattern_counts.items(), key=lambda x: -x[1]))}

---

## Exit Reason Breakdown

| Exit Reason | BASELINE | FILTERED |
|-------------|----------|----------|
{"".join(f'| {r} | {baseline_exits.get(r, 0)} | {filtered_exits.get(r, 0)} |{chr(10)}' for r in sorted(set(list(baseline_exits.keys()) + list(filtered_exits.keys()))))}

---

## Baseline Trade Log

| # | Signal Date | Entry Date | Entry $ | Exit $ | PnL% | Exit Reason | CS Pattern |
|---|-------------|------------|---------|--------|------|-------------|------------|
"""

    for i, t in enumerate(baseline_trades, 1):
        pnl = f"{t.pnl_pct*100:.2f}%" if t.pnl_pct is not None else "—"
        md += (
            f"| {i} | {t.signal_date or t.entry_date} | {t.entry_date} | "
            f"{fmt_dollar(t.entry_price)} | "
            f"{fmt_dollar(t.exit_price) if t.exit_price else '—'} | "
            f"{pnl} | {t.exit_reason or '—'} | {t.candlestick_pattern} |\n"
        )

    md += """
---

## Filtered Trade Log

| # | Signal Date | Entry Date | Days Waited | Entry $ | Exit $ | PnL% | Exit Reason | CS Confirmed | CS Pattern |
|---|-------------|------------|-------------|---------|--------|------|-------------|--------------|------------|
"""

    for i, t in enumerate(filtered_trades, 1):
        pnl = f"{t.pnl_pct*100:.2f}%" if t.pnl_pct is not None else "—"
        confirmed_str = "✅ YES" if t.candlestick_confirmed else "❌ NO"
        md += (
            f"| {i} | {t.signal_date or t.entry_date} | {t.entry_date} | "
            f"{t.days_waited}d | "
            f"{fmt_dollar(t.entry_price)} | "
            f"{fmt_dollar(t.exit_price) if t.exit_price else '—'} | "
            f"{pnl} | {t.exit_reason or '—'} | {confirmed_str} | {t.candlestick_pattern} |\n"
        )

    md += f"""
---

## Verdict

"""
    # Add a verdict based on results
    win_rate_delta = filtered_metrics['win_rate'] - baseline_metrics['win_rate']
    return_delta = filtered_metrics['total_return'] - baseline_metrics['total_return']
    dd_delta = filtered_metrics['max_drawdown'] - baseline_metrics['max_drawdown']

    verdict_parts = []
    if win_rate_delta > 0.05:
        verdict_parts.append(f"✅ Win rate improved by {fmt_pct(win_rate_delta)} with candlestick filter")
    elif win_rate_delta < -0.05:
        verdict_parts.append(f"⚠️ Win rate decreased by {fmt_pct(abs(win_rate_delta))} — filter may be skipping good setups")
    else:
        verdict_parts.append(f"➡️ Win rate largely unchanged ({fmt_pct(win_rate_delta)} delta)")

    if return_delta > 0.02:
        verdict_parts.append(f"✅ Total return improved by {fmt_pct(return_delta)}")
    elif return_delta < -0.02:
        verdict_parts.append(f"⚠️ Total return decreased by {fmt_pct(abs(return_delta))} — delayed entries cost performance")
    else:
        verdict_parts.append(f"➡️ Total return similar ({fmt_pct(return_delta)} delta)")

    if dd_delta < -0.02:
        verdict_parts.append(f"✅ Max drawdown reduced by {fmt_pct(abs(dd_delta))}")
    elif dd_delta > 0.02:
        verdict_parts.append(f"⚠️ Max drawdown increased by {fmt_pct(dd_delta)}")
    else:
        verdict_parts.append(f"➡️ Max drawdown similar ({fmt_pct(dd_delta)} delta)")

    for vp in verdict_parts:
        md += f"- {vp}\n"

    md += f"""
**Recommendation:** {"Add the candlestick filter to the live strategy." if (win_rate_delta > 0 and return_delta > 0) else "The filter shows mixed results; further optimization of the confirmation window may help." if (win_rate_delta + return_delta > 0) else "The baseline strategy is preferred; the candlestick filter delays entries without sufficient benefit."}

---

> *Rule of Acquisition #22: A wise man can hear profit in the wind.*  
> *But a smart Ferengi waits for the candle to confirm it.*
"""

    with open(path, "w") as f:
        f.write(md)
    print(f"Results saved: {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 65)
    print("PINCH CANDLESTICK FILTER BACKTEST")
    print("=" * 65)
    print(f"Period: {BACKTEST_START} → {BACKTEST_END}")
    print(f"Capital: {fmt_dollar(INITIAL_CAPITAL)}")
    print(f"Confirmation Window: {CONFIRMATION_WINDOW} trading days")
    print()

    for path, label in [(BTC_CSV, "BTC CSV"), (MACRO_CSV, "Macro CSV")]:
        if not os.path.exists(path):
            print(f"ERROR: {label} not found at {path}")
            sys.exit(1)

    print("[1/6] Loading price data...")
    price_data = load_price_data(BTC_CSV)
    print(f"  BTC: {len(price_data)} daily bars loaded")

    print("[2/6] Loading macro events...")
    macro_events = load_macro_events(MACRO_CSV)
    print(f"  Macro events: {sum(len(v) for v in macro_events.values())} events on {len(macro_events)} dates")

    print("[3/6] Running BASELINE strategy (enter on signal day)...")
    baseline_state, baseline_trades, baseline_log = run_baseline(
        price_data=price_data,
        macro_events=macro_events,
        start_date=BACKTEST_START,
        end_date=BACKTEST_END,
        initial_capital=INITIAL_CAPITAL,
    )
    print(f"  Baseline: {len(baseline_trades)} trades executed")

    print("[4/6] Running FILTERED strategy (wait up to 3d for candlestick)...")
    filtered_state, filtered_trades, filtered_log = run_filtered(
        price_data=price_data,
        macro_events=macro_events,
        start_date=BACKTEST_START,
        end_date=BACKTEST_END,
        initial_capital=INITIAL_CAPITAL,
        confirmation_window=CONFIRMATION_WINDOW,
    )
    print(f"  Filtered: {len(filtered_trades)} trades executed")

    print("[5/6] Computing metrics & comparing...")
    baseline_metrics = compute_metrics_ext(baseline_trades, INITIAL_CAPITAL, BACKTEST_START, BACKTEST_END)
    filtered_metrics = compute_metrics_ext(filtered_trades, INITIAL_CAPITAL, BACKTEST_START, BACKTEST_END)
    bh = compute_buy_hold(price_data, BACKTEST_START, BACKTEST_END, INITIAL_CAPITAL)
    entry_improvement = avg_entry_price_improvement(baseline_trades, filtered_trades, price_data)

    print("[6/6] Saving results...")
    os.makedirs(RESULTS_DIR, exist_ok=True)
    save_results_md(
        baseline_metrics,
        filtered_metrics,
        bh,
        baseline_trades,
        filtered_trades,
        entry_improvement,
        RESULTS_MD,
    )

    # Print comparison
    print()
    print("=" * 65)
    print("COMPARISON SUMMARY")
    print("=" * 65)
    print(f"{'Metric':<35} {'BASELINE':>12} {'FILTERED':>12} {'Δ':>10}")
    print("-" * 65)
    print(f"{'Final Value':<35} {fmt_dollar(baseline_metrics['final_value']):>12} {fmt_dollar(filtered_metrics['final_value']):>12} {fmt_dollar(filtered_metrics['final_value']-baseline_metrics['final_value']):>10}")
    print(f"{'Total Return':<35} {fmt_pct(baseline_metrics['total_return']):>12} {fmt_pct(filtered_metrics['total_return']):>12} {fmt_pct(filtered_metrics['total_return']-baseline_metrics['total_return']):>10}")
    print(f"{'Max Drawdown':<35} {fmt_pct(baseline_metrics['max_drawdown']):>12} {fmt_pct(filtered_metrics['max_drawdown']):>12} {fmt_pct(filtered_metrics['max_drawdown']-baseline_metrics['max_drawdown']):>10}")
    print(f"{'Win Rate':<35} {fmt_pct(baseline_metrics['win_rate']):>12} {fmt_pct(filtered_metrics['win_rate']):>12} {fmt_pct(filtered_metrics['win_rate']-baseline_metrics['win_rate']):>10}")
    print(f"{'Sharpe Ratio':<35} {baseline_metrics['sharpe']:>12.3f} {filtered_metrics['sharpe']:>12.3f} {filtered_metrics['sharpe']-baseline_metrics['sharpe']:>+10.3f}")
    print(f"{'Profit Factor':<35} {baseline_metrics['profit_factor']:>12.3f} {filtered_metrics['profit_factor']:>12.3f} {filtered_metrics['profit_factor']-baseline_metrics['profit_factor']:>+10.3f}")
    print(f"{'# Trades':<35} {baseline_metrics['n_trades']:>12} {filtered_metrics['n_trades']:>12}")
    print("-" * 65)
    print(f"{'Avg Entry Improvement (filtered)':<35} {entry_improvement.get('avg_pct_improvement', 0)*100:>+11.2f}%")
    n_conf = filtered_metrics.get('n_confirmed', 0)
    n_unconf = filtered_metrics.get('n_unconfirmed', 0)
    print(f"{'CS Confirmed / Timed Out':<35} {n_conf:>10} / {n_unconf}")
    print(f"{'Win Rate (confirmed)':<35} {fmt_pct(filtered_metrics.get('confirmed_win_rate', 0)):>12}")
    print(f"{'Win Rate (no confirm)':<35} {fmt_pct(filtered_metrics.get('unconfirmed_win_rate', 0)):>12}")
    print("=" * 65)
    print()
    print("Buy & Hold BTC for reference:")
    print(f"  Return: {fmt_pct(bh.get('total_return', 0))}  |  Final: {fmt_dollar(bh.get('final_value', 0))}")
    print()
    print("Rule of Acquisition #22: A wise man can hear profit in the wind.")
    print("But a smart Ferengi waits for the candle to confirm it.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
