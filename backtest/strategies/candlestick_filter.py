#!/usr/bin/env python3
"""
candlestick_filter.py — Bullish Candlestick Pattern Detection

Detects the following patterns on daily BTC candles:
  - Bullish Engulfing
  - Hammer
  - Morning Star (3-candle)
  - Doji

Usage:
    from strategies.candlestick_filter import detect_patterns, is_bullish_confirmation
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Candle:
    date: str
    open: float
    high: float
    low: float
    close: float

    @property
    def body(self) -> float:
        """Absolute size of candle body."""
        return abs(self.close - self.open)

    @property
    def total_range(self) -> float:
        """Full high-low range."""
        return self.high - self.low

    @property
    def upper_shadow(self) -> float:
        """Distance from body top to high."""
        return self.high - max(self.open, self.close)

    @property
    def lower_shadow(self) -> float:
        """Distance from body bottom to low."""
        return min(self.open, self.close) - self.low

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        return self.close < self.open


@dataclass
class PatternResult:
    date: str
    bullish_engulfing: bool = False
    hammer: bool = False
    morning_star: bool = False
    doji: bool = False

    @property
    def any_bullish(self) -> bool:
        """True if any bullish confirmation pattern is detected."""
        return self.bullish_engulfing or self.hammer or self.morning_star

    @property
    def pattern_names(self) -> list[str]:
        names = []
        if self.bullish_engulfing:
            names.append("bullish_engulfing")
        if self.hammer:
            names.append("hammer")
        if self.morning_star:
            names.append("morning_star")
        if self.doji:
            names.append("doji")
        return names

    def __str__(self) -> str:
        names = self.pattern_names
        return f"[{', '.join(names)}]" if names else "[none]"


# ---------------------------------------------------------------------------
# Individual pattern detectors
# ---------------------------------------------------------------------------

def is_bullish_engulfing(curr: Candle, prev: Candle) -> bool:
    """
    Bullish Engulfing:
      - Current close > prior open  (engulfs the prior candle top)
      - Current open < prior close  (opens below prior close)
      - Current body > prior body   (larger candle)
    The current candle must be bullish (close > open).
    """
    if not curr.is_bullish:
        return False
    body_engulfs = (curr.close > prev.open) and (curr.open < prev.close)
    bigger_body = curr.body > prev.body
    return body_engulfs and bigger_body


def is_hammer(candle: Candle, body_threshold: float = 2.0) -> bool:
    """
    Hammer:
      - Long lower shadow: lower_shadow > body_threshold * body
      - Small body (not a doji — body must exist)
      - Upper shadow < body
    Must have a non-zero body.
    """
    if candle.body == 0:
        return False
    long_lower = candle.lower_shadow > body_threshold * candle.body
    small_upper = candle.upper_shadow < candle.body
    return long_lower and small_upper


def is_morning_star(c1: Candle, c2: Candle, c3: Candle,
                    small_body_pct: float = 0.30,
                    big_body_pct: float = 0.50) -> bool:
    """
    Morning Star (3-candle reversal):
      c1: Large bearish (red) candle — body > big_body_pct of its range
      c2: Small body (doji-like) — body < small_body_pct of c1's body
      c3: Large bullish (green) candle — body > big_body_pct of its range,
          closes above midpoint of c1's body
    """
    if not c1.is_bearish:
        return False
    if c1.total_range == 0:
        return False

    c1_big = c1.body > big_body_pct * c1.total_range
    c2_small = c2.body < small_body_pct * c1.body if c1.body > 0 else False
    c3_big = c3.is_bullish and (c3.body > big_body_pct * c3.total_range if c3.total_range > 0 else False)

    # c3 must close above the midpoint of c1's body
    c1_midpoint = (c1.open + c1.close) / 2.0
    c3_recovers = c3.close > c1_midpoint

    return c1_big and c2_small and c3_big and c3_recovers


def is_doji(candle: Candle, body_pct: float = 0.10) -> bool:
    """
    Doji: body < body_pct (10%) of total high-low range.
    """
    if candle.total_range == 0:
        return False
    return candle.body < body_pct * candle.total_range


# ---------------------------------------------------------------------------
# Multi-candle scanner
# ---------------------------------------------------------------------------

def detect_patterns(candles: list[Candle]) -> list[PatternResult]:
    """
    Detect all patterns across a list of Candle objects.
    Returns one PatternResult per candle (indexed to candles[i]).
    Single-candle patterns use candles[i] and candles[i-1].
    Morning star uses candles[i-2], candles[i-1], candles[i].
    """
    results = []
    for i, candle in enumerate(candles):
        result = PatternResult(date=candle.date)

        # Doji — single candle
        result.doji = is_doji(candle)

        # Hammer — single candle
        result.hammer = is_hammer(candle)

        # Bullish Engulfing — needs prior candle
        if i >= 1:
            result.bullish_engulfing = is_bullish_engulfing(candle, candles[i - 1])

        # Morning Star — needs 2 prior candles
        if i >= 2:
            result.morning_star = is_morning_star(candles[i - 2], candles[i - 1], candle)

        results.append(result)

    return results


def candles_from_price_data(price_data: dict, dates: list[str]) -> list[Candle]:
    """Convert price_data dict (date → OHLCV) to list of Candle objects for given dates."""
    candles = []
    for d in sorted(dates):
        if d in price_data:
            bar = price_data[d]
            candles.append(Candle(
                date=d,
                open=bar["open"],
                high=bar["high"],
                low=bar["low"],
                close=bar["close"],
            ))
    return candles


def is_bullish_confirmation(date: str, price_data: dict, all_dates: list[str]) -> tuple[bool, PatternResult]:
    """
    Check if there's a bullish confirmation pattern on `date`.
    Needs up to 2 prior days for morning star.
    Returns (confirmed: bool, pattern_result: PatternResult).
    """
    # Grab this date and 2 prior trading days
    idx = all_dates.index(date) if date in all_dates else -1
    if idx < 0:
        empty = PatternResult(date=date)
        return False, empty

    start_idx = max(0, idx - 2)
    window_dates = all_dates[start_idx: idx + 1]
    candles = candles_from_price_data(price_data, window_dates)

    if not candles:
        empty = PatternResult(date=date)
        return False, empty

    pattern_results = detect_patterns(candles)
    current_result = pattern_results[-1]

    # Bullish confirmation = engulfing, hammer, or morning star (doji alone is neutral)
    confirmed = current_result.any_bullish
    return confirmed, current_result
