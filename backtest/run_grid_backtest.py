#!/usr/bin/env python3
"""
run_grid_backtest.py — Grid Trading Backtest Runner for ETH

Tests four grid spacings ($50, $100, $150, $200) over ETH daily data
from 2022-01-01 to 2026-03-01. Outputs results to backtest/results/grid_trading_results.md.
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.strategies.grid_trading import (
    load_eth_data,
    initialize_grid,
    simulate_day,
    compute_metrics,
    INITIAL_ACCOUNT,
    GRID_CAPITAL,
    GRID_LEVELS,
    FEE_RATE,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATA_FILE   = os.path.join(os.path.dirname(__file__), 'data', 'eth_daily.csv')
RESULTS_DIR = os.path.join(os.path.dirname(__file__), 'results')
RESULTS_FILE = os.path.join(RESULTS_DIR, 'grid_trading_results.md')

START_DATE  = '2022-01-01'
END_DATE    = '2026-03-01'

GRID_SPACINGS = [50, 100, 150, 200]


# ---------------------------------------------------------------------------
# Run one backtest
# ---------------------------------------------------------------------------

def run_backtest(data: list, grid_spacing: float) -> dict:
    start_price = data[0]['close']
    center_price = start_price

    state = initialize_grid(center_price, grid_spacing)

    for row in data:
        simulate_day(
            state,
            date_str=row['date'],
            day_open=row['open'],
            day_high=row['high'],
            day_low=row['low'],
            day_close=row['close'],
        )

    metrics = compute_metrics(
        state,
        start_price=start_price,
        end_price=data[-1]['close'],
        start_date=data[0]['date'],
        end_date=data[-1]['date'],
    )
    metrics['_state'] = state
    return metrics


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _fmt_pct(v: float) -> str:
    sign = '+' if v >= 0 else ''
    return f"{sign}{v:.2f}%"


def _fmt_usd(v: float) -> str:
    sign = '+' if v >= 0 else '-'
    return f"{sign}${abs(v):,.2f}"


def generate_report(all_results: list[dict]) -> str:
    lines = []

    lines.append("# Grid Trading Backtest — ETH/USD")
    lines.append("")
    lines.append(f"**Period:** {START_DATE} → {END_DATE}")
    lines.append(f"**Initial Capital:** ${INITIAL_ACCOUNT:,.0f}  ")
    lines.append(f"**Grid Allocation:** ${GRID_CAPITAL:,.0f} (50%)  ")
    lines.append(f"**Grid Levels:** {GRID_LEVELS} above + {GRID_LEVELS} below center  ")
    lines.append(f"**Fee Rate:** {FEE_RATE*100:.1f}% per side  ")
    lines.append(f"**Grid Spacings Tested:** $50 · $100 · $150 · $200")
    lines.append("")

    # ETH buy-and-hold reference (same for all)
    r0 = all_results[0]
    lines.append("## ETH Buy & Hold Benchmark")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Entry Price | ${r0['start_price']:,.2f} |")
    lines.append(f"| Exit Price  | ${r0['end_price']:,.2f} |")
    lines.append(f"| Final Value | ${r0['hold_final_value']:,.2f} |")
    lines.append(f"| Total Return | {_fmt_pct(r0['hold_return_pct'])} |")
    lines.append("")

    # Summary comparison table
    lines.append("## Strategy Comparison")
    lines.append("")
    lines.append("| Metric | $50 Grid | $100 Grid | $150 Grid | $200 Grid | Buy & Hold |")
    lines.append("|--------|----------|-----------|-----------|-----------|------------|")

    def row(label, key=None, fn=None, hold_val=None):
        cells = [label]
        for r in all_results:
            v = r[key] if key else None
            cells.append(fn(v) if fn else str(v))
        cells.append(hold_val if hold_val else "—")
        lines.append("| " + " | ".join(cells) + " |")

    for r in all_results:
        pass  # just referencing

    row("Final Value",       "final_account_value", lambda v: f"${v:,.2f}",
        f"${r0['hold_final_value']:,.2f}")
    row("Total Return",      "total_return_pct",    _fmt_pct,
        _fmt_pct(r0['hold_return_pct']))
    row("Annualized Return", "annualized_return_pct", _fmt_pct, "—")
    row("Max Drawdown",      "max_drawdown_pct",    lambda v: f"-{v:.2f}%", "—")
    row("Realized P&L",      "realized_pnl",        _fmt_usd, "—")
    row("Total Fees",        "total_fees",           lambda v: f"${v:,.2f}", "—")
    row("# Completed Cycles","num_cycles",           lambda v: f"{v:,}", "—")
    row("Buy Fills",         "num_buy_fills",        lambda v: f"{v:,}", "—")
    row("Sell Fills",        "num_sell_fills",       lambda v: f"{v:,}", "—")
    row("Avg Fills/Month",   "avg_fills_per_month",  lambda v: f"{v:.1f}", "—")
    row("Profit/Cycle",      "profit_per_cycle",     _fmt_usd, "—")
    row("ETH Held at End",   "eth_inventory_remaining", lambda v: f"{v:.4f} ETH", "—")

    lines.append("")

    # Per-spacing detail
    for r in all_results:
        gs = r['grid_spacing']
        state = r['_state']
        lines.append(f"---")
        lines.append(f"")
        lines.append(f"## Grid Spacing: ${gs}")
        lines.append(f"")
        lines.append(f"### Summary")
        lines.append(f"")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Grid Center (Start) | ${r['start_price']:,.2f} |")
        lines.append(f"| ETH Price at End | ${r['end_price']:,.2f} |")
        lines.append(f"| Final Account Value | ${r['final_account_value']:,.2f} |")
        lines.append(f"| Realized P&L | {_fmt_usd(r['realized_pnl'])} |")
        lines.append(f"| Unrealized P&L | {_fmt_usd(r['unrealized_pnl'])} |")
        lines.append(f"| Total Fees Paid | ${r['total_fees']:,.2f} |")
        lines.append(f"| Total Return | {_fmt_pct(r['total_return_pct'])} |")
        lines.append(f"| Annualized Return | {_fmt_pct(r['annualized_return_pct'])} |")
        lines.append(f"| Max Drawdown | -{r['max_drawdown_pct']:.2f}% |")
        lines.append(f"| Completed Grid Cycles | {r['num_cycles']:,} |")
        lines.append(f"| Buy Fills | {r['num_buy_fills']:,} |")
        lines.append(f"| Sell Fills | {r['num_sell_fills']:,} |")
        lines.append(f"| Avg Fills per Month | {r['avg_fills_per_month']:.1f} |")
        lines.append(f"| Avg Profit per Cycle | {_fmt_usd(r['profit_per_cycle'])} |")
        lines.append(f"| ETH Remaining | {r['eth_inventory_remaining']:.4f} ETH |")
        lines.append(f"| Grid Cash Remaining | ${r['grid_cash_remaining']:,.2f} |")
        lines.append(f"| vs Buy & Hold | {_fmt_pct(r['total_return_pct'] - r['hold_return_pct'])} alpha |")
        lines.append(f"")

        # Monthly P&L table
        lines.append(f"### Monthly P&L (Realized, ${gs} Grid)")
        lines.append(f"")
        lines.append(f"| Month | Fills | Net P&L |")
        lines.append(f"|-------|-------|---------|")
        all_months = sorted(set(list(state.monthly_fills.keys()) +
                                list(state.monthly_pnl.keys())))
        for ym in all_months:
            fills = state.monthly_fills.get(ym, 0)
            pnl   = state.monthly_pnl.get(ym, 0.0)
            lines.append(f"| {ym} | {fills} | {_fmt_usd(pnl)} |")
        lines.append(f"")

        lines.append(f"**Best Month:** {r['best_month']} ({_fmt_usd(r['best_month_pnl'])})  ")
        lines.append(f"**Worst Month:** {r['worst_month']} ({_fmt_usd(r['worst_month_pnl'])})")
        lines.append(f"")

    # Observations
    lines.append("---")
    lines.append("")
    lines.append("## Key Observations")
    lines.append("")

    best_by_return = max(all_results, key=lambda r: r['total_return_pct'])
    best_by_cycles = max(all_results, key=lambda r: r['num_cycles'])
    best_by_drawdown = min(all_results, key=lambda r: r['max_drawdown_pct'])

    lines.append(f"- **Best Total Return:** ${best_by_return['grid_spacing']} grid "
                 f"({_fmt_pct(best_by_return['total_return_pct'])})")
    lines.append(f"- **Most Active (Cycles):** ${best_by_cycles['grid_spacing']} grid "
                 f"({best_by_cycles['num_cycles']:,} completed cycles)")
    lines.append(f"- **Lowest Drawdown:** ${best_by_drawdown['grid_spacing']} grid "
                 f"(-{best_by_drawdown['max_drawdown_pct']:.2f}%)")
    lines.append(f"- **Buy & Hold Return:** {_fmt_pct(r0['hold_return_pct'])} "
                 f"(${r0['hold_final_value']:,.2f})")
    lines.append("")
    lines.append("### Grid Trading Dynamics")
    lines.append("")
    lines.append("- Tighter grids ($50) generate more fills and cycles but each cycle profits less.")
    lines.append("- Wider grids ($200) profit more per cycle but fill less frequently.")
    lines.append("- High-volatility periods (2022 bear, 2024-2025 bull) drive most grid activity.")
    lines.append("- ETH's net decline from $3,769 → ~$1,939 (−49%) creates a challenging environment:")
    lines.append("  grid buys accumulate inventory in declining market; unrealized losses offset realized gains.")
    lines.append("- Grid trading outperforms buy-and-hold when price oscillates in a range;")
    lines.append("  strong directional trends (especially down) reduce effectiveness.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"*Generated by run_grid_backtest.py — Pinch Grid Trading Engine*")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"Loading ETH data: {START_DATE} → {END_DATE}")
    data = load_eth_data(DATA_FILE, START_DATE, END_DATE)
    if not data:
        print("ERROR: No data loaded. Check file path and date range.")
        sys.exit(1)
    print(f"Loaded {len(data)} trading days")
    print(f"ETH range: ${data[0]['close']:,.2f} (start) → ${data[-1]['close']:,.2f} (end)")
    print()

    all_results = []
    for spacing in GRID_SPACINGS:
        print(f"Running backtest: grid spacing = ${spacing} ...")
        result = run_backtest(data, float(spacing))
        all_results.append(result)
        print(f"  → Final: ${result['final_account_value']:,.2f} | "
              f"Return: {result['total_return_pct']:+.2f}% | "
              f"Cycles: {result['num_cycles']:,} | "
              f"Realized P&L: {result['realized_pnl']:+,.2f}")

    print()
    print(f"ETH Buy & Hold: ${all_results[0]['hold_final_value']:,.2f} "
          f"({all_results[0]['hold_return_pct']:+.2f}%)")
    print()

    # Save report
    os.makedirs(RESULTS_DIR, exist_ok=True)
    report = generate_report(all_results)
    with open(RESULTS_FILE, 'w') as f:
        f.write(report)
    print(f"Results saved → {RESULTS_FILE}")


if __name__ == '__main__':
    main()
