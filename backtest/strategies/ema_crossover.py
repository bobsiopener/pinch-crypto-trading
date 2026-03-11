#!/usr/bin/env python3
"""
ema_crossover.py — EMA Crossover Trend-Following Strategy

Strategy:
  - Calculate fast and slow EMA on daily close prices
  - BUY (long) when fast EMA crosses ABOVE slow EMA  (golden cross)
  - SELL (cash) when fast EMA crosses BELOW slow EMA  (death cross)
  - Position size: 80% of account value when long, 0% when in cash
  - Trading cost: 0.40% round-trip applied on every entry/exit
  - Optional: 10% trailing stop-loss from entry high-water mark
"""

import csv
import math
from dataclasses import dataclass, field
from typing import Optional, List, Dict


COST_RT   = 0.004   # 0.40% round-trip
POSITION  = 0.80    # 80% of account when long
TRAIL_PCT = 0.10    # 10% trailing stop from peak


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Trade:
    entry_date: str
    entry_price: float
    exit_date: Optional[str]   = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None   # 'signal' | 'trailing_stop'
    pnl_pct: Optional[float]   = None
    hold_days: Optional[int]   = None
    account_value_before: float = 0.0
    account_value_after:  float = 0.0


@dataclass
class BacktestState:
    account_value: float = 100_000.0
    in_position:   bool  = False
    current_trade: Optional[Trade] = None
    trades: List[Trade]  = field(default_factory=list)
    peak_price: float    = 0.0   # for trailing stop


# ---------------------------------------------------------------------------
# EMA calculation (pure Python, also accepts pandas Series)
# ---------------------------------------------------------------------------

def calc_ema(prices: list, period: int) -> list:
    """Return a list of EMA values (same length as prices; NaN for warm-up)."""
    k = 2.0 / (period + 1)
    ema = [float("nan")] * len(prices)
    # seed with first non-NaN value
    for i, p in enumerate(prices):
        if not math.isnan(p):
            ema[i] = p
            start = i + 1
            break
    else:
        return ema
    for i in range(start, len(prices)):
        if math.isnan(prices[i]):
            ema[i] = float("nan")
        else:
            ema[i] = prices[i] * k + ema[i - 1] * (1 - k)
    return ema


# ---------------------------------------------------------------------------
# Single backtest run
# ---------------------------------------------------------------------------

def run_backtest(
    dates:       List[str],
    closes:      List[float],
    highs:       List[float],
    lows:        List[float],
    fast_period: int,
    slow_period: int,
    trailing_stop: bool = False,
    start_date: str = "2022-01-01",
    end_date:   str = "2026-03-01",
    initial_capital: float = 100_000.0,
) -> Dict:
    """
    Run one EMA crossover backtest.

    Returns a dict with:
        trades          – list of Trade objects
        equity_curve    – list of (date, account_value)
        final_value     – float
        params          – dict of input params
    """
    fast_ema = calc_ema(closes, fast_period)
    slow_ema = calc_ema(closes, slow_period)

    state = BacktestState(account_value=initial_capital)
    equity_curve: List[tuple] = []

    for i in range(len(dates)):
        date = dates[i]
        if date < start_date or date > end_date:
            continue

        close = closes[i]
        high  = highs[i]
        low   = lows[i]
        fe    = fast_ema[i]
        se    = slow_ema[i]

        if math.isnan(fe) or math.isnan(se):
            equity_curve.append((date, state.account_value))
            continue

        # Determine previous non-NaN cross
        prev_fast = prev_slow = float("nan")
        for j in range(i - 1, -1, -1):
            if not math.isnan(fast_ema[j]) and not math.isnan(slow_ema[j]):
                prev_fast = fast_ema[j]
                prev_slow = slow_ema[j]
                break

        golden_cross = (not math.isnan(prev_fast)) and (prev_fast <= prev_slow) and (fe > se)
        death_cross  = (not math.isnan(prev_fast)) and (prev_fast >= prev_slow) and (fe < se)

        # --- Trailing stop check (intra-bar, checked before signal) ---
        if state.in_position and trailing_stop and state.current_trade:
            state.peak_price = max(state.peak_price, high)
            stop_level = state.peak_price * (1 - TRAIL_PCT)
            if low <= stop_level:
                exit_price = stop_level  # assume fill at stop
                t = state.current_trade
                t.exit_date   = date
                t.exit_price  = exit_price
                t.exit_reason = "trailing_stop"
                gross_return  = (exit_price / t.entry_price) - 1.0
                net_return    = gross_return - COST_RT      # cost already deducted at entry; deduct exit half
                invested      = t.account_value_before * POSITION
                gain          = invested * net_return
                t.pnl_pct     = net_return * 100
                t.hold_days   = _days_diff(t.entry_date, date)
                t.account_value_after = t.account_value_before + gain
                state.account_value   = t.account_value_after
                state.in_position     = False
                state.current_trade   = None
                state.trades.append(t)
                equity_curve.append((date, state.account_value))
                continue

        # --- Signal handling ---
        if golden_cross and not state.in_position:
            # Enter long: pay entry half of round-trip cost
            entry_cost = state.account_value * POSITION * (COST_RT / 2)
            trade = Trade(
                entry_date          = date,
                entry_price         = close,
                account_value_before= state.account_value,
            )
            state.account_value  -= entry_cost
            state.in_position     = True
            state.current_trade   = trade
            state.peak_price      = close

        elif death_cross and state.in_position and state.current_trade:
            # Exit long: pay exit half of round-trip cost
            t = state.current_trade
            t.exit_date   = date
            t.exit_price  = close
            t.exit_reason = "signal"
            gross_return  = (close / t.entry_price) - 1.0
            exit_cost     = state.account_value * POSITION * (COST_RT / 2)
            invested      = t.account_value_before * POSITION
            gain          = invested * gross_return
            t.pnl_pct     = (gross_return - COST_RT) * 100   # net
            t.hold_days   = _days_diff(t.entry_date, date)
            t.account_value_after = t.account_value_before + gain - exit_cost
            state.account_value   = t.account_value_after
            state.in_position     = False
            state.current_trade   = None
            state.trades.append(t)

        # Mark-to-market for equity curve (position valued at close)
        if state.in_position and state.current_trade:
            mtm_gain = (close / state.current_trade.entry_price - 1.0) \
                       * state.current_trade.account_value_before * POSITION
            equity_value = state.current_trade.account_value_before + mtm_gain
        else:
            equity_value = state.account_value

        equity_curve.append((date, equity_value))

    # Force-close open position at end of period
    if state.in_position and state.current_trade:
        t     = state.current_trade
        close = closes[-1]
        t.exit_date   = dates[-1]
        t.exit_price  = close
        t.exit_reason = "eod"
        gross_return  = (close / t.entry_price) - 1.0
        invested      = t.account_value_before * POSITION
        gain          = invested * gross_return
        exit_cost     = state.account_value * POSITION * (COST_RT / 2)
        t.pnl_pct     = (gross_return - COST_RT) * 100
        t.hold_days   = _days_diff(t.entry_date, t.exit_date)
        t.account_value_after = t.account_value_before + gain - exit_cost
        state.account_value   = t.account_value_after
        state.trades.append(t)
        equity_curve[-1] = (equity_curve[-1][0], state.account_value)

    return {
        "trades":        state.trades,
        "equity_curve":  equity_curve,
        "final_value":   state.account_value,
        "params": {
            "fast": fast_period,
            "slow": slow_period,
            "trailing_stop": trailing_stop,
        },
    }


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_metrics(result: Dict, initial_capital: float = 100_000.0) -> Dict:
    trades       = result["trades"]
    equity_curve = result["equity_curve"]
    final_value  = result["final_value"]

    if not equity_curve:
        return {}

    # Total return
    total_return = (final_value / initial_capital - 1.0) * 100

    # Annualised return
    dates = [e[0] for e in equity_curve]
    n_days = _days_diff(dates[0], dates[-1]) or 1
    ann_return = ((final_value / initial_capital) ** (365.25 / n_days) - 1.0) * 100

    # Max drawdown
    peak = initial_capital
    max_dd = 0.0
    for _, val in equity_curve:
        if val > peak:
            peak = val
        dd = (peak - val) / peak * 100
        if dd > max_dd:
            max_dd = dd

    # Win rate
    completed = [t for t in trades if t.pnl_pct is not None]
    wins = [t for t in completed if t.pnl_pct > 0]
    win_rate = (len(wins) / len(completed) * 100) if completed else 0.0

    # Avg hold time
    hold_times = [t.hold_days for t in completed if t.hold_days is not None]
    avg_hold = sum(hold_times) / len(hold_times) if hold_times else 0.0

    # Sharpe ratio (daily returns, annualised, rf=0)
    daily_rets = []
    prev_val = initial_capital
    for _, val in equity_curve:
        if prev_val and prev_val > 0:
            daily_rets.append((val - prev_val) / prev_val)
        prev_val = val
    sharpe = 0.0
    if len(daily_rets) > 1:
        avg_r = sum(daily_rets) / len(daily_rets)
        std_r = math.sqrt(sum((r - avg_r) ** 2 for r in daily_rets) / (len(daily_rets) - 1))
        sharpe = (avg_r / std_r * math.sqrt(252)) if std_r > 0 else 0.0

    return {
        "total_return":  round(total_return, 2),
        "ann_return":    round(ann_return, 2),
        "max_drawdown":  round(max_dd, 2),
        "win_rate":      round(win_rate, 2),
        "n_trades":      len(completed),
        "avg_hold_days": round(avg_hold, 1),
        "sharpe":        round(sharpe, 3),
    }


def yearly_returns(result: Dict, initial_capital: float = 100_000.0) -> Dict[str, float]:
    """Return % gain/loss by calendar year."""
    equity_curve = result["equity_curve"]
    if not equity_curve:
        return {}

    by_year: Dict[str, list] = {}
    for date, val in equity_curve:
        yr = date[:4]
        by_year.setdefault(yr, []).append(val)

    out: Dict[str, float] = {}
    prev_val = initial_capital
    for yr in sorted(by_year):
        first = by_year[yr][0]
        last  = by_year[yr][-1]
        ret   = (last / prev_val - 1.0) * 100
        out[yr] = round(ret, 2)
        prev_val = last
    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _days_diff(d1: str, d2: str) -> int:
    """Days between two ISO date strings."""
    from datetime import date
    a = date.fromisoformat(d1)
    b = date.fromisoformat(d2)
    return abs((b - a).days)
