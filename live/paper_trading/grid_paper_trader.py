#!/usr/bin/env python3
"""
Grid Paper Trader — Issue #33
Tracks a symmetric grid strategy on ETHUSD (paper trading only).
No external dependencies; uses urllib for Kraken public API.
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

# ── Config ────────────────────────────────────────────────────────────────────
PAIR          = "ETHUSD"
GRID_SPACING  = 150.0     # dollars between levels
NUM_LEVELS    = 5         # above AND below center
CAPITAL       = 376.0     # USD allocated to grid
FEE_RATE      = 0.004     # 0.40% round-trip (split as 0.20% per side)

STATE_DIR  = os.path.join(os.path.dirname(__file__), "state")
STATE_FILE = os.path.join(STATE_DIR, "grid_paper_state.json")

KRAKEN_URL = "https://api.kraken.com/0/public/Ticker?pair=ETHUSD"
KRAKEN_KEY = "XETHZUSD"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fetch_eth_price() -> float:
    """Fetch last ETH/USD price from Kraken public API."""
    with urllib.request.urlopen(KRAKEN_URL, timeout=10) as resp:
        data = json.loads(resp.read().decode())
    if data.get("error"):
        raise RuntimeError(f"Kraken API error: {data['error']}")
    return float(data["result"][KRAKEN_KEY]["c"][0])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _round2(v: float) -> float:
    return round(v, 2)


# ── Grid Paper Trader ─────────────────────────────────────────────────────────

class GridPaperTrader:
    """
    Symmetric grid paper trader.

    Grid layout (example center=$2000, spacing=$150, 5 levels):
      Sell: 2150, 2300, 2450, 2600, 2750
      Buy:  1850, 1700, 1550, 1400, 1250

    On a buy fill  → place sell one level above the filled price.
    On a sell fill → place buy one level below the filled price.
    """

    def __init__(
        self,
        pair: str = PAIR,
        grid_spacing: float = GRID_SPACING,
        num_levels: int = NUM_LEVELS,
        capital: float = CAPITAL,
        fee_rate: float = FEE_RATE,
    ):
        self.pair        = pair
        self.spacing     = grid_spacing
        self.num_levels  = num_levels
        self.capital     = capital
        self.fee_rate    = fee_rate          # round-trip; 0.5× applied per fill
        self.one_side_fee = fee_rate / 2.0   # ~0.20% per individual fill

        # Per-level allocation: capital spread evenly across buy levels
        self.level_capital = capital / num_levels

        # Live state (overridden by load_state if file exists)
        self.center_price  = 0.0
        self.buy_orders    = {}   # price → {price, qty, status}
        self.sell_orders   = {}   # price → {price, qty, status}
        self.fill_history  = []   # list of fill dicts
        self.inventory     = 0.0  # ETH held
        self.cash          = capital
        self.realized_pnl  = 0.0
        self.setup_time    = None

        os.makedirs(STATE_DIR, exist_ok=True)
        self._load_state()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load_state(self):
        if not os.path.exists(STATE_FILE):
            return
        try:
            with open(STATE_FILE) as f:
                s = json.load(f)
            self.center_price = s.get("center_price", 0.0)
            self.buy_orders   = {float(k): v for k, v in s.get("buy_orders", {}).items()}
            self.sell_orders  = {float(k): v for k, v in s.get("sell_orders", {}).items()}
            self.fill_history = s.get("fill_history", [])
            self.inventory    = s.get("inventory", 0.0)
            self.cash         = s.get("cash", self.capital)
            self.realized_pnl = s.get("realized_pnl", 0.0)
            self.setup_time   = s.get("setup_time")
        except Exception as e:
            print(f"[WARN] Could not load state: {e}")

    def _save_state(self):
        state = {
            "center_price": self.center_price,
            "buy_orders":   {str(k): v for k, v in self.buy_orders.items()},
            "sell_orders":  {str(k): v for k, v in self.sell_orders.items()},
            "fill_history": self.fill_history,
            "inventory":    self.inventory,
            "cash":         self.cash,
            "realized_pnl": self.realized_pnl,
            "setup_time":   self.setup_time,
            "pair":         self.pair,
            "grid_spacing": self.spacing,
            "num_levels":   self.num_levels,
            "capital":      self.capital,
        }
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)

    # ── Grid setup ───────────────────────────────────────────────────────────

    def setup_grid(self, current_price: float):
        """Create symmetric grid centered on current_price."""
        self.center_price = current_price
        self.buy_orders   = {}
        self.sell_orders  = {}
        self.inventory    = 0.0
        self.cash         = self.capital
        self.realized_pnl = 0.0
        self.fill_history = []
        self.setup_time   = _now()

        for i in range(1, self.num_levels + 1):
            buy_price  = _round2(current_price - i * self.spacing)
            sell_price = _round2(current_price + i * self.spacing)
            qty = _round2(self.level_capital / buy_price)

            self.buy_orders[buy_price] = {
                "price":  buy_price,
                "qty":    qty,
                "status": "open",
                "level":  i,
            }
            self.sell_orders[sell_price] = {
                "price":  sell_price,
                "qty":    qty,
                "status": "open",
                "level":  i,
            }

        self._save_state()
        print(f"✅ Grid set up at center ${current_price:,.2f}")
        print(f"   Buy levels:  {sorted(self.buy_orders.keys())}")
        print(f"   Sell levels: {sorted(self.sell_orders.keys())}")

    # ── Fill checking ─────────────────────────────────────────────────────────

    def check_fills(self, current_high: float, current_low: float):
        """
        Simulate fills for current candle's high/low.
        Buy if low <= buy level price.
        Sell if high >= sell level price.
        """
        filled_any = False

        # Check buy fills (low dipped below buy level)
        for price in sorted(self.buy_orders.keys()):
            order = self.buy_orders[price]
            if order["status"] != "open":
                continue
            if current_low <= price:
                self._fill_buy(order, price)
                filled_any = True

        # Check sell fills (high reached sell level)
        for price in sorted(self.sell_orders.keys(), reverse=True):
            order = self.sell_orders[price]
            if order["status"] != "open":
                continue
            if current_high >= price:
                self._fill_sell(order, price)
                filled_any = True

        if filled_any:
            self._save_state()
        return filled_any

    def _fill_buy(self, order: dict, price: float):
        qty   = order["qty"]
        fee   = _round2(price * qty * self.one_side_fee)
        cost  = _round2(price * qty + fee)

        order["status"]      = "filled"
        order["fill_time"]   = _now()
        order["fee_paid"]    = fee

        self.cash      -= cost
        self.inventory += qty

        fill_record = {
            "side":      "buy",
            "price":     price,
            "qty":       qty,
            "fee":       fee,
            "cost":      cost,
            "time":      _now(),
        }
        self.fill_history.append(fill_record)
        print(f"  🟢 BUY  filled: {qty:.6f} ETH @ ${price:,.2f}  fee=${fee:.2f}")

        # Place sell one level above
        sell_price = _round2(price + self.spacing)
        if sell_price not in self.sell_orders or self.sell_orders[sell_price]["status"] == "filled":
            self.sell_orders[sell_price] = {
                "price":  sell_price,
                "qty":    qty,
                "status": "open",
                "level":  "counter",
            }
            print(f"       → Counter-sell placed at ${sell_price:,.2f}")

    def _fill_sell(self, order: dict, price: float):
        qty      = order["qty"]
        fee      = _round2(price * qty * self.one_side_fee)
        proceeds = _round2(price * qty - fee)

        # Find the corresponding buy cost basis
        # Use average from fill history for simplicity
        buy_fills = [f for f in self.fill_history if f["side"] == "buy"]
        avg_cost  = (
            sum(f["price"] for f in buy_fills) / len(buy_fills)
            if buy_fills else price - self.spacing
        )
        pnl = _round2((price - avg_cost) * qty - fee)

        order["status"]      = "filled"
        order["fill_time"]   = _now()
        order["fee_paid"]    = fee

        self.cash         += proceeds
        self.inventory    -= qty
        self.realized_pnl += pnl

        fill_record = {
            "side":     "sell",
            "price":    price,
            "qty":      qty,
            "fee":      fee,
            "proceeds": proceeds,
            "pnl":      pnl,
            "time":     _now(),
        }
        self.fill_history.append(fill_record)
        print(f"  🔴 SELL filled: {qty:.6f} ETH @ ${price:,.2f}  fee=${fee:.2f}  pnl=${pnl:+.2f}")

        # Place buy one level below
        buy_price = _round2(price - self.spacing)
        if buy_price not in self.buy_orders or self.buy_orders[buy_price]["status"] == "filled":
            self.buy_orders[buy_price] = {
                "price":  buy_price,
                "qty":    qty,
                "status": "open",
                "level":  "counter",
            }
            print(f"       → Counter-buy placed at ${buy_price:,.2f}")

    # ── Status & summaries ────────────────────────────────────────────────────

    def get_status(self, current_price: float = None) -> dict:
        unrealized_pnl = 0.0
        if current_price and self.inventory > 0:
            # Estimate avg buy price from open inventory
            buy_fills = [f for f in self.fill_history if f["side"] == "buy"]
            sell_fills = [f for f in self.fill_history if f["side"] == "sell"]
            total_bought = sum(f["qty"] for f in buy_fills)
            total_sold   = sum(f["qty"] for f in sell_fills)
            if total_bought > 0:
                avg_buy = sum(f["price"] * f["qty"] for f in buy_fills) / total_bought
                unrealized_pnl = _round2((current_price - avg_buy) * self.inventory)

        total_value = _round2(
            self.cash + self.inventory * (current_price or self.center_price)
        )

        return {
            "pair":           self.pair,
            "center_price":   self.center_price,
            "current_price":  current_price,
            "grid_spacing":   self.spacing,
            "num_levels":     self.num_levels,
            "open_buys":      sum(1 for o in self.buy_orders.values()  if o["status"] == "open"),
            "open_sells":     sum(1 for o in self.sell_orders.values() if o["status"] == "open"),
            "filled_buys":    sum(1 for f in self.fill_history if f["side"] == "buy"),
            "filled_sells":   sum(1 for f in self.fill_history if f["side"] == "sell"),
            "inventory_eth":  _round2(self.inventory),
            "cash_usd":       _round2(self.cash),
            "realized_pnl":   _round2(self.realized_pnl),
            "unrealized_pnl": _round2(unrealized_pnl),
            "total_value":    total_value,
            "pnl_pct":        _round2((total_value - self.capital) / self.capital * 100),
            "setup_time":     self.setup_time,
        }

    def get_daily_summary(self, current_price: float = None) -> str:
        s = self.get_status(current_price)
        lines = [
            "### 📊 Grid Paper Trader — ETHUSD",
            f"- **Center:** ${s['center_price']:,.2f}  |  **Current:** ${s['current_price']:,.2f}" if s['current_price'] else f"- **Center:** ${s['center_price']:,.2f}",
            f"- **Grid spacing:** ${s['grid_spacing']:.0f}  |  **Levels:** {s['num_levels']} above + {s['num_levels']} below",
            f"- **Open orders:** {s['open_buys']} buys / {s['open_sells']} sells",
            f"- **Fills:** {s['filled_buys']} buys / {s['filled_sells']} sells",
            f"- **Inventory:** {s['inventory_eth']:.6f} ETH  |  **Cash:** ${s['cash_usd']:,.2f}",
            f"- **Realized P&L:** ${s['realized_pnl']:+,.2f}",
            f"- **Unrealized P&L:** ${s['unrealized_pnl']:+,.2f}",
            f"- **Total Value:** ${s['total_value']:,.2f}  ({s['pnl_pct']:+.2f}%)",
        ]
        return "\n".join(lines)

    def reset_grid(self, new_center_price: float):
        """Recenter grid around a new price (liquidates existing state)."""
        print(f"🔄 Resetting grid from ${self.center_price:,.2f} → ${new_center_price:,.2f}")
        self.setup_grid(new_center_price)

    # ── Grid levels display ───────────────────────────────────────────────────

    def _print_grid_levels(self):
        all_sells = sorted(self.sell_orders.keys(), reverse=True)
        all_buys  = sorted(self.buy_orders.keys(),  reverse=True)

        print("\n  SELL levels:")
        for p in all_sells:
            o = self.sell_orders[p]
            mark = "✓" if o["status"] == "filled" else "·"
            print(f"    {mark} ${p:>10,.2f}  qty={o['qty']:.6f}  [{o['status']}]")

        print(f"  ── CENTER: ${self.center_price:,.2f} ──")

        print("  BUY levels:")
        for p in all_buys:
            o = self.buy_orders[p]
            mark = "✓" if o["status"] == "filled" else "·"
            print(f"    {mark} ${p:>10,.2f}  qty={o['qty']:.6f}  [{o['status']}]")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    trader = GridPaperTrader()

    if cmd == "setup":
        print("Fetching ETH price from Kraken…")
        price = _fetch_eth_price()
        print(f"Current ETH/USD: ${price:,.2f}")
        trader.setup_grid(price)

    elif cmd == "check":
        if trader.center_price == 0:
            print("❌ Grid not initialized. Run: python3 grid_paper_trader.py setup")
            sys.exit(1)
        print("Fetching ETH price from Kraken…")
        price = _fetch_eth_price()
        print(f"Current ETH/USD: ${price:,.2f}")
        # For paper trading we use current price as both high and low
        # (single price tick check; use OHLC for proper candle-based checks)
        filled = trader.check_fills(current_high=price, current_low=price)
        if not filled:
            print("  No fills at current price.")
        status = trader.get_status(price)
        print(f"\nInventory: {status['inventory_eth']:.6f} ETH  Cash: ${status['cash_usd']:,.2f}")
        print(f"Realized P&L: ${status['realized_pnl']:+,.2f}  |  Total: ${status['total_value']:,.2f} ({status['pnl_pct']:+.2f}%)")

    elif cmd == "status":
        if trader.center_price == 0:
            print("❌ Grid not initialized. Run: python3 grid_paper_trader.py setup")
            sys.exit(1)
        try:
            price = _fetch_eth_price()
        except Exception:
            price = None
        status = trader.get_status(price)
        print(trader.get_daily_summary(price))
        trader._print_grid_levels()

    elif cmd == "history":
        if not trader.fill_history:
            print("No fills recorded yet.")
        else:
            print(f"{'Time':<27} {'Side':<5} {'Price':>10} {'Qty':>10} {'Fee':>8} {'P&L':>10}")
            print("-" * 80)
            for f in trader.fill_history:
                pnl = f.get("pnl", 0)
                print(
                    f"{f['time']:<27} {f['side']:<5} ${f['price']:>9,.2f} "
                    f"{f['qty']:>10.6f} ${f['fee']:>7.2f} ${pnl:>9,.2f}"
                )
            print(f"\nTotal realized P&L: ${trader.realized_pnl:+,.2f}")

    elif cmd == "reset":
        price_arg = float(sys.argv[2]) if len(sys.argv) > 2 else None
        if price_arg is None:
            price_arg = _fetch_eth_price()
        trader.reset_grid(price_arg)

    else:
        print(f"Unknown command: {cmd}")
        print("Usage: python3 grid_paper_trader.py [setup|check|status|history|reset]")
        sys.exit(1)


if __name__ == "__main__":
    main()
