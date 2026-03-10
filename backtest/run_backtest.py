#!/usr/bin/env python3
"""
run_backtest.py — Pinch Macro Swing Backtest Runner

Runs the macro swing strategy on BTC from 2022-01-01 to 2026-03-01,
covering bear market, recovery, bull run, and current drawdown.

Usage: python3 run_backtest.py
"""

import csv
import os
import sys
import datetime
import math

# Ensure backtest package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from strategies.macro_swing import (
    load_price_data,
    load_macro_events,
    run_strategy,
    compute_metrics,
    compute_buy_hold,
)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

BTC_CSV = os.path.join(DATA_DIR, "btc_daily.csv")
MACRO_CSV = os.path.join(DATA_DIR, "macro_events.csv")
RESULTS_MD = os.path.join(RESULTS_DIR, "macro_swing_results.md")
TRADE_LOG_CSV = os.path.join(RESULTS_DIR, "trade_log.csv")

BACKTEST_START = "2022-01-01"
BACKTEST_END = "2026-03-01"
INITIAL_CAPITAL = 100_000.0


def fmt_pct(v: float) -> str:
    return f"{v*100:.2f}%"


def fmt_dollar(v: float) -> str:
    return f"${v:,.2f}"


def save_trade_log(trades, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fieldnames = [
        "entry_date", "exit_date", "direction", "score",
        "position_size_pct", "entry_price", "exit_price",
        "stop_loss", "take_profit", "exit_reason",
        "pnl_pct", "partial_tp_taken",
        "account_value_before", "account_value_after",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for t in trades:
            writer.writerow({
                "entry_date": t.entry_date,
                "exit_date": t.exit_date or "",
                "direction": t.direction,
                "score": t.score,
                "position_size_pct": f"{t.position_size_pct:.2f}",
                "entry_price": f"{t.entry_price:.2f}",
                "exit_price": f"{t.exit_price:.2f}" if t.exit_price else "",
                "stop_loss": f"{t.stop_loss:.2f}",
                "take_profit": f"{t.take_profit:.2f}",
                "exit_reason": t.exit_reason or "",
                "pnl_pct": f"{t.pnl_pct*100:.4f}" if t.pnl_pct is not None else "",
                "partial_tp_taken": t.partial_tp_taken,
                "account_value_before": f"{t.account_value_before:.2f}",
                "account_value_after": f"{t.account_value_after:.2f}",
            })
    print(f"Trade log saved: {path}")


def save_results_md(metrics: dict, bh: dict, trades, log_lines: list, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)

    exit_counts = {}
    for t in trades:
        r = t.exit_reason or "unknown"
        exit_counts[r] = exit_counts.get(r, 0) + 1

    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    md = f"""# Macro Swing Strategy — Backtest Results

**Generated:** {now}  
**Period:** {BACKTEST_START} → {BACKTEST_END}  
**Initial Capital:** {fmt_dollar(INITIAL_CAPITAL)}  

---

## Strategy Performance

| Metric | Macro Swing | Buy & Hold BTC |
|--------|-------------|----------------|
| Final Value | {fmt_dollar(metrics['final_value'])} | {fmt_dollar(bh.get('final_value', 0))} |
| Total Return | {fmt_pct(metrics['total_return'])} | {fmt_pct(bh.get('total_return', 0))} |
| Annualized Return | {fmt_pct(metrics['annualized_return'])} | {fmt_pct(bh.get('annualized_return', 0))} |
| Max Drawdown | {fmt_pct(metrics['max_drawdown'])} | {fmt_pct(bh.get('max_drawdown', 0))} |
| Sharpe Ratio | {metrics['sharpe']:.3f} | N/A |

---

## Trade Statistics

| Metric | Value |
|--------|-------|
| Number of Trades | {metrics['n_trades']} |
| Win Rate | {fmt_pct(metrics['win_rate'])} |
| Average Win | {fmt_pct(metrics['avg_win'])} |
| Average Loss | {fmt_pct(metrics['avg_loss'])} |
| Profit Factor | {metrics['profit_factor']:.3f} |

### Exit Reasons
{chr(10).join(f'- **{k}**: {v}' for k, v in sorted(exit_counts.items()))}

---

## Benchmark Comparison

- BTC Start Price: {fmt_dollar(bh.get('start_price', 0))} ({BACKTEST_START})
- BTC End Price: {fmt_dollar(bh.get('end_price', 0))} ({BACKTEST_END})
- Buy & Hold Return: {fmt_pct(bh.get('total_return', 0))}
- Strategy Return: {fmt_pct(metrics['total_return'])}
- **Alpha vs BH:** {fmt_pct(metrics['total_return'] - bh.get('total_return', 0))}

---

## Strategy Signal Log (first 50 entries)

```
{chr(10).join(log_lines[:50])}
```

---

## Trade Log Summary

| # | Entry | Exit | Entry $ | Exit $ | PnL% | Reason |
|---|-------|------|---------|--------|------|--------|
"""
    for i, t in enumerate(trades, 1):
        pnl = f"{t.pnl_pct*100:.2f}%" if t.pnl_pct is not None else "—"
        md += (
            f"| {i} | {t.entry_date} | {t.exit_date or '—'} | "
            f"{fmt_dollar(t.entry_price)} | "
            f"{fmt_dollar(t.exit_price) if t.exit_price else '—'} | "
            f"{pnl} | {t.exit_reason or '—'} |\n"
        )

    md += f"""
---

## Notes

- **Signal Source:** CPI, FOMC, NFP macro events (2024-2026 data)
- **Trading Costs:** 0.40% round-trip (Kraken taker fees)  
- **Risk:** 8% stop-loss, 16% take-profit (2:1 R:R), 14-day time stop
- **Position Sizing:** 20% (score±2) or 30% (score≥±3) of account
- **Data Source:** CoinGecko free API + manual macro event database

> *Rule of Acquisition #22: A wise man can hear profit in the wind.*
"""

    with open(path, "w") as f:
        f.write(md)
    print(f"Results saved: {path}")


def main():
    print("=" * 60)
    print("PINCH MACRO SWING BACKTEST")
    print("=" * 60)
    print(f"Period: {BACKTEST_START} → {BACKTEST_END}")
    print(f"Capital: {fmt_dollar(INITIAL_CAPITAL)}")
    print()

    # Check data files
    if not os.path.exists(BTC_CSV):
        print(f"ERROR: BTC data not found at {BTC_CSV}")
        print("Run: python3 backtest/data/collect_data.py first")
        sys.exit(1)
    if not os.path.exists(MACRO_CSV):
        print(f"ERROR: Macro events not found at {MACRO_CSV}")
        sys.exit(1)

    # Load data
    print("[1/5] Loading price data...")
    price_data = load_price_data(BTC_CSV)
    print(f"  BTC: {len(price_data)} daily bars loaded")

    print("[2/5] Loading macro events...")
    macro_events = load_macro_events(MACRO_CSV)
    print(f"  Macro events: {sum(len(v) for v in macro_events.values())} events on {len(macro_events)} dates")

    print("[3/5] Running macro swing strategy...")
    state, log_lines = run_strategy(
        price_data=price_data,
        macro_events=macro_events,
        start_date=BACKTEST_START,
        end_date=BACKTEST_END,
        initial_capital=INITIAL_CAPITAL,
    )
    print(f"  Completed. {len(state.trades)} trades executed.")

    print("[4/5] Computing metrics...")
    metrics = compute_metrics(state, INITIAL_CAPITAL, BACKTEST_START, BACKTEST_END)
    bh = compute_buy_hold(price_data, BACKTEST_START, BACKTEST_END, INITIAL_CAPITAL)

    print("[5/5] Saving results...")
    os.makedirs(RESULTS_DIR, exist_ok=True)
    save_trade_log(state.trades, TRADE_LOG_CSV)
    save_results_md(metrics, bh, state.trades, log_lines, RESULTS_MD)

    # Print summary
    print()
    print("=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    print(f"{'Metric':<30} {'Macro Swing':>15} {'Buy & Hold':>15}")
    print("-" * 60)
    print(f"{'Final Value':<30} {fmt_dollar(metrics['final_value']):>15} {fmt_dollar(bh.get('final_value',0)):>15}")
    print(f"{'Total Return':<30} {fmt_pct(metrics['total_return']):>15} {fmt_pct(bh.get('total_return',0)):>15}")
    print(f"{'Annualized Return':<30} {fmt_pct(metrics['annualized_return']):>15} {fmt_pct(bh.get('annualized_return',0)):>15}")
    print(f"{'Max Drawdown':<30} {fmt_pct(metrics['max_drawdown']):>15} {fmt_pct(bh.get('max_drawdown',0)):>15}")
    print(f"{'Sharpe Ratio':<30} {metrics['sharpe']:>15.3f} {'N/A':>15}")
    print("-" * 60)
    print(f"{'Number of Trades':<30} {metrics['n_trades']:>15}")
    print(f"{'Win Rate':<30} {fmt_pct(metrics['win_rate']):>15}")
    print(f"{'Avg Win':<30} {fmt_pct(metrics['avg_win']):>15}")
    print(f"{'Avg Loss':<30} {fmt_pct(metrics['avg_loss']):>15}")
    print(f"{'Profit Factor':<30} {metrics['profit_factor']:>15.3f}")
    print("=" * 60)
    print()
    print("Rule of Acquisition #22: A wise man can hear profit in the wind.")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
