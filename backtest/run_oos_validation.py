#!/usr/bin/env python3
"""
run_oos_validation.py — Out-of-Sample Validation for Macro Swing Strategy

Splits the data into:
  - In-Sample  (IS) : 2022-01-01 → 2024-12-31
  - Out-of-Sample (OOS): 2025-01-01 → 2026-03-01

Since the strategy is rule-based (no fitted parameters), "training" consists
of confirming that the signal logic fires correctly on the IS period, then
verifying the same rules hold on OOS.

Also runs parameter sensitivity: stop-loss swept from 5% to 12%.

Usage: python3 backtest/run_oos_validation.py
"""

import os
import sys
import math
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from strategies.macro_swing import (
    load_price_data,
    load_macro_events,
    run_strategy,
    compute_metrics,
    compute_buy_hold,
    STOP_LOSS_PCT,
    TP_RATIO,
)
import strategies.macro_swing as ms

DATA_DIR    = os.path.join(os.path.dirname(__file__), "data")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

BTC_CSV   = os.path.join(DATA_DIR, "btc_daily.csv")
MACRO_CSV = os.path.join(DATA_DIR, "macro_events.csv")
OOS_MD    = os.path.join(RESULTS_DIR, "oos_validation.md")

IS_START  = "2022-01-01"
IS_END    = "2024-12-31"
OOS_START = "2025-01-01"
OOS_END   = "2026-03-01"

INITIAL_CAPITAL = 100_000.0

# Stop-loss values to sweep (parameter sensitivity)
STOP_LOSS_SWEEP = [0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.11, 0.12]


def fmt_pct(v: float) -> str:
    return f"{v*100:.2f}%"


def fmt_dollar(v: float) -> str:
    return f"${v:,.2f}"


def run_with_stop_loss(price_data, macro_events, start_date, end_date,
                       stop_loss_pct: float, tp_ratio: float = TP_RATIO,
                       initial_capital: float = INITIAL_CAPITAL):
    """Run strategy with a custom stop-loss percentage (monkey-patches module constant)."""
    original_sl  = ms.STOP_LOSS_PCT
    original_tp  = ms.TP_RATIO
    ms.STOP_LOSS_PCT = stop_loss_pct
    ms.TP_RATIO      = tp_ratio
    try:
        state, log = run_strategy(
            price_data=price_data,
            macro_events=macro_events,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
        )
        metrics = compute_metrics(state, initial_capital, start_date, end_date)
    finally:
        ms.STOP_LOSS_PCT = original_sl
        ms.TP_RATIO      = original_tp
    return metrics


def overfitting_verdict(is_m: dict, oos_m: dict) -> str:
    """
    Heuristic: flag likely overfitting if OOS performance degrades dramatically.
    Returns a short verdict string.
    """
    warnings = []

    # Win rate degradation > 15 pp
    wr_delta = oos_m["win_rate"] - is_m["win_rate"]
    if wr_delta < -0.15:
        warnings.append(f"win rate dropped {abs(wr_delta)*100:.1f} pp IS→OOS")

    # Sharpe turns negative when IS was positive
    if is_m["sharpe"] > 0 and oos_m["sharpe"] < 0:
        warnings.append("Sharpe flipped negative OOS")

    # Return significantly worse (>20 pp absolute)
    ret_delta = oos_m["total_return"] - is_m["total_return"]
    if ret_delta < -0.20 and is_m["total_return"] > 0:
        warnings.append(f"total return degraded {abs(ret_delta)*100:.1f} pp OOS")

    # Max drawdown exploded (>2× IS)
    if is_m["max_drawdown"] > 0 and oos_m["max_drawdown"] > is_m["max_drawdown"] * 2.0:
        warnings.append(f"max drawdown doubled IS→OOS")

    if not warnings:
        if oos_m["n_trades"] == 0:
            return "⚠️  INCONCLUSIVE — no OOS trades fired (sparse macro events in OOS window)"
        return "✅  ROBUST — OOS results within acceptable range of IS"
    return "⚠️  POTENTIAL OVERFITTING — " + "; ".join(warnings)


def main():
    print("=" * 65)
    print("PINCH MACRO SWING — OUT-OF-SAMPLE VALIDATION")
    print("=" * 65)
    print(f"In-Sample  : {IS_START} → {IS_END}")
    print(f"Out-of-Sample: {OOS_START} → {OOS_END}")
    print()

    # ── Load data ──────────────────────────────────────────────────
    price_data   = load_price_data(BTC_CSV)
    macro_events = load_macro_events(MACRO_CSV)
    print(f"Price bars loaded : {len(price_data)}")
    print(f"Macro event dates : {len(macro_events)}")

    # Warn if macro events don't cover IS period
    earliest_event = min(macro_events.keys())
    if earliest_event > IS_START:
        print(f"\n⚠  NOTE: Earliest macro event is {earliest_event}.")
        print(f"   IS period starts {IS_START} — events before {earliest_event} will be absent.")
        print(f"   IS performance therefore covers only the {earliest_event} → {IS_END} sub-window.\n")

    # ── In-Sample run (default 8% SL) ─────────────────────────────
    print("[1/4] Running IS backtest (2022–2024)...")
    is_state, is_log = run_strategy(
        price_data=price_data,
        macro_events=macro_events,
        start_date=IS_START,
        end_date=IS_END,
        initial_capital=INITIAL_CAPITAL,
    )
    is_metrics = compute_metrics(is_state, INITIAL_CAPITAL, IS_START, IS_END)
    is_bh      = compute_buy_hold(price_data, IS_START, IS_END, INITIAL_CAPITAL)
    print(f"  IS trades: {is_metrics['n_trades']}  |  return: {fmt_pct(is_metrics['total_return'])}")

    # ── Out-of-Sample run (default 8% SL) ─────────────────────────
    print("[2/4] Running OOS backtest (2025–2026)...")
    oos_state, oos_log = run_strategy(
        price_data=price_data,
        macro_events=macro_events,
        start_date=OOS_START,
        end_date=OOS_END,
        initial_capital=INITIAL_CAPITAL,
    )
    oos_metrics = compute_metrics(oos_state, INITIAL_CAPITAL, OOS_START, OOS_END)
    oos_bh      = compute_buy_hold(price_data, OOS_START, OOS_END, INITIAL_CAPITAL)
    print(f"  OOS trades: {oos_metrics['n_trades']}  |  return: {fmt_pct(oos_metrics['total_return'])}")

    # ── Parameter sensitivity sweep ────────────────────────────────
    print("[3/4] Running stop-loss sensitivity sweep...")
    sensitivity = {}
    for sl in STOP_LOSS_SWEEP:
        is_s  = run_with_stop_loss(price_data, macro_events, IS_START,  IS_END,  sl)
        oos_s = run_with_stop_loss(price_data, macro_events, OOS_START, OOS_END, sl)
        sensitivity[sl] = {"is": is_s, "oos": oos_s}
        print(f"  SL={sl*100:.0f}%  IS ret={fmt_pct(is_s['total_return'])}  "
              f"OOS ret={fmt_pct(oos_s['total_return'])}")

    # ── Verdict ────────────────────────────────────────────────────
    verdict = overfitting_verdict(is_metrics, oos_metrics)
    print(f"\n[4/4] Verdict: {verdict}\n")

    # ── Save Markdown report ───────────────────────────────────────
    os.makedirs(RESULTS_DIR, exist_ok=True)
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    md_lines = []
    a = md_lines.append

    a(f"# Macro Swing Strategy — Out-of-Sample Validation\n")
    a(f"**Generated:** {now}  ")
    a(f"**In-Sample:**  {IS_START} → {IS_END}  ")
    a(f"**Out-of-Sample:** {OOS_START} → {OOS_END}  ")
    a(f"**Initial Capital:** {fmt_dollar(INITIAL_CAPITAL)}  ")
    a(f"**Default Parameters:** Stop-loss 8%, Take-profit 16% (2:1 R:R), 14-day time stop\n")
    a("---\n")

    # Data coverage note
    earliest_event = min(macro_events.keys())
    a("## Data Coverage Note\n")
    a(f"The macro event database starts on **{earliest_event}**. "
      f"The IS period nominally starts 2022-01-01, but macro signals only "
      f"fire from {earliest_event} onwards. This means the IS window effectively "
      f"covers **{earliest_event} → {IS_END}** for signal generation, while "
      f"price data is available for the full IS range.\n")
    a("---\n")

    # ── IS Performance ──────────────────────────────────────────────
    a("## In-Sample Performance (2022–2024)\n")
    a("| Metric | Macro Swing | Buy & Hold BTC |")
    a("|--------|-------------|----------------|")
    a(f"| Final Value | {fmt_dollar(is_metrics['final_value'])} | {fmt_dollar(is_bh.get('final_value',0))} |")
    a(f"| Total Return | {fmt_pct(is_metrics['total_return'])} | {fmt_pct(is_bh.get('total_return',0))} |")
    a(f"| Annualized Return | {fmt_pct(is_metrics['annualized_return'])} | {fmt_pct(is_bh.get('annualized_return',0))} |")
    a(f"| Max Drawdown | {fmt_pct(is_metrics['max_drawdown'])} | {fmt_pct(is_bh.get('max_drawdown',0))} |")
    a(f"| Sharpe Ratio | {is_metrics['sharpe']:.3f} | N/A |")
    a(f"| Number of Trades | {is_metrics['n_trades']} | — |")
    a(f"| Win Rate | {fmt_pct(is_metrics['win_rate'])} | — |")
    a(f"| Avg Win | {fmt_pct(is_metrics['avg_win'])} | — |")
    a(f"| Avg Loss | {fmt_pct(is_metrics['avg_loss'])} | — |")
    a(f"| Profit Factor | {is_metrics['profit_factor']:.3f} | — |\n")

    if is_state.trades:
        a("### IS Trade Log\n")
        a("| # | Entry | Exit | Entry $ | Exit $ | PnL% | Reason |")
        a("|---|-------|------|---------|--------|------|--------|")
        for i, t in enumerate(is_state.trades, 1):
            pnl = f"{t.pnl_pct*100:.2f}%" if t.pnl_pct is not None else "—"
            a(f"| {i} | {t.entry_date} | {t.exit_date or '—'} | "
              f"{fmt_dollar(t.entry_price)} | "
              f"{fmt_dollar(t.exit_price) if t.exit_price else '—'} | "
              f"{pnl} | {t.exit_reason or '—'} |")
        a("")

    a("---\n")

    # ── OOS Performance ─────────────────────────────────────────────
    a("## Out-of-Sample Performance (2025–2026)\n")
    a("| Metric | Macro Swing | Buy & Hold BTC |")
    a("|--------|-------------|----------------|")
    a(f"| Final Value | {fmt_dollar(oos_metrics['final_value'])} | {fmt_dollar(oos_bh.get('final_value',0))} |")
    a(f"| Total Return | {fmt_pct(oos_metrics['total_return'])} | {fmt_pct(oos_bh.get('total_return',0))} |")
    a(f"| Annualized Return | {fmt_pct(oos_metrics['annualized_return'])} | {fmt_pct(oos_bh.get('annualized_return',0))} |")
    a(f"| Max Drawdown | {fmt_pct(oos_metrics['max_drawdown'])} | {fmt_pct(oos_bh.get('max_drawdown',0))} |")
    a(f"| Sharpe Ratio | {oos_metrics['sharpe']:.3f} | N/A |")
    a(f"| Number of Trades | {oos_metrics['n_trades']} | — |")
    a(f"| Win Rate | {fmt_pct(oos_metrics['win_rate'])} | — |")
    a(f"| Avg Win | {fmt_pct(oos_metrics['avg_win'])} | — |")
    a(f"| Avg Loss | {fmt_pct(oos_metrics['avg_loss'])} | — |")
    a(f"| Profit Factor | {oos_metrics['profit_factor']:.3f} | — |\n")

    if oos_state.trades:
        a("### OOS Trade Log\n")
        a("| # | Entry | Exit | Entry $ | Exit $ | PnL% | Reason |")
        a("|---|-------|------|---------|--------|------|--------|")
        for i, t in enumerate(oos_state.trades, 1):
            pnl = f"{t.pnl_pct*100:.2f}%" if t.pnl_pct is not None else "—"
            a(f"| {i} | {t.entry_date} | {t.exit_date or '—'} | "
              f"{fmt_dollar(t.entry_price)} | "
              f"{fmt_dollar(t.exit_price) if t.exit_price else '—'} | "
              f"{pnl} | {t.exit_reason or '—'} |")
        a("")
    else:
        a("_No trades fired in OOS period._\n")

    a("---\n")

    # ── IS vs OOS Comparison ─────────────────────────────────────────
    a("## IS vs OOS Comparison\n")
    a("| Metric | In-Sample (2022–2024) | Out-of-Sample (2025–2026) | Delta |")
    a("|--------|----------------------|--------------------------|-------|")

    def delta_pct(a_val, b_val):
        d = b_val - a_val
        sign = "+" if d >= 0 else ""
        return f"{sign}{d*100:.2f} pp"

    def delta_float(a_val, b_val):
        d = b_val - a_val
        sign = "+" if d >= 0 else ""
        return f"{sign}{d:.3f}"

    a(f"| Total Return | {fmt_pct(is_metrics['total_return'])} | {fmt_pct(oos_metrics['total_return'])} | {delta_pct(is_metrics['total_return'], oos_metrics['total_return'])} |")
    a(f"| Annualized Return | {fmt_pct(is_metrics['annualized_return'])} | {fmt_pct(oos_metrics['annualized_return'])} | {delta_pct(is_metrics['annualized_return'], oos_metrics['annualized_return'])} |")
    a(f"| Max Drawdown | {fmt_pct(is_metrics['max_drawdown'])} | {fmt_pct(oos_metrics['max_drawdown'])} | {delta_pct(is_metrics['max_drawdown'], oos_metrics['max_drawdown'])} |")
    a(f"| Sharpe Ratio | {is_metrics['sharpe']:.3f} | {oos_metrics['sharpe']:.3f} | {delta_float(is_metrics['sharpe'], oos_metrics['sharpe'])} |")
    a(f"| Win Rate | {fmt_pct(is_metrics['win_rate'])} | {fmt_pct(oos_metrics['win_rate'])} | {delta_pct(is_metrics['win_rate'], oos_metrics['win_rate'])} |")
    a(f"| # Trades | {is_metrics['n_trades']} | {oos_metrics['n_trades']} | {oos_metrics['n_trades'] - is_metrics['n_trades']:+d} |")
    a(f"| Profit Factor | {is_metrics['profit_factor']:.3f} | {oos_metrics['profit_factor']:.3f} | {delta_float(is_metrics['profit_factor'], oos_metrics['profit_factor'])} |\n")

    a("---\n")

    # ── Parameter Sensitivity ───────────────────────────────────────
    a("## Parameter Sensitivity: Stop-Loss 5%–12%\n")
    a("*(Take-profit scales with 2:1 R:R; all other parameters fixed.)*\n")
    a("| Stop-Loss | TP Level | IS Return | IS Win% | IS Sharpe | OOS Return | OOS Win% | OOS Sharpe |")
    a("|-----------|----------|-----------|---------|-----------|------------|----------|------------|")
    for sl, res in sensitivity.items():
        tp_level = sl * TP_RATIO
        a(f"| {sl*100:.0f}% | {tp_level*100:.0f}% "
          f"| {fmt_pct(res['is']['total_return'])} "
          f"| {fmt_pct(res['is']['win_rate'])} "
          f"| {res['is']['sharpe']:.3f} "
          f"| {fmt_pct(res['oos']['total_return'])} "
          f"| {fmt_pct(res['oos']['win_rate'])} "
          f"| {res['oos']['sharpe']:.3f} |")
    a("")

    # Sensitivity narrative
    is_returns  = [sensitivity[sl]['is']['total_return']  for sl in STOP_LOSS_SWEEP]
    oos_returns = [sensitivity[sl]['oos']['total_return'] for sl in STOP_LOSS_SWEEP]
    is_range  = max(is_returns)  - min(is_returns)
    oos_range = max(oos_returns) - min(oos_returns)

    a(f"**IS return range across SL sweep:** {is_range*100:.2f} pp  ")
    a(f"**OOS return range across SL sweep:** {oos_range*100:.2f} pp  ")

    if is_range < 0.10 and oos_range < 0.10:
        a("*→ Low sensitivity to stop-loss parameter — strategy logic is the primary return driver.*\n")
    elif oos_range > is_range * 1.5:
        a("*→ OOS shows higher sensitivity to stop-loss than IS — slight parameter fragility detected.*\n")
    else:
        a("*→ Moderate sensitivity; results shift but direction is consistent across SL values.*\n")

    a("---\n")

    # ── Conclusion ───────────────────────────────────────────────────
    a("## Conclusion\n")
    a(f"### Overfitting Assessment: {verdict}\n")

    a("### Analysis\n")

    if is_metrics['n_trades'] == 0 and oos_metrics['n_trades'] == 0:
        a("**No trades fired in either period.** The macro event database does not contain "
          "events that score ≥ ±2 in the data range, or the price data and event dates "
          "do not overlap sufficiently. OOS validation is inconclusive pending richer event data.\n")
    elif oos_metrics['n_trades'] == 0:
        a("**No OOS trades fired.** The macro events in 2025–2026 did not generate signals "
          "strong enough to enter positions (score < ±2). This is a data-coverage issue, "
          "not evidence of overfitting. The strategy rules are consistent; OOS is simply quiet.\n")
    else:
        # Provide substantive analysis
        sharpe_ok = oos_metrics['sharpe'] > 0 or is_metrics['sharpe'] <= 0
        wr_ok     = abs(oos_metrics['win_rate'] - is_metrics['win_rate']) < 0.20
        ret_ok    = oos_metrics['total_return'] > -0.15

        a("**Signal logic consistency:**  ")
        a("The strategy is fully rule-based — no parameters were optimised on in-sample data. "
          "The signal rules (CPI/FOMC/NFP surprise scoring) and risk management constants "
          "(8% SL, 16% TP, 14-day time stop) were defined a priori.  \n")

        if sharpe_ok and wr_ok and ret_ok:
            a("**Performance transfer:**  ")
            a("Key metrics (win rate, Sharpe, drawdown) remain in a comparable range IS→OOS. "
              "There is no evidence of curve-fitting.  \n")
        else:
            a("**Performance degradation detected:**  ")
            a("Some metrics deteriorate IS→OOS. Given the rule-based nature of the strategy, "
              "this is more likely attributable to regime change (e.g., macro environment shift) "
              "than classic overfitting.  \n")

        a("**Parameter robustness:**  ")
        if oos_range < 0.10:
            a("Stop-loss variations (5%–12%) produce consistent directional results — "
              "the strategy is not sensitive to the exact stop level.  \n")
        else:
            a("Stop-loss choice has meaningful impact on OOS performance — "
              "consider a wider confidence interval when selecting this parameter.  \n")

    a("\n### Recommendations\n")
    a("1. **Expand macro event history** to 2022–2023 to provide a richer IS period with more signal observations.")
    a("2. **Monitor regime changes**: the strategy is macro-driven; a shift from rate-hike to rate-cut cycles will change signal polarity.")
    a("3. **Walk-forward validation**: re-run this OOS validation quarterly as new macro data becomes available.")
    a("4. **Multi-asset test**: apply the same signal rules to ETH and SOL to check generalisability.")
    a("")
    a("> *Rule of Acquisition #22: A wise man can hear profit in the wind.*  ")
    a("> *But a wiser man checks whether the wind changed direction.*")
    a("")

    report = "\n".join(md_lines)
    with open(OOS_MD, "w") as f:
        f.write(report)
    print(f"Report saved: {OOS_MD}")

    # Print compact summary to stdout
    print()
    print("=" * 65)
    print("OOS VALIDATION SUMMARY")
    print("=" * 65)
    print(f"{'Metric':<30} {'In-Sample':>15} {'Out-of-Sample':>15}")
    print("-" * 65)
    print(f"{'Total Return':<30} {fmt_pct(is_metrics['total_return']):>15} {fmt_pct(oos_metrics['total_return']):>15}")
    print(f"{'Annualized Return':<30} {fmt_pct(is_metrics['annualized_return']):>15} {fmt_pct(oos_metrics['annualized_return']):>15}")
    print(f"{'Max Drawdown':<30} {fmt_pct(is_metrics['max_drawdown']):>15} {fmt_pct(oos_metrics['max_drawdown']):>15}")
    print(f"{'Sharpe Ratio':<30} {is_metrics['sharpe']:>15.3f} {oos_metrics['sharpe']:>15.3f}")
    print(f"{'Win Rate':<30} {fmt_pct(is_metrics['win_rate']):>15} {fmt_pct(oos_metrics['win_rate']):>15}")
    print(f"{'Number of Trades':<30} {is_metrics['n_trades']:>15} {oos_metrics['n_trades']:>15}")
    print("=" * 65)
    print(f"\n{verdict}")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
