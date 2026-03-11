#!/usr/bin/env python3
"""
kelly_sizing.py — Dynamic Position Sizing via Kelly Criterion + ATR

Implements three position sizing methods for the Pinch macro swing strategy:

1. Kelly Criterion: f* = (b·p - q) / b  (with fractional scaling)
2. ATR-based: size = target_risk / atr_pct  (volatility-normalized)
3. Combined: min(kelly_size, atr_size)  (conservative composite)

Usage:
    from strategies.kelly_sizing import kelly_position_size, atr_position_size, combined_sizing

Rule of Acquisition #22: A wise man can hear profit in the wind.
"""

import math
from typing import Optional


# Hard caps applied by all sizing methods
MAX_POSITION_SIZE = 0.30   # Never exceed 30% of account
MIN_POSITION_SIZE = 0.10   # Below 10%, skip the trade


def kelly_position_size(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    kelly_fraction: float = 0.5,
) -> float:
    """
    Compute Kelly-optimal position size as a fraction of account equity.

    Kelly formula: f* = (b·p - q) / b
    where:
        b = odds ratio = avg_win / abs(avg_loss)
        p = win probability (win_rate)
        q = 1 - p

    Args:
        win_rate:       Fraction of trades that are winners (0.0–1.0).
                        e.g. 0.70 for 70% win rate.
        avg_win:        Average return on winning trades (positive fraction).
                        e.g. 0.0725 for 7.25%.
        avg_loss:       Average return on losing trades (negative or positive fraction).
                        e.g. -0.084 for -8.4% loss (sign is handled automatically).
        kelly_fraction: Scaling factor applied to full Kelly.
                        0.5 = half Kelly (recommended), 0.25 = quarter Kelly.

    Returns:
        Position size as a fraction of account equity, clamped to [0, MAX_POSITION_SIZE].
        Returns 0.0 if there is no positive edge.

    Examples:
        >>> kelly_position_size(0.70, 0.0725, -0.084, kelly_fraction=0.5)
        0.17621...  # half Kelly ≈ 17.6%
        >>> kelly_position_size(0.70, 0.0725, -0.084, kelly_fraction=1.0)
        0.35243...  # full Kelly ≈ 35.2%
    """
    if win_rate <= 0.0 or win_rate >= 1.0:
        raise ValueError(f"win_rate must be in (0, 1), got {win_rate}")
    if avg_win <= 0.0:
        raise ValueError(f"avg_win must be positive, got {avg_win}")
    if kelly_fraction <= 0.0 or kelly_fraction > 1.0:
        raise ValueError(f"kelly_fraction must be in (0, 1], got {kelly_fraction}")

    # Normalize avg_loss to absolute magnitude
    abs_loss = abs(avg_loss)
    if abs_loss <= 0.0:
        raise ValueError(f"avg_loss must be non-zero, got {avg_loss}")

    # Odds ratio: how many units do we win per unit risked?
    b = avg_win / abs_loss

    p = win_rate
    q = 1.0 - p

    # Full Kelly fraction
    f_star = (b * p - q) / b

    if f_star <= 0.0:
        # No positive edge — do not trade
        return 0.0

    # Apply fractional Kelly and cap
    size = f_star * kelly_fraction
    return min(size, MAX_POSITION_SIZE)


def atr_position_size(
    atr: float,
    account_value: float,
    risk_per_trade: float = 0.02,
    price: Optional[float] = None,
) -> float:
    """
    Compute ATR-based position size that targets a fixed dollar risk per trade.

    Formula:
        atr_pct = atr / price  (if price given)  OR  atr treated as already a fraction
        position_size = risk_per_trade / atr_pct

    Intuition: If BTC has a 20-day ATR of 4% and we want to risk 2% of account,
    we size so that a 1-ATR move against us costs 2%.

    Args:
        atr:            Average True Range over N days.
                        If `price` is provided: raw price units (e.g. $3,000 for BTC).
                        If `price` is None: atr is treated as a fraction (e.g. 0.04 for 4%).
        account_value:  Current account equity in dollars (used for validation only).
        risk_per_trade: Target fraction of account to risk per trade.
                        Default 0.02 = 2% risk per trade.
        price:          Current asset price in dollars. Used to convert raw ATR to %.
                        If None, `atr` is assumed to already be a percentage fraction.

    Returns:
        Position size as a fraction of account equity, clamped to [0, MAX_POSITION_SIZE].
        Returns 0.0 if ATR is zero or undefined.

    Examples:
        >>> atr_position_size(atr=0.04, account_value=100000)
        0.30  # capped: 0.02/0.04 = 0.50 → clamped to MAX
        >>> atr_position_size(atr=2400, account_value=100000, price=60000)
        0.30  # atr_pct = 2400/60000 = 4% → same result
        >>> atr_position_size(atr=0.10, account_value=100000)
        0.20  # 0.02 / 0.10 = 0.20
    """
    if account_value <= 0:
        raise ValueError(f"account_value must be positive, got {account_value}")
    if risk_per_trade <= 0.0 or risk_per_trade > 0.25:
        raise ValueError(f"risk_per_trade must be in (0, 0.25], got {risk_per_trade}")

    # Convert raw ATR to fraction if price provided
    if price is not None:
        if price <= 0:
            raise ValueError(f"price must be positive, got {price}")
        atr_pct = atr / price
    else:
        atr_pct = atr

    if atr_pct <= 0.0:
        return 0.0

    # Size to risk exactly risk_per_trade of account per 1-ATR move
    size = risk_per_trade / atr_pct

    return min(size, MAX_POSITION_SIZE)


def combined_sizing(
    kelly_size: float,
    atr_size: float,
    min_size: float = MIN_POSITION_SIZE,
) -> float:
    """
    Combine Kelly and ATR sizing by taking the minimum (conservative composite).

    Rationale:
    - Kelly size: calibrated to our edge (win rate + payoff ratio)
    - ATR size: calibrated to current market volatility
    - Minimum of both: never over-bet relative to either risk model

    Args:
        kelly_size: Position fraction from kelly_position_size().
        atr_size:   Position fraction from atr_position_size().
        min_size:   Minimum viable position; if combined < this, return 0 (skip trade).
                    Default MIN_POSITION_SIZE = 10%.

    Returns:
        Combined position fraction, or 0.0 if below min_size threshold.

    Examples:
        >>> combined_sizing(0.176, 0.50)
        0.176  # Kelly is binding
        >>> combined_sizing(0.176, 0.12)
        0.12   # ATR is binding (high volatility)
        >>> combined_sizing(0.176, 0.08)
        0.0    # Below minimum — skip trade
    """
    if kelly_size < 0.0 or atr_size < 0.0:
        return 0.0

    size = min(kelly_size, atr_size)

    if size < min_size:
        return 0.0

    return min(size, MAX_POSITION_SIZE)


def compute_kelly_full(win_rate: float, avg_win: float, avg_loss: float) -> dict:
    """
    Compute full Kelly statistics for reporting/logging.

    Returns a dict with:
        b, p, q, f_star, half_kelly, quarter_kelly, edge
    """
    abs_loss = abs(avg_loss)
    b = avg_win / abs_loss if abs_loss > 0 else 0.0
    p = win_rate
    q = 1.0 - p
    f_star = max(0.0, (b * p - q) / b) if b > 0 else 0.0
    edge = b * p - q  # Expected value per unit risked

    return {
        "b": b,
        "p": p,
        "q": q,
        "f_star": f_star,
        "half_kelly": f_star * 0.5,
        "quarter_kelly": f_star * 0.25,
        "edge": edge,
    }


def compute_atr(highs: list, lows: list, closes: list, period: int = 20) -> list:
    """
    Compute N-period Average True Range from OHLC lists.

    True Range = max(High - Low, |High - PrevClose|, |Low - PrevClose|)
    ATR = simple moving average of True Range over `period` bars.

    Args:
        highs:   List of daily high prices.
        lows:    List of daily low prices.
        closes:  List of daily close prices.
        period:  Lookback period in days. Default 20.

    Returns:
        List of ATR values (same length as input; first `period` values may be None).
    """
    n = len(closes)
    if n != len(highs) or n != len(lows):
        raise ValueError("highs, lows, closes must have equal length")

    true_ranges = []
    for i in range(n):
        if i == 0:
            tr = highs[i] - lows[i]
        else:
            prev_close = closes[i - 1]
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - prev_close),
                abs(lows[i] - prev_close),
            )
        true_ranges.append(tr)

    atrs = []
    for i in range(n):
        if i < period - 1:
            atrs.append(None)
        else:
            window = true_ranges[i - period + 1 : i + 1]
            atrs.append(sum(window) / period)

    return atrs


# ---------------------------------------------------------------------------
# Quick sanity-check / demo
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 55)
    print("KELLY SIZING — Strategy Parameters")
    print("=" * 55)

    # Backtest priors from macro_swing_results.md
    WIN_RATE = 0.70
    AVG_WIN  = 0.0725   # +7.25%
    AVG_LOSS = -0.084   # -8.40%

    stats = compute_kelly_full(WIN_RATE, AVG_WIN, AVG_LOSS)
    print(f"Win Rate:          {WIN_RATE:.1%}")
    print(f"Avg Win:           {AVG_WIN:.2%}")
    print(f"Avg Loss:          {AVG_LOSS:.2%}")
    print(f"Odds ratio (b):    {stats['b']:.4f}")
    print(f"Edge per unit:     {stats['edge']:.4f}")
    print()
    print(f"Full Kelly:        {stats['f_star']:.4f} = {stats['f_star']:.2%}")
    print(f"Half Kelly:        {stats['half_kelly']:.4f} = {stats['half_kelly']:.2%}")
    print(f"Quarter Kelly:     {stats['quarter_kelly']:.4f} = {stats['quarter_kelly']:.2%}")
    print()

    # ATR example
    atr_pct = 0.04   # 4% ATR (typical BTC)
    atr_sz = atr_position_size(atr=atr_pct, account_value=100_000)
    half_k = kelly_position_size(WIN_RATE, AVG_WIN, AVG_LOSS, kelly_fraction=0.5)
    combo  = combined_sizing(half_k, atr_sz)
    print(f"ATR sizing (4% ATR, 2% risk): {atr_sz:.2%} → capped at {MAX_POSITION_SIZE:.0%}")
    print(f"Combined (min of both):       {combo:.2%}")
    print()
    print("Rule of Acquisition #22: A wise man can hear profit in the wind.")
