#!/usr/bin/env python3
"""
run_ema_backtest.py — EMA Crossover Backtest Runner

Tests three EMA pairs on BTC daily 2022-01-01 → 2026-03-01
  - (10, 30)  fast/slow
  - (20, 50)
  - (20, 100)

Both with and without 10% trailing stop.
Saves results to backtest/results/ema_crossover_results.md
"""

import os
import sys
import csv
import math

# Allow running from project root or backtest/
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from backtest.strategies.ema_crossover import (
    run_backtest, compute_metrics, yearly_returns
)

DATA_FILE     = os.path.join(PROJECT_ROOT, "backtest", "data", "btc_daily.csv")
RESULTS_FILE  = os.path.join(PROJECT_ROOT, "backtest", "results", "ema_crossover_results.md")

START_DATE    = "2022-01-01"
END_DATE      = "2026-03-01"
INITIAL_CAP   = 100_000.0

EMA_PAIRS = [
    (10,  30),
    (20,  50),
    (20, 100),
]


# ---------------------------------------------------------------------------
# Load BTC data
# ---------------------------------------------------------------------------

def load_data(path: str):
    dates, opens, highs, lows, closes, volumes = [], [], [], [], [], []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            dates.append(row["date"])
            opens.append(float(row["open"]))
            highs.append(float(row["high"]))
            lows.append(float(row["low"]))
            closes.append(float(row["close"]))
            volumes.append(float(row["volume"]))
    return dates, opens, highs, lows, closes, volumes


# ---------------------------------------------------------------------------
# Buy-and-hold benchmark
# ---------------------------------------------------------------------------

def buy_and_hold(dates, closes, start_date, end_date, initial_cap):
    entry = exit_ = None
    for i, d in enumerate(dates):
        if d >= start_date and entry is None:
            entry = closes[i]
        if d <= end_date:
            exit_ = closes[i]
    if entry and exit_:
        ret = (exit_ / entry - 1.0) * 100
        n   = sum(1 for d in dates if start_date <= d <= end_date) - 1
        ann = ((exit_ / entry) ** (365.25 / max(n, 1)) - 1.0) * 100

        # drawdown on BnH
        filtered = [(d, c) for d, c in zip(dates, closes) if start_date <= d <= end_date]
        peak = filtered[0][1]; max_dd = 0.0
        for _, c in filtered:
            if c > peak:
                peak = c
            dd = (peak - c) / peak * 100
            if dd > max_dd:
                max_dd = dd

        # Sharpe on BnH daily
        vals  = [c for _, c in filtered]
        rets  = [(vals[i] - vals[i-1]) / vals[i-1] for i in range(1, len(vals))]
        avg_r = sum(rets) / len(rets)
        std_r = math.sqrt(sum((r - avg_r)**2 for r in rets) / max(len(rets)-1, 1))
        sharpe = (avg_r / std_r * math.sqrt(252)) if std_r > 0 else 0.0

        return {
            "total_return":  round(ret,    2),
            "ann_return":    round(ann,    2),
            "max_drawdown":  round(max_dd, 2),
            "sharpe":        round(sharpe, 3),
        }
    return {}


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def pct(v):   return f"{v:+.2f}%"
def num(v):   return f"{v:.3f}"
def intv(v):  return str(int(round(v)))


def trades_table(trades) -> str:
    if not trades:
        return "_No trades._\n"
    header = "| Entry Date | Exit Date | Entry Price | Exit Price | P&L % | Hold Days | Exit Reason |\n"
    sep    = "|------------|-----------|-------------|------------|-------|-----------|-------------|\n"
    rows   = []
    for t in trades:
        rows.append(
            f"| {t.entry_date} | {t.exit_date or '—'} "
            f"| ${t.entry_price:>10,.0f} | ${t.exit_price:>10,.0f} "
            f"| {t.pnl_pct:+.2f}% | {t.hold_days or '—'} | {t.exit_reason or '—'} |"
        )
    return header + sep + "\n".join(rows) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"Loading BTC data from {DATA_FILE} …")
    dates, opens, highs, lows, closes, volumes = load_data(DATA_FILE)
    print(f"  Rows loaded: {len(dates)}  ({dates[0]} → {dates[-1]})")

    # Buy-and-hold benchmark
    bnh = buy_and_hold(dates, closes, START_DATE, END_DATE, INITIAL_CAP)
    print(f"\nBuy-and-Hold BTC ({START_DATE} → {END_DATE}):")
    print(f"  Total return:    {pct(bnh['total_return'])}")
    print(f"  Ann. return:     {pct(bnh['ann_return'])}")
    print(f"  Max drawdown:    {pct(-bnh['max_drawdown'])}")
    print(f"  Sharpe:          {num(bnh['sharpe'])}")

    all_results = {}

    for fast, slow in EMA_PAIRS:
        for trailing in (False, True):
            label = f"EMA({fast},{slow})" + (" + Trailing Stop" if trailing else "")
            print(f"\n{'='*60}")
            print(f"  {label}")
            print(f"{'='*60}")

            result = run_backtest(
                dates, closes, highs, lows,
                fast_period    = fast,
                slow_period    = slow,
                trailing_stop  = trailing,
                start_date     = START_DATE,
                end_date       = END_DATE,
                initial_capital= INITIAL_CAP,
            )

            metrics = compute_metrics(result, INITIAL_CAP)
            yr_rets = yearly_returns(result, INITIAL_CAP)

            print(f"  Total return:    {pct(metrics['total_return'])}")
            print(f"  Ann. return:     {pct(metrics['ann_return'])}")
            print(f"  Max drawdown:    {pct(-metrics['max_drawdown'])}")
            print(f"  Sharpe:          {num(metrics['sharpe'])}")
            print(f"  Win rate:        {metrics['win_rate']:.1f}%")
            print(f"  # Trades:        {metrics['n_trades']}")
            print(f"  Avg hold days:   {metrics['avg_hold_days']}")
            print(f"  Yearly returns:  {yr_rets}")

            key = (fast, slow, trailing)
            all_results[key] = {
                "label":   label,
                "result":  result,
                "metrics": metrics,
                "yr_rets": yr_rets,
            }

    # -----------------------------------------------------------------------
    # Generate Markdown report
    # -----------------------------------------------------------------------
    os.makedirs(os.path.dirname(RESULTS_FILE), exist_ok=True)
    write_report(all_results, bnh, dates, closes)
    print(f"\nResults saved → {RESULTS_FILE}")


def write_report(all_results, bnh, dates, closes):
    lines = []
    A = lines.append

    A("# EMA Crossover Backtest — BTC Daily")
    A("")
    A(f"**Period:** 2022-01-01 → 2026-03-01  ")
    A(f"**Asset:** BTC/USD (daily close)  ")
    A(f"**Position size:** 80% of account when long  ")
    A(f"**Trading cost:** 0.40% round-trip  ")
    A(f"**Trailing stop variant:** 10% from peak after entry  ")
    A("")

    # --- Summary table ---
    A("## Summary Comparison")
    A("")
    A("| Strategy | Total Return | Ann. Return | Max Drawdown | Sharpe | Win Rate | # Trades | Avg Hold |")
    A("|----------|-------------|------------|-------------|--------|----------|----------|----------|")

    # BnH row
    A(f"| **Buy & Hold BTC** | {pct(bnh['total_return'])} | {pct(bnh['ann_return'])} "
      f"| {pct(-bnh['max_drawdown'])} | {num(bnh['sharpe'])} | — | — | — |")

    for (fast, slow, trailing), data in sorted(all_results.items()):
        m = data["metrics"]
        tag = "🔴 +TS" if trailing else "⚪"
        A(f"| {tag} EMA({fast},{slow}) | {pct(m['total_return'])} | {pct(m['ann_return'])} "
          f"| {pct(-m['max_drawdown'])} | {num(m['sharpe'])} "
          f"| {m['win_rate']:.1f}% | {m['n_trades']} | {m['avg_hold_days']}d |")

    A("")

    # --- Per-pair detail ---
    A("## Detailed Results by EMA Pair")
    A("")

    for (fast, slow, trailing), data in sorted(all_results.items()):
        m     = data["metrics"]
        label = data["label"]
        trades= data["result"]["trades"]
        yr    = data["yr_rets"]

        A(f"### {label}")
        A("")
        A("**Metrics**")
        A("")
        A(f"- Total Return: **{pct(m['total_return'])}** (BnH: {pct(bnh['total_return'])})")
        A(f"- Annualised Return: **{pct(m['ann_return'])}** (BnH: {pct(bnh['ann_return'])})")
        A(f"- Max Drawdown: **{pct(-m['max_drawdown'])}** (BnH: {pct(-bnh['max_drawdown'])})")
        A(f"- Sharpe Ratio: **{num(m['sharpe'])}** (BnH: {num(bnh['sharpe'])})")
        A(f"- Win Rate: **{m['win_rate']:.1f}%**")
        A(f"- Number of Trades: **{m['n_trades']}**")
        A(f"- Average Hold Time: **{m['avg_hold_days']} days**")
        A("")

        # Yearly performance
        A("**Yearly Returns**")
        A("")
        A("| Year | EMA Strategy | Best / Worst |")
        A("|------|-------------|--------------|")
        best_yr  = max(yr, key=yr.get) if yr else "—"
        worst_yr = min(yr, key=yr.get) if yr else "—"
        for y, r in sorted(yr.items()):
            tag = "🟢 Best" if y == best_yr else ("🔴 Worst" if y == worst_yr else "")
            A(f"| {y} | {pct(r)} | {tag} |")
        A("")

        # Trade log (condensed — show up to 30)
        A(f"**Trade Log** ({m['n_trades']} trades)")
        A("")
        if trades:
            A(trades_table(trades[:30]))
            if len(trades) > 30:
                A(f"_…{len(trades) - 30} more trades omitted for brevity._\n")
        else:
            A("_No trades executed._\n")
        A("---")
        A("")

    # --- Best periods analysis ---
    A("## Best & Worst Years by Pair (No Trailing Stop)")
    A("")
    A("| EMA Pair | Best Year | Best Return | Worst Year | Worst Return |")
    A("|----------|-----------|------------|------------|--------------|")
    for (fast, slow, trailing), data in sorted(all_results.items()):
        if trailing:
            continue
        yr = data["yr_rets"]
        if not yr:
            A(f"| EMA({fast},{slow}) | — | — | — | — |")
            continue
        best_yr  = max(yr, key=yr.get)
        worst_yr = min(yr, key=yr.get)
        A(f"| EMA({fast},{slow}) | {best_yr} | {pct(yr[best_yr])} | {worst_yr} | {pct(yr[worst_yr])} |")
    A("")

    # --- Trailing stop impact ---
    A("## Trailing Stop Impact (10% from peak)")
    A("")
    A("| EMA Pair | Base Return | +TS Return | Δ Return | Base Max DD | +TS Max DD | Δ DD |")
    A("|----------|------------|-----------|---------|------------|-----------|------|")
    for fast, slow in EMA_PAIRS:
        base = all_results.get((fast, slow, False), {}).get("metrics", {})
        ts   = all_results.get((fast, slow, True),  {}).get("metrics", {})
        if not base or not ts:
            continue
        delta_ret = ts["total_return"] - base["total_return"]
        delta_dd  = ts["max_drawdown"]  - base["max_drawdown"]
        A(f"| EMA({fast},{slow}) | {pct(base['total_return'])} | {pct(ts['total_return'])} "
          f"| {pct(delta_ret)} | {pct(-base['max_drawdown'])} | {pct(-ts['max_drawdown'])} "
          f"| {pct(-delta_dd)} |")
    A("")

    # --- Key findings ---
    A("## Key Findings")
    A("")

    # Find overall best strategy (no trailing stop, by total return)
    base_runs = {k: v for k, v in all_results.items() if not k[2]}
    if base_runs:
        best_key = max(base_runs, key=lambda k: base_runs[k]["metrics"]["total_return"])
        best_m   = base_runs[best_key]["metrics"]
        A(f"- **Best performing pair (no TS):** EMA({best_key[0]},{best_key[1]}) "
          f"with {pct(best_m['total_return'])} total return, Sharpe {num(best_m['sharpe'])}")

        worst_key = min(base_runs, key=lambda k: base_runs[k]["metrics"]["total_return"])
        worst_m   = base_runs[worst_key]["metrics"]
        A(f"- **Worst performing pair (no TS):** EMA({worst_key[0]},{worst_key[1]}) "
          f"with {pct(worst_m['total_return'])} total return")

    # BnH vs best
    if base_runs:
        best_ret  = base_runs[best_key]["metrics"]["total_return"]
        bnh_ret   = bnh["total_return"]
        if best_ret > bnh_ret:
            A(f"- EMA crossover **outperformed** buy-and-hold by "
              f"{pct(best_ret - bnh_ret)} (best pair vs BnH)")
        else:
            A(f"- EMA crossover **underperformed** buy-and-hold by "
              f"{pct(bnh_ret - best_ret)} (best pair vs BnH)")

    A(f"- Buy-and-hold BTC returned **{pct(bnh['total_return'])}** over the period "
      f"with max drawdown of **{pct(-bnh['max_drawdown'])}**")
    A("")
    A("---")
    A("_Generated by Pinch · pinch@openclaw.ai_")

    with open(RESULTS_FILE, "w") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
