#!/usr/bin/env python3
"""
grid_trading.py — Grid Trading Strategy Engine for ETH

Strategy: Place buy orders below and sell orders above current price at fixed grid intervals.
When a buy fills → create corresponding sell one level above.
When a sell fills → create corresponding buy one level below.
Tracks realized P&L from completed buy-sell pairs plus unrealized position value.
"""

import csv
import math
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

INITIAL_ACCOUNT    = 100_000.0   # total account size
GRID_ALLOCATION    = 0.50        # 50% allocated to grid trading
GRID_CAPITAL       = INITIAL_ACCOUNT * GRID_ALLOCATION   # $50,000
GRID_LEVELS        = 10          # levels above and below center
FEE_RATE           = 0.001       # 0.1% taker fee per side


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class GridOrder:
    level_index: int          # signed: negative = below center, positive = above
    price: float
    side: str                 # 'buy' or 'sell'
    qty_eth: float
    filled: bool = False
    fill_date: Optional[str] = None


@dataclass
class GridCycle:
    """A completed buy-sell pair."""
    buy_date: str
    buy_price: float
    sell_date: str
    sell_price: float
    qty_eth: float
    gross_profit: float
    fees: float
    net_profit: float


@dataclass
class GridState:
    grid_spacing: float
    center_price: float
    cash: float                            # remaining cash (not in grid)
    grid_cash: float                       # cash reserved for buy orders
    eth_inventory: float = 0.0            # ETH held from filled buys
    eth_avg_cost: float = 0.0            # weighted avg cost of inventory
    realized_pnl: float = 0.0
    total_fees: float = 0.0
    cycles: list = field(default_factory=list)          # GridCycle list
    active_orders: list = field(default_factory=list)   # GridOrder list
    # tracking
    account_values: list = field(default_factory=list)  # (date, value) tuples
    fill_log: list = field(default_factory=list)        # (date, side, price, qty)
    monthly_fills: dict = field(default_factory=dict)   # ym -> count
    monthly_pnl: dict = field(default_factory=dict)     # ym -> net_pnl


# ---------------------------------------------------------------------------
# Grid initialization
# ---------------------------------------------------------------------------

def _qty_per_level(center_price: float, grid_spacing: float,
                   grid_capital: float, levels: int) -> float:
    """
    Divide grid capital equally across buy levels.
    qty = (capital / levels) / price_of_each_level.
    We use center price as a proxy for level prices (close enough for setup).
    """
    capital_per_level = grid_capital / levels
    return capital_per_level / center_price


def initialize_grid(center_price: float, grid_spacing: float) -> GridState:
    """Set up the grid around the given center price."""
    qty = _qty_per_level(center_price, grid_spacing, GRID_CAPITAL, GRID_LEVELS)

    # Cash allocated per buy level
    cash_per_level = GRID_CAPITAL / GRID_LEVELS

    state = GridState(
        grid_spacing=grid_spacing,
        center_price=center_price,
        cash=INITIAL_ACCOUNT - GRID_CAPITAL,   # non-grid cash
        grid_cash=GRID_CAPITAL,                # available for buys
    )

    # Place buy orders below center (levels -1 .. -GRID_LEVELS)
    for i in range(1, GRID_LEVELS + 1):
        price = center_price - i * grid_spacing
        if price <= 0:
            continue
        order = GridOrder(
            level_index=-i,
            price=round(price, 2),
            side='buy',
            qty_eth=qty,
        )
        state.active_orders.append(order)

    # Place sell orders above center (levels +1 .. +GRID_LEVELS)
    # These are "hypothetical" — they only fill if we already own ETH.
    # At init we have no ETH, so we skip initial sell orders.
    # (Sell orders are created dynamically when buys fill.)

    return state


# ---------------------------------------------------------------------------
# Daily simulation step
# ---------------------------------------------------------------------------

def _month_key(date_str: str) -> str:
    return date_str[:7]   # "2022-01"


def simulate_day(state: GridState, date_str: str,
                 day_open: float, day_high: float,
                 day_low: float, day_close: float) -> None:
    """
    Process a single trading day:
    - Check if LOW reached any buy order price → fill buy(s)
    - Check if HIGH reached any sell order price → fill sell(s)
    - Update account value snapshot.

    Multiple fills can happen in one day (day_high/low can span several levels).
    We process buys and sells independently (both directions can happen intraday).
    """
    ym = _month_key(date_str)

    # --- Process BUY fills (price dropped to buy level) ---
    for order in list(state.active_orders):
        if order.side != 'buy':
            continue
        if day_low <= order.price:
            _fill_buy(state, order, date_str, ym)

    # --- Process SELL fills (price rose to sell level) ---
    for order in list(state.active_orders):
        if order.side != 'sell':
            continue
        if day_high >= order.price:
            _fill_sell(state, order, date_str, ym)

    # --- Account value snapshot ---
    unrealized = state.eth_inventory * day_close
    total_value = state.cash + state.grid_cash + unrealized + state.realized_pnl
    state.account_values.append((date_str, total_value))


def _fill_buy(state: GridState, order: GridOrder,
              date_str: str, ym: str) -> None:
    """Fill a buy order and place a corresponding sell one level above."""
    cost = order.price * order.qty_eth
    fee  = cost * FEE_RATE

    if state.grid_cash < cost + fee:
        return   # insufficient capital, skip

    # Deduct cash
    state.grid_cash -= (cost + fee)
    state.total_fees += fee

    # Add ETH inventory (weighted avg cost)
    total_cost = state.eth_inventory * state.eth_avg_cost + cost
    state.eth_inventory += order.qty_eth
    state.eth_avg_cost = total_cost / state.eth_inventory if state.eth_inventory > 0 else 0

    order.filled = True
    order.fill_date = date_str
    state.active_orders.remove(order)

    # Log fill
    state.fill_log.append((date_str, 'buy', order.price, order.qty_eth))
    state.monthly_fills[ym] = state.monthly_fills.get(ym, 0) + 1

    # Place corresponding sell one level above
    sell_price = round(order.price + state.grid_spacing, 2)
    sell_order = GridOrder(
        level_index=order.level_index + 1,
        price=sell_price,
        side='sell',
        qty_eth=order.qty_eth,
    )
    # Attach the buy info for P&L tracking
    sell_order._buy_price = order.price   # type: ignore[attr-defined]
    state.active_orders.append(sell_order)


def _fill_sell(state: GridState, order: GridOrder,
               date_str: str, ym: str) -> None:
    """Fill a sell order, book profit, and place a buy one level below."""
    gross = order.price * order.qty_eth
    fee   = gross * FEE_RATE

    buy_price = getattr(order, '_buy_price', order.price - state.grid_spacing)
    buy_cost  = buy_price * order.qty_eth
    buy_fee   = buy_cost * FEE_RATE

    net_profit = gross - fee - buy_cost - buy_fee
    state.realized_pnl += net_profit
    state.total_fees   += fee

    # Return cash from sold ETH
    state.grid_cash += gross - fee

    # Reduce ETH inventory
    state.eth_inventory = max(0.0, state.eth_inventory - order.qty_eth)
    if state.eth_inventory <= 0:
        state.eth_avg_cost = 0.0

    order.filled = True
    order.fill_date = date_str
    state.active_orders.remove(order)

    # Record completed cycle
    cycle = GridCycle(
        buy_date=order.fill_date or date_str,
        buy_price=buy_price,
        sell_date=date_str,
        sell_price=order.price,
        qty_eth=order.qty_eth,
        gross_profit=gross - buy_cost,
        fees=fee + buy_fee,
        net_profit=net_profit,
    )
    state.cycles.append(cycle)
    state.monthly_pnl[ym] = state.monthly_pnl.get(ym, 0.0) + net_profit

    # Log fill
    state.fill_log.append((date_str, 'sell', order.price, order.qty_eth))
    state.monthly_fills[ym] = state.monthly_fills.get(ym, 0) + 1

    # Place corresponding buy one level below
    buy_back_price = round(order.price - state.grid_spacing, 2)
    if buy_back_price > 0:
        new_buy = GridOrder(
            level_index=order.level_index - 1,
            price=buy_back_price,
            side='buy',
            qty_eth=order.qty_eth,
        )
        state.active_orders.append(new_buy)


# ---------------------------------------------------------------------------
# Metrics calculation
# ---------------------------------------------------------------------------

def compute_metrics(state: GridState, start_price: float,
                    end_price: float, start_date: str, end_date: str) -> dict:
    """
    Compute summary metrics for a completed backtest run.
    """
    # Final account value
    final_unrealized = state.eth_inventory * end_price
    final_value = (state.cash + state.grid_cash + final_unrealized
                   + state.realized_pnl)

    total_return_pct = (final_value - INITIAL_ACCOUNT) / INITIAL_ACCOUNT * 100

    # Annualize
    from datetime import date as _date
    d0 = _date.fromisoformat(start_date)
    d1 = _date.fromisoformat(end_date)
    years = (d1 - d0).days / 365.25
    if years > 0 and final_value > 0:
        annualized_return = ((final_value / INITIAL_ACCOUNT) ** (1 / years) - 1) * 100
    else:
        annualized_return = 0.0

    # Max drawdown
    peak = INITIAL_ACCOUNT
    max_dd = 0.0
    for _, val in state.account_values:
        if val > peak:
            peak = val
        dd = (peak - val) / peak * 100
        if dd > max_dd:
            max_dd = dd

    # Monthly fills stats
    all_months = sorted(state.monthly_fills.keys())
    avg_fills = (sum(state.monthly_fills.values()) / len(all_months)
                 if all_months else 0)

    # Best/worst month by P&L
    best_month = max(state.monthly_pnl.items(), key=lambda x: x[1]) if state.monthly_pnl else ("N/A", 0)
    worst_month = min(state.monthly_pnl.items(), key=lambda x: x[1]) if state.monthly_pnl else ("N/A", 0)

    # Buy & hold comparison
    hold_shares = INITIAL_ACCOUNT / start_price
    hold_value = hold_shares * end_price
    hold_return = (hold_value - INITIAL_ACCOUNT) / INITIAL_ACCOUNT * 100

    return {
        "grid_spacing": state.grid_spacing,
        "start_price": start_price,
        "end_price": end_price,
        "final_account_value": final_value,
        "realized_pnl": state.realized_pnl,
        "unrealized_pnl": final_unrealized - (state.eth_inventory * start_price) if state.eth_inventory > 0 else 0,
        "total_fees": state.total_fees,
        "total_return_pct": total_return_pct,
        "annualized_return_pct": annualized_return,
        "max_drawdown_pct": max_dd,
        "num_cycles": len(state.cycles),
        "num_buy_fills": sum(1 for _, s, _, _ in state.fill_log if s == 'buy'),
        "num_sell_fills": sum(1 for _, s, _, _ in state.fill_log if s == 'sell'),
        "avg_fills_per_month": avg_fills,
        "best_month": best_month[0],
        "best_month_pnl": best_month[1],
        "worst_month": worst_month[0],
        "worst_month_pnl": worst_month[1],
        "eth_inventory_remaining": state.eth_inventory,
        "grid_cash_remaining": state.grid_cash,
        "hold_return_pct": hold_return,
        "hold_final_value": hold_value,
        "profit_per_cycle": state.realized_pnl / len(state.cycles) if state.cycles else 0,
    }


# ---------------------------------------------------------------------------
# CSV loader
# ---------------------------------------------------------------------------

def load_eth_data(filepath: str, start_date: str, end_date: str) -> list:
    """Load ETH OHLCV rows filtered to [start_date, end_date] inclusive."""
    rows = []
    with open(filepath, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            d = row.get('date') or row.get('Date')
            if d and start_date <= d <= end_date:
                rows.append({
                    'date': d,
                    'open':  float(row.get('open')  or row.get('Open')),
                    'high':  float(row.get('high')  or row.get('High')),
                    'low':   float(row.get('low')   or row.get('Low')),
                    'close': float(row.get('close') or row.get('Close')),
                })
    rows.sort(key=lambda r: r['date'])
    return rows
