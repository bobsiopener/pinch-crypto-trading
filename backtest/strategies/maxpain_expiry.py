"""
Max Pain Expiry Strategy for BTC

Two sub-strategies:
  Trade 1: Expiry Week Magnet — price drifts toward max pain during expiry week
  Trade 2: Post-Expiry Mean Reversion — price snaps back after expiry pin

Quarterly expiry boost: 2x position size in Mar/Jun/Sep/Dec.
"""

from dataclasses import dataclass, field
from typing import Optional, List
from datetime import date as DateType


@dataclass
class Trade:
    trade_id: int
    trade_type: str          # 'expiry_week' or 'post_expiry'
    direction: str           # 'long' or 'short'
    entry_date: DateType
    entry_price: float
    position_size_pct: float # fraction of account (0.15 = 15%)
    stop_loss_pct: float
    take_profit_target: float  # absolute price level
    exit_date: Optional[DateType] = None
    exit_price: Optional[float] = None
    exit_reason: str = ''
    pnl_pct: float = 0.0     # % return on account (position-sized)
    is_quarterly: bool = False
    max_pain: float = 0.0

    def is_open(self):
        return self.exit_date is None

    def close(self, exit_date, exit_price, reason):
        self.exit_date = exit_date
        self.exit_price = exit_price
        self.exit_reason = reason
        # P&L as % of total account (not just position)
        if self.direction == 'long':
            raw_return = (exit_price - self.entry_price) / self.entry_price
        else:
            raw_return = (self.entry_price - exit_price) / self.entry_price
        self.pnl_pct = raw_return * self.position_size_pct


class MaxPainExpiryStrategy:
    """
    Standalone Max Pain Expiry Strategy.

    Call process_day() for each trading day in chronological order.
    Strategy tracks account equity as a multiplier (starts at 1.0).
    """

    def __init__(self, initial_capital: float = 100_000.0):
        self.initial_capital = initial_capital
        self.equity_multiplier = 1.0      # grows/shrinks with trades
        self.trades: List[Trade] = []
        self._trade_counter = 0

        # State tracking
        self._open_expiry_trade: Optional[Trade] = None
        self._open_postreversion_trade: Optional[Trade] = None

        # For post-expiry logic: remember last expiry result
        self._last_expiry_direction: Optional[str] = None   # 'down' or 'up'
        self._last_expiry_hit_max_pain: bool = False

        # Day counter within expiry week (for time-stop logic)
        self._expiry_week_entry_date: Optional[DateType] = None
        self._current_expiry_friday: Optional[DateType] = None

    def _next_id(self):
        self._trade_counter += 1
        return self._trade_counter

    def process_day(self,
                    date: DateType,
                    open_: float,
                    high: float,
                    low: float,
                    close: float,
                    max_pain: float,
                    is_expiry_week: bool,
                    days_to_expiry: int,       # negative = days before expiry Friday
                    is_quarterly: bool,
                    is_post_expiry_monday: bool,
                    expiry_friday: Optional[DateType] = None):
        """
        Process a single trading day through the strategy.

        days_to_expiry: 0 = expiry Friday, -1 = Thursday before, -4 = Monday
        is_post_expiry_monday: True if this is the Monday after expiry Friday
        """
        events = []  # log of what happened today

        # ── 1. Manage open POST-EXPIRY trade ──────────────────────────────────
        if self._open_postreversion_trade and self._open_postreversion_trade.is_open():
            t = self._open_postreversion_trade
            # Check stop loss (use intraday low/high)
            stopped = False
            if t.direction == 'long':
                sl_price = t.entry_price * (1 - t.stop_loss_pct)
                if low <= sl_price:
                    t.close(date, sl_price, 'stop_loss')
                    self.equity_multiplier *= (1 + t.pnl_pct)
                    events.append(f"POST-EXPIRY {t.direction.upper()} STOP LOSS @ {sl_price:.0f}")
                    self._open_postreversion_trade = None
                    stopped = True
            else:
                sl_price = t.entry_price * (1 + t.stop_loss_pct)
                if high >= sl_price:
                    t.close(date, sl_price, 'stop_loss')
                    self.equity_multiplier *= (1 + t.pnl_pct)
                    events.append(f"POST-EXPIRY {t.direction.upper()} STOP LOSS @ {sl_price:.0f}")
                    self._open_postreversion_trade = None
                    stopped = True

            if not stopped:
                # Check take profit (3% move)
                if t.direction == 'long':
                    tp_price = t.entry_price * (1 + 0.03)
                    if high >= tp_price:
                        t.close(date, tp_price, 'take_profit')
                        self.equity_multiplier *= (1 + t.pnl_pct)
                        events.append(f"POST-EXPIRY {t.direction.upper()} TAKE PROFIT @ {tp_price:.0f}")
                        self._open_postreversion_trade = None
                        stopped = True
                else:
                    tp_price = t.entry_price * (1 - 0.03)
                    if low <= tp_price:
                        t.close(date, tp_price, 'take_profit')
                        self.equity_multiplier *= (1 + t.pnl_pct)
                        events.append(f"POST-EXPIRY {t.direction.upper()} TAKE PROFIT @ {tp_price:.0f}")
                        self._open_postreversion_trade = None
                        stopped = True

            # Time stop: Wednesday close (2-day hold max from Monday entry)
            if not stopped and self._open_postreversion_trade:
                entry = t.entry_date
                # Close on Wednesday (entry_date + 2 days) or later
                wednesday = entry + __import__('datetime').timedelta(days=2)
                if date >= wednesday:
                    t.close(date, close, 'time_stop_wednesday')
                    self.equity_multiplier *= (1 + t.pnl_pct)
                    events.append(f"POST-EXPIRY {t.direction.upper()} TIME STOP (Wed) @ {close:.0f}")
                    self._open_postreversion_trade = None

        # ── 2. Manage open EXPIRY WEEK trade ─────────────────────────────────
        if self._open_expiry_trade and self._open_expiry_trade.is_open():
            t = self._open_expiry_trade
            stopped = False

            # Stop loss check (intraday)
            if t.direction == 'long':
                sl_price = t.entry_price * (1 - t.stop_loss_pct)
                if low <= sl_price:
                    t.close(date, sl_price, 'stop_loss')
                    self.equity_multiplier *= (1 + t.pnl_pct)
                    events.append(f"EXPIRY {t.direction.upper()} STOP LOSS @ {sl_price:.0f}")
                    self._open_expiry_trade = None
                    stopped = True
                    self._last_expiry_hit_max_pain = False
                    self._last_expiry_direction = t.direction  # was going up, got stopped
            else:
                sl_price = t.entry_price * (1 + t.stop_loss_pct)
                if high >= sl_price:
                    t.close(date, sl_price, 'stop_loss')
                    self.equity_multiplier *= (1 + t.pnl_pct)
                    events.append(f"EXPIRY {t.direction.upper()} STOP LOSS @ {sl_price:.0f}")
                    self._open_expiry_trade = None
                    stopped = True
                    self._last_expiry_hit_max_pain = False
                    self._last_expiry_direction = t.direction

            if not stopped:
                # Take profit: price within 1% of max pain
                hit_max_pain = abs(close - t.max_pain) / t.max_pain <= 0.01
                if hit_max_pain:
                    t.close(date, close, 'take_profit_max_pain')
                    self.equity_multiplier *= (1 + t.pnl_pct)
                    events.append(f"EXPIRY {t.direction.upper()} TP (near max pain) @ {close:.0f}")
                    self._last_expiry_hit_max_pain = True
                    self._last_expiry_direction = 'down' if t.direction == 'short' else 'up'
                    self._open_expiry_trade = None
                    stopped = True

            # Time stop: Friday close (days_to_expiry == 0)
            if not stopped and self._open_expiry_trade and days_to_expiry == 0:
                t.close(date, close, 'time_stop_friday')
                self.equity_multiplier *= (1 + t.pnl_pct)
                events.append(f"EXPIRY {t.direction.upper()} TIME STOP (Fri expiry) @ {close:.0f}")
                # Did it hit max pain at expiry?
                hit_at_expiry = abs(close - t.max_pain) / t.max_pain <= 0.03
                self._last_expiry_hit_max_pain = hit_at_expiry
                self._last_expiry_direction = 'down' if t.direction == 'short' else 'up'
                self._open_expiry_trade = None

        # ── 3. Entry: EXPIRY WEEK (Monday, days_to_expiry == -4) ─────────────
        if (days_to_expiry == -4 and is_expiry_week and
                self._open_expiry_trade is None):
            gap_pct = (close - max_pain) / close  # positive = max pain below spot

            pos_size = 0.30 if is_quarterly else 0.15
            sl_pct = 0.05

            direction = None
            if gap_pct > 0.03:
                direction = 'short'  # max pain below → price should drift down
            elif gap_pct < -0.03:
                direction = 'long'   # max pain above → price should drift up

            if direction:
                self._current_expiry_friday = expiry_friday
                t = Trade(
                    trade_id=self._next_id(),
                    trade_type='expiry_week',
                    direction=direction,
                    entry_date=date,
                    entry_price=close,
                    position_size_pct=pos_size,
                    stop_loss_pct=sl_pct,
                    take_profit_target=max_pain,
                    is_quarterly=is_quarterly,
                    max_pain=max_pain,
                )
                self._open_expiry_trade = t
                self.trades.append(t)
                events.append(f"ENTRY EXPIRY {'QUARTERLY' if is_quarterly else 'MONTHLY'} "
                              f"{direction.upper()} @ {close:.0f} "
                              f"(max_pain={max_pain:.0f}, gap={gap_pct*100:.1f}%)")

        # ── 4. Entry: POST-EXPIRY MONDAY ──────────────────────────────────────
        if (is_post_expiry_monday and
                self._last_expiry_hit_max_pain and
                self._last_expiry_direction is not None and
                self._open_postreversion_trade is None and
                self._open_expiry_trade is None):

            # Opposite direction to expiry drift
            direction = 'long' if self._last_expiry_direction == 'down' else 'short'
            pos_size = 0.20 if is_quarterly else 0.10
            sl_pct = 0.04
            tp_target = (close * 1.03 if direction == 'long' else close * 0.97)

            t = Trade(
                trade_id=self._next_id(),
                trade_type='post_expiry',
                direction=direction,
                entry_date=date,
                entry_price=close,
                position_size_pct=pos_size,
                stop_loss_pct=sl_pct,
                take_profit_target=tp_target,
                is_quarterly=is_quarterly,
                max_pain=max_pain,
            )
            self._open_postreversion_trade = t
            self.trades.append(t)
            events.append(f"ENTRY POST-EXPIRY {'QUARTERLY' if is_quarterly else 'MONTHLY'} "
                          f"{direction.upper()} @ {close:.0f}")

            # Reset
            self._last_expiry_hit_max_pain = False
            self._last_expiry_direction = None

        return events

    # ── Analytics ─────────────────────────────────────────────────────────────

    def closed_trades(self):
        return [t for t in self.trades if not t.is_open()]

    def open_trades(self):
        return [t for t in self.trades if t.is_open()]

    def summary_stats(self):
        closed = self.closed_trades()
        if not closed:
            return {}

        total_pnl = sum(t.pnl_pct for t in closed)
        wins = [t for t in closed if t.pnl_pct > 0]
        losses = [t for t in closed if t.pnl_pct <= 0]

        expiry_trades = [t for t in closed if t.trade_type == 'expiry_week']
        post_trades = [t for t in closed if t.trade_type == 'post_expiry']
        quarterly = [t for t in closed if t.is_quarterly]
        monthly = [t for t in closed if not t.is_quarterly]

        def sub_stats(tlist):
            if not tlist:
                return {'count': 0, 'win_rate': 0, 'total_pnl_pct': 0, 'avg_pnl_pct': 0}
            w = [t for t in tlist if t.pnl_pct > 0]
            return {
                'count': len(tlist),
                'win_rate': len(w) / len(tlist),
                'total_pnl_pct': sum(t.pnl_pct for t in tlist),
                'avg_pnl_pct': sum(t.pnl_pct for t in tlist) / len(tlist),
            }

        return {
            'total_trades': len(closed),
            'win_rate': len(wins) / len(closed),
            'total_pnl_pct': total_pnl,
            'avg_pnl_per_trade': total_pnl / len(closed),
            'best_trade': max(t.pnl_pct for t in closed),
            'worst_trade': min(t.pnl_pct for t in closed),
            'expiry_week': sub_stats(expiry_trades),
            'post_expiry': sub_stats(post_trades),
            'quarterly': sub_stats(quarterly),
            'monthly': sub_stats(monthly),
        }
