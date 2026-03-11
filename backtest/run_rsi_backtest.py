#!/usr/bin/env python3
"""
run_rsi_backtest.py — RSI Timing Overlay Backtest Runner

Compares macro swing strategy in two modes:
  1. BASELINE: Enter on signal day (original behavior)
  2. RSI-FILTERED: Wait up to 5 days for RSI < 35 before entering

Tests RSI periods: 7, 14, 21.
Saves results to backtest/results/rsi_overlay_results.md
"""

import os
import sys
import datetime

# Ensure project root is on path
project_root = os.path.dirname(os.path.abspath(__file__))
parent = os.path.dirname(project_root)
if parent not in sys.path:
    sys.path.insert(0, parent)

from backtest.strategies.macro_swing import (
    load_price_data, load_macro_events, compute_buy_hold
)
from backtest.strategies.rsi_overlay import (
    run_strategy_with_rsi, compute_rsi_metrics, calculate_rsi
)

# ─── Paths ────────────────────────────────────────────────────────────────────
DATA_DIR = os.path.join(project_root, "data")
RESULTS_DIR = os.path.join(project_root, "results")
BTC_CSV = os.path.join(DATA_DIR, "btc_daily.csv")
MACRO_CSV = os.path.join(DATA_DIR, "macro_events.csv")
OUTPUT_MD = os.path.join(RESULTS_DIR, "rsi_overlay_results.md")

START_DATE = "2024-01-01"
END_DATE = "2026-03-09"
INITIAL_CAPITAL = 100_000.0
RSI_THRESHOLD = 35.0
MAX_WAIT_DAYS = 5
RSI_PERIODS = [7, 14, 21]


def fmt_pct(v) -> str:
    if v is None:
        return "N/A"
    return f"{v*100:.2f}%"


def fmt_dollar(v) -> str:
    if v is None:
        return "N/A"
    return f"${v:,.2f}"


def fmt_rsi(v) -> str:
    if v is None:
        return "N/A"
    return f"{v:.1f}"


def run_all() -> str:
    """Run all backtests and return markdown report."""
    print(f"Loading price data from {BTC_CSV}...")
    price_data = load_price_data(BTC_CSV)
    macro_events = load_macro_events(MACRO_CSV)

    # Compute buy-and-hold benchmark
    bh = compute_buy_hold(price_data, START_DATE, END_DATE, INITIAL_CAPITAL)

    lines = []
    lines.append("# RSI Overlay Backtest Results")
    lines.append("")
    lines.append(f"**Generated:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"**Period:** {START_DATE} → {END_DATE}")
    lines.append(f"**Initial Capital:** {fmt_dollar(INITIAL_CAPITAL)}")
    lines.append(f"**Strategy:** Macro Swing + RSI Timing Overlay")
    lines.append(f"**RSI Entry Threshold:** RSI < {RSI_THRESHOLD:.0f} (long signals)")
    lines.append(f"**Max Wait Days:** {MAX_WAIT_DAYS}")
    lines.append(f"**Partial Entry Size (timeout):** 50% of normal position size")
    lines.append("")

    # ── Buy-and-Hold Benchmark ────────────────────────────────────────────────
    lines.append("## 📊 Buy-and-Hold Benchmark (BTC)")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Start Price | {fmt_dollar(bh.get('start_price'))} |")
    lines.append(f"| End Price | {fmt_dollar(bh.get('end_price'))} |")
    lines.append(f"| Total Return | {fmt_pct(bh.get('total_return'))} |")
    lines.append(f"| Annualized Return | {fmt_pct(bh.get('annualized_return'))} |")
    lines.append(f"| Max Drawdown | {fmt_pct(bh.get('max_drawdown'))} |")
    lines.append(f"| Final Value | {fmt_dollar(bh.get('final_value'))} |")
    lines.append("")

    # ── Per-RSI-Period Results ────────────────────────────────────────────────
    all_results = {}

    for period in RSI_PERIODS:
        print(f"\nRunning RSI-{period} backtests...")
        rsi_values = calculate_rsi(price_data, period=period)

        # BASELINE
        print(f"  BASELINE (RSI-{period})...")
        base_state, base_log = run_strategy_with_rsi(
            price_data, macro_events, START_DATE, END_DATE,
            rsi_period=period, rsi_threshold=RSI_THRESHOLD,
            max_wait_days=MAX_WAIT_DAYS, mode="baseline",
            initial_capital=INITIAL_CAPITAL,
        )
        base_metrics = compute_rsi_metrics(
            base_state, INITIAL_CAPITAL, START_DATE, END_DATE, price_data, rsi_values
        )

        # RSI-FILTERED
        print(f"  RSI-FILTERED (RSI-{period})...")
        rsi_state, rsi_log = run_strategy_with_rsi(
            price_data, macro_events, START_DATE, END_DATE,
            rsi_period=period, rsi_threshold=RSI_THRESHOLD,
            max_wait_days=MAX_WAIT_DAYS, mode="rsi_filter",
            initial_capital=INITIAL_CAPITAL,
        )
        rsi_metrics = compute_rsi_metrics(
            rsi_state, INITIAL_CAPITAL, START_DATE, END_DATE, price_data, rsi_values
        )

        all_results[period] = {
            "baseline": (base_state, base_metrics, base_log),
            "rsi_filter": (rsi_state, rsi_metrics, rsi_log),
            "rsi_values": rsi_values,
        }

        # ── Section header ────────────────────────────────────────────────────
        lines.append(f"---")
        lines.append(f"")
        lines.append(f"## RSI Period: {period}")
        lines.append("")
        lines.append("### Comparison Table")
        lines.append("")
        lines.append(f"| Metric | Baseline | RSI-Filtered | Δ |")
        lines.append(f"|--------|----------|--------------|---|")

        bm = base_metrics
        rm = rsi_metrics

        def delta_pct(a, b):
            if a is None or b is None:
                return "N/A"
            d = b - a
            return f"{d*100:+.2f}pp"

        def delta_val(a, b, pct=False):
            if a is None or b is None:
                return "N/A"
            d = b - a
            if pct:
                return f"{d*100:+.2f}pp"
            return f"{d:+.4f}"

        lines.append(f"| Total Return | {fmt_pct(bm['total_return'])} | {fmt_pct(rm['total_return'])} | {delta_pct(bm['total_return'], rm['total_return'])} |")
        lines.append(f"| Annualized Return | {fmt_pct(bm['annualized_return'])} | {fmt_pct(rm['annualized_return'])} | {delta_pct(bm['annualized_return'], rm['annualized_return'])} |")
        lines.append(f"| Final Value | {fmt_dollar(bm['final_value'])} | {fmt_dollar(rm['final_value'])} | {fmt_dollar(rm['final_value'] - bm['final_value'])} |")
        lines.append(f"| Max Drawdown | {fmt_pct(bm['max_drawdown'])} | {fmt_pct(rm['max_drawdown'])} | {delta_pct(bm['max_drawdown'], rm['max_drawdown'])} |")
        lines.append(f"| Win Rate | {fmt_pct(bm['win_rate'])} | {fmt_pct(rm['win_rate'])} | {delta_pct(bm['win_rate'], rm['win_rate'])} |")
        lines.append(f"| # Trades | {bm['n_trades']} | {rm['n_trades']} | {rm['n_trades'] - bm['n_trades']:+d} |")
        lines.append(f"| Avg Win | {fmt_pct(bm['avg_win'])} | {fmt_pct(rm['avg_win'])} | {delta_pct(bm['avg_win'], rm['avg_win'])} |")
        lines.append(f"| Avg Loss | {fmt_pct(bm['avg_loss'])} | {fmt_pct(rm['avg_loss'])} | {delta_pct(bm['avg_loss'], rm['avg_loss'])} |")
        lines.append(f"| Profit Factor | {bm['profit_factor']:.3f} | {rm['profit_factor']:.3f} | {rm['profit_factor'] - bm['profit_factor']:+.3f} |")
        lines.append(f"| Sharpe Ratio | {bm['sharpe']:.3f} | {rm['sharpe']:.3f} | {rm['sharpe'] - bm['sharpe']:+.3f} |")
        lines.append(f"| Avg Entry RSI | {fmt_rsi(bm['avg_entry_rsi'])} | {fmt_rsi(rm['avg_entry_rsi'])} | — |")
        lines.append(f"| Avg Entry Price | {fmt_dollar(bm['avg_entry_price'])} | {fmt_dollar(rm['avg_entry_price'])} | — |")
        lines.append("")

        # ── Trade-level detail ────────────────────────────────────────────────
        lines.append("### BASELINE Trade Log")
        lines.append("")
        lines.append("| # | Entry Date | Entry Price | Exit Date | Exit Price | PnL% | Exit Reason | Entry RSI |")
        lines.append("|---|-----------|-------------|-----------|------------|------|-------------|-----------|")
        for i, t in enumerate(base_state.trades, 1):
            rv = rsi_values.get(t.entry_date)
            lines.append(
                f"| {i} | {t.entry_date} | {fmt_dollar(t.entry_price)} | "
                f"{t.exit_date or '—'} | {fmt_dollar(t.exit_price)} | "
                f"{fmt_pct(t.pnl_pct)} | {t.exit_reason or '—'} | {fmt_rsi(rv)} |"
            )
        lines.append("")

        lines.append("### RSI-FILTERED Trade Log")
        lines.append("")
        lines.append("| # | Entry Date | Entry Price | Size% | Exit Date | Exit Price | PnL% | Exit Reason | Entry RSI |")
        lines.append("|---|-----------|-------------|-------|-----------|------------|------|-------------|-----------|")
        for i, t in enumerate(rsi_state.trades, 1):
            rv = rsi_values.get(t.entry_date)
            lines.append(
                f"| {i} | {t.entry_date} | {fmt_dollar(t.entry_price)} | "
                f"{t.position_size_pct*100:.0f}% | "
                f"{t.exit_date or '—'} | {fmt_dollar(t.exit_price)} | "
                f"{fmt_pct(t.pnl_pct)} | {t.exit_reason or '—'} | {fmt_rsi(rv)} |"
            )
        lines.append("")

    # ── Cross-Period Summary ──────────────────────────────────────────────────
    lines.append("---")
    lines.append("")
    lines.append("## 📈 Cross-Period Summary")
    lines.append("")
    lines.append("### Total Return by RSI Period")
    lines.append("")
    lines.append("| RSI Period | Baseline Return | RSI-Filtered Return | Delta | Winner |")
    lines.append("|-----------|----------------|---------------------|-------|--------|")
    for period in RSI_PERIODS:
        bm = all_results[period]["baseline"][1]
        rm = all_results[period]["rsi_filter"][1]
        delta = rm["total_return"] - bm["total_return"]
        winner = "RSI-Filter ✅" if rm["total_return"] > bm["total_return"] else "Baseline"
        lines.append(
            f"| RSI-{period} | {fmt_pct(bm['total_return'])} | {fmt_pct(rm['total_return'])} "
            f"| {delta*100:+.2f}pp | {winner} |"
        )
    lines.append("")

    lines.append("### Win Rate by RSI Period")
    lines.append("")
    lines.append("| RSI Period | Baseline Win Rate | RSI-Filtered Win Rate | Delta |")
    lines.append("|-----------|------------------|----------------------|-------|")
    for period in RSI_PERIODS:
        bm = all_results[period]["baseline"][1]
        rm = all_results[period]["rsi_filter"][1]
        delta = rm["win_rate"] - bm["win_rate"]
        lines.append(
            f"| RSI-{period} | {fmt_pct(bm['win_rate'])} | {fmt_pct(rm['win_rate'])} "
            f"| {delta*100:+.2f}pp |"
        )
    lines.append("")

    lines.append("### Max Drawdown by RSI Period")
    lines.append("")
    lines.append("| RSI Period | Baseline DD | RSI-Filtered DD | Improvement |")
    lines.append("|-----------|------------|-----------------|-------------|")
    for period in RSI_PERIODS:
        bm = all_results[period]["baseline"][1]
        rm = all_results[period]["rsi_filter"][1]
        improvement = bm["max_drawdown"] - rm["max_drawdown"]
        lines.append(
            f"| RSI-{period} | {fmt_pct(bm['max_drawdown'])} | {fmt_pct(rm['max_drawdown'])} "
            f"| {improvement*100:+.2f}pp |"
        )
    lines.append("")

    # ── Interpretation ────────────────────────────────────────────────────────
    lines.append("---")
    lines.append("")
    lines.append("## 💡 Interpretation & Recommendations")
    lines.append("")

    # Determine best performer
    best_period = None
    best_return = -float("inf")
    best_mode = None
    for period in RSI_PERIODS:
        bm = all_results[period]["baseline"][1]
        rm = all_results[period]["rsi_filter"][1]
        if bm["total_return"] > best_return:
            best_return = bm["total_return"]
            best_period = period
            best_mode = "Baseline"
        if rm["total_return"] > best_return:
            best_return = rm["total_return"]
            best_period = period
            best_mode = f"RSI-{period} Filtered"

    lines.append(f"**Best performer:** {best_mode} with RSI-{best_period} ({fmt_pct(best_return)} total return)")
    lines.append("")
    lines.append("### Key Findings")
    lines.append("")
    lines.append("1. **RSI Filtering Effect on Entry Quality**")
    lines.append("   - RSI < 35 threshold targets oversold conditions before macro-driven long entries")
    lines.append("   - Lower avg entry RSI in filtered mode = entering at more favorable prices")
    lines.append("   - 50% size on timeout entries limits risk when RSI confirmation is absent")
    lines.append("")
    lines.append("2. **Trade Count Impact**")
    lines.append("   - RSI filtering reduces trade count (some signals expire without confirmation)")
    lines.append("   - Fewer trades = lower total commission drag")
    lines.append("   - Risk: missed moves if RSI never reaches threshold in trending markets")
    lines.append("")
    lines.append("3. **RSI Period Sensitivity**")
    lines.append("   - RSI-7 (fast): More responsive, generates more confirmation signals")
    lines.append("   - RSI-14 (standard): Balanced signal/noise tradeoff")
    lines.append("   - RSI-21 (slow): Fewer but potentially higher-quality oversold readings")
    lines.append("")
    lines.append("4. **Recommendation**")
    lines.append("   - If RSI filtering improves win rate AND reduces drawdown → adopt RSI-{best_period} filter")
    lines.append("   - Consider using RSI as a CONFIDENCE MODIFIER rather than hard gate:")
    lines.append("     * RSI < 30: full size")
    lines.append("     * RSI 30-45: 75% size")
    lines.append("     * RSI > 45: 50% size (as currently coded for timeout case)")
    lines.append("   - **Rule of Acquisition #22: A wise man can hear profit in the wind.**")
    lines.append("     *Waiting for RSI confirmation is not patience — it's math.*")
    lines.append("")
    lines.append("---")
    lines.append(f"*Run by Pinch — {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}*")

    return "\n".join(lines)


if __name__ == "__main__":
    os.makedirs(RESULTS_DIR, exist_ok=True)

    report = run_all()

    with open(OUTPUT_MD, "w") as f:
        f.write(report)

    print(f"\n✅ Results saved to {OUTPUT_MD}")
    print("\n" + "="*60)
    # Print summary to stdout
    for line in report.split("\n"):
        if line.startswith("## ") or line.startswith("| "):
            print(line)
