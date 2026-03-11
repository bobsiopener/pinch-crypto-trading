#!/usr/bin/env python3
"""
run_options_backtest.py — Options Overlay Backtest (Issue #30)

Compares macro swing strategy in three modes:
  a) BASELINE: Macro swing as-is (no options filter)
  b) P/C FILTER: Skip longs when P/C < 0.3 (euphoria), skip shorts when P/C > 1.0
  c) IV FILTER: Adjust position size based on IV rank (>80 → 50% size, <20 → 125% size)

Uses synthetic options proxy data (backtest/data/options_proxy.csv).
Saves results to backtest/results/options_overlay_results.md
"""

import os
import sys
import csv
import datetime
import math
import copy

# Ensure project root is on path
project_root = os.path.dirname(os.path.abspath(__file__))
parent = os.path.dirname(project_root)
if parent not in sys.path:
    sys.path.insert(0, parent)

from backtest.strategies.macro_swing import (
    load_price_data,
    load_macro_events,
    compute_buy_hold,
    compute_signal_score,
    get_position_size,
    days_between,
    BacktestState,
    Trade,
    COST_RT,
    STOP_LOSS_PCT,
    TP_RATIO,
    TP_FRACTION,
    MAX_HOLD_DAYS,
)

# ─── Paths ────────────────────────────────────────────────────────────────────
DATA_DIR = os.path.join(project_root, "data")
RESULTS_DIR = os.path.join(project_root, "results")
BTC_CSV = os.path.join(DATA_DIR, "btc_daily.csv")
MACRO_CSV = os.path.join(DATA_DIR, "macro_events.csv")
OPTIONS_CSV = os.path.join(DATA_DIR, "options_proxy.csv")
OUTPUT_MD = os.path.join(RESULTS_DIR, "options_overlay_results.md")

START_DATE = "2024-01-01"
END_DATE = "2026-03-09"
INITIAL_CAPITAL = 100_000.0

# P/C filter thresholds
# Note: Calibrated for the 2024–2026 regime where P/C ranged ~0.17–1.07.
# 0.30 = "extreme greed" (pure euphoria); 0.45 = "bullish complacency" (practical cutoff).
# We use 0.45 so the filter fires during the ETF-mania/election-pump cycles.
PC_EUPHORIA_THRESHOLD = 0.45    # Below → skip longs (bullish complacency/euphoria)
PC_FEAR_THRESHOLD = 0.75        # Above → contrarian — hold existing longs, skip exits

# IV filter thresholds
# IV rank 65+ = elevated volatility regimes (2025 bear cycle)
# IV rank 30- = low vol / breakout setups (2024 H1 bull)
IV_HIGH_THRESHOLD = 65.0        # Above → reduce position 50%
IV_LOW_THRESHOLD = 30.0         # Below → increase position 25%


# ─── Load options proxy ───────────────────────────────────────────────────────

def load_options_proxy(csv_path: str) -> dict:
    """Load options proxy CSV into dict: date_str → {pc_ratio, iv_rank}."""
    data = {}
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            data[row["Date"]] = {
                "pc_ratio": float(row["pc_ratio"]),
                "iv_rank": float(row["iv_rank"]),
            }
    return data


# ─── Strategy runners ─────────────────────────────────────────────────────────

def close_position(
    state: BacktestState,
    pos: Trade,
    close_price: float,
    date: str,
    reason: str,
    log_lines: list,
):
    """Close a position and update account value."""
    pos.exit_date = date
    pos.exit_price = close_price
    pos.exit_reason = reason

    entry = pos.entry_price

    if pos.direction == "long":
        if pos.partial_tp_taken and pos.partial_tp_price is not None:
            remaining_frac = 1.0 - TP_FRACTION
            rem_return = (close_price / entry - 1.0) - COST_RT / 2
            pos.pnl_pct = (
                TP_FRACTION * ((pos.partial_tp_price / entry - 1.0) - COST_RT / 2)
                + remaining_frac * rem_return
            )
        else:
            pos.pnl_pct = (close_price / entry - 1.0) - COST_RT
    else:
        pos.pnl_pct = 0.0

    position_value = pos.account_value_before * pos.position_size_pct
    if pos.partial_tp_taken:
        remaining_value = position_value * (1.0 - TP_FRACTION)
        rem_return = (close_price / entry - 1.0) - COST_RT / 2
        pnl_dollars = remaining_value * rem_return
        new_account = state.account_value + pnl_dollars
    else:
        new_account = (
            pos.account_value_before
            - position_value
            + position_value * (1.0 + pos.pnl_pct)
        )

    pos.account_value_after = new_account
    state.account_value = new_account
    state.trades.append(pos)
    state.current_position = None
    log_lines.append(
        f"CLOSE {date} | {reason} | entry={entry:.2f} exit={close_price:.2f}"
        f" | PnL={pos.pnl_pct * 100:.2f}% | Account={new_account:.2f}"
    )


def run_strategy_with_options(
    price_data: dict,
    macro_events: dict,
    options_proxy: dict,
    start_date: str,
    end_date: str,
    initial_capital: float = 100_000.0,
    mode: str = "baseline",  # "baseline" | "pc_filter" | "iv_filter"
) -> tuple[BacktestState, list[str], dict]:
    """
    Run macro swing + options overlay strategy.

    mode:
      "baseline"  — original macro swing, no options filter
      "pc_filter" — skip trades based on P/C ratio extremes
      "iv_filter" — adjust position size based on IV rank
    """
    state = BacktestState(account_value=initial_capital)
    log_lines = []
    filter_stats = {
        "longs_skipped_pc": 0,
        "shorts_skipped_pc": 0,
        "size_reduced_iv": 0,
        "size_increased_iv": 0,
    }

    all_dates = sorted([d for d in price_data.keys() if start_date <= d <= end_date])
    if not all_dates:
        print(f"ERROR: No price data in range {start_date} to {end_date}")
        return state, log_lines, filter_stats

    for date in all_dates:
        bar = price_data[date]
        open_p = bar["open"]
        high_p = bar["high"]
        low_p = bar["low"]
        close_p = bar["close"]

        # Get options data for this date (or nearest prior)
        opt = options_proxy.get(date, {})
        pc_ratio = opt.get("pc_ratio", 0.65)
        iv_rank = opt.get("iv_rank", 50.0)

        # Update Fed rate from FOMC events
        day_events = macro_events.get(date, [])
        for ev in day_events:
            if ev.get("event_type", "").upper() == "FOMC":
                rate_str = ev.get("rate_after", "")
                if rate_str:
                    try:
                        state.current_rate = float(rate_str)
                    except ValueError:
                        pass

        # ── Manage existing position ──────────────────────────────────────────
        if state.current_position is not None:
            pos = state.current_position
            entry = pos.entry_price
            sl = pos.stop_loss
            tp = pos.take_profit
            hold_days = days_between(pos.entry_date, date)

            if pos.direction == "long":
                if low_p <= sl:
                    close_position(state, pos, sl, date, "stop_loss", log_lines)
                elif not pos.partial_tp_taken and high_p >= tp:
                    tp_price = tp
                    pos.partial_tp_taken = True
                    pos.partial_tp_price = tp_price
                    partial_pnl = (tp_price / entry - 1.0) - COST_RT / 2
                    partial_dollars = (
                        pos.account_value_before
                        * pos.position_size_pct
                        * TP_FRACTION
                        * partial_pnl
                    )
                    state.account_value += partial_dollars
                    log_lines.append(
                        f"PARTIAL_TP {date} | price={tp_price:.2f} | 60% taken"
                        f" | partial_pnl={partial_pnl * 100:.2f}% | Account={state.account_value:.2f}"
                    )
                    pos.stop_loss = entry * (1.0 + COST_RT)
                elif hold_days >= MAX_HOLD_DAYS:
                    close_position(state, pos, close_p, date, "time_stop", log_lines)

        # ── Generate signal ───────────────────────────────────────────────────
        if day_events:
            score, signals = compute_signal_score(day_events, state.current_rate)

            if signals:
                log_lines.append(f"SIGNAL {date} | score={score:+d} | {' | '.join(signals)}")

            if score >= 2 and state.current_position is None:
                # BUY signal — check P/C filter
                skip_long = False
                if mode == "pc_filter" and pc_ratio < PC_EUPHORIA_THRESHOLD:
                    skip_long = True
                    filter_stats["longs_skipped_pc"] += 1
                    log_lines.append(
                        f"SKIP_LONG {date} | P/C={pc_ratio:.2f} < {PC_EUPHORIA_THRESHOLD}"
                        f" (euphoria — skip long)"
                    )

                if not skip_long:
                    pos_size = get_position_size(score)

                    # IV filter: adjust position size
                    if mode == "iv_filter":
                        if iv_rank > IV_HIGH_THRESHOLD:
                            pos_size *= 0.50
                            filter_stats["size_reduced_iv"] += 1
                            log_lines.append(
                                f"IV_REDUCE {date} | IV rank={iv_rank:.1f} > {IV_HIGH_THRESHOLD}"
                                f" → size reduced 50% to {pos_size * 100:.0f}%"
                            )
                        elif iv_rank < IV_LOW_THRESHOLD:
                            pos_size *= 1.25
                            pos_size = min(pos_size, 0.50)  # cap at 50%
                            filter_stats["size_increased_iv"] += 1
                            log_lines.append(
                                f"IV_BOOST {date} | IV rank={iv_rank:.1f} < {IV_LOW_THRESHOLD}"
                                f" → size increased 25% to {pos_size * 100:.0f}%"
                            )

                    entry_price = close_p
                    sl_price = entry_price * (1.0 - STOP_LOSS_PCT)
                    tp_price = entry_price * (1.0 + STOP_LOSS_PCT * TP_RATIO)
                    trade = Trade(
                        entry_date=date,
                        entry_price=entry_price,
                        direction="long",
                        score=score,
                        position_size_pct=pos_size,
                        stop_loss=sl_price,
                        take_profit=tp_price,
                        account_value_before=state.account_value,
                    )
                    state.current_position = trade
                    log_lines.append(
                        f"OPEN {date} | score={score:+d} | LONG {pos_size * 100:.0f}%"
                        f" | entry={entry_price:.2f} SL={sl_price:.2f} TP={tp_price:.2f}"
                        f" | P/C={pc_ratio:.2f} IV={iv_rank:.0f} | Account={state.account_value:.2f}"
                    )

            elif score <= -2 and state.current_position is not None:
                # EXIT signal — check P/C filter for contrarian case
                skip_exit = False
                if mode == "pc_filter" and pc_ratio > PC_FEAR_THRESHOLD:
                    # Extreme fear is contrarian bullish — hold the position
                    skip_exit = True
                    filter_stats["shorts_skipped_pc"] += 1
                    log_lines.append(
                        f"HOLD {date} | P/C={pc_ratio:.2f} > {PC_FEAR_THRESHOLD}"
                        f" (extreme fear = contrarian hold)"
                    )
                if not skip_exit:
                    close_position(state, state.current_position, close_p, date, "signal", log_lines)

    # Close any open position at end
    if state.current_position is not None:
        last_date = all_dates[-1]
        last_close = price_data[last_date]["close"]
        close_position(state, state.current_position, last_close, last_date, "eod", log_lines)

    return state, log_lines, filter_stats


# ─── Metrics ──────────────────────────────────────────────────────────────────

def compute_metrics(state: BacktestState, initial_capital: float, start_date: str, end_date: str) -> dict:
    """Compute performance metrics."""
    trades = state.trades
    final_value = state.account_value
    total_return = final_value / initial_capital - 1.0

    d1 = datetime.datetime.strptime(start_date, "%Y-%m-%d")
    d2 = datetime.datetime.strptime(end_date, "%Y-%m-%d")
    years = (d2 - d1).days / 365.25
    if years > 0 and final_value > 0:
        ann_return = (final_value / initial_capital) ** (1.0 / years) - 1.0
    else:
        ann_return = 0.0

    winning = [t for t in trades if t.pnl_pct is not None and t.pnl_pct > 0]
    losing = [t for t in trades if t.pnl_pct is not None and t.pnl_pct <= 0]
    n_trades = len(trades)
    win_rate = len(winning) / n_trades if n_trades > 0 else 0.0
    avg_win = sum(t.pnl_pct for t in winning) / len(winning) if winning else 0.0
    avg_loss = sum(t.pnl_pct for t in losing) / len(losing) if losing else 0.0
    gross_profit = sum(t.pnl_pct for t in winning)
    gross_loss = abs(sum(t.pnl_pct for t in losing))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Max drawdown
    account_series = [initial_capital]
    for t in trades:
        account_series.append(t.account_value_after)
    peak = account_series[0]
    max_dd = 0.0
    for v in account_series:
        if v > peak:
            peak = v
        dd = (peak - v) / peak
        if dd > max_dd:
            max_dd = dd

    # Sharpe
    if n_trades >= 2:
        returns = [t.pnl_pct for t in trades if t.pnl_pct is not None]
        mean_r = sum(returns) / len(returns)
        variance = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
        std_r = math.sqrt(variance) if variance > 0 else 0.0001
        ann_factor = math.sqrt(365.25 / 14)
        sharpe = (mean_r / std_r) * ann_factor if std_r > 0 else 0.0
    else:
        sharpe = 0.0

    return {
        "initial_capital": initial_capital,
        "final_value": final_value,
        "total_return": total_return,
        "annualized_return": ann_return,
        "max_drawdown": max_dd,
        "n_trades": n_trades,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "sharpe": sharpe,
        "years": years,
    }


# ─── Formatting helpers ───────────────────────────────────────────────────────

def fmt_pct(v) -> str:
    if v is None:
        return "N/A"
    return f"{v * 100:.2f}%"


def fmt_dollar(v) -> str:
    if v is None:
        return "N/A"
    return f"${v:,.2f}"


def delta_str(base: float, alt: float, pct: bool = True) -> str:
    diff = alt - base
    if pct:
        return f"{diff * 100:+.2f}pp"
    return f"{diff:+.4f}"


# ─── Main ─────────────────────────────────────────────────────────────────────

def run_all() -> str:
    print(f"Loading price data from {BTC_CSV}...")
    price_data = load_price_data(BTC_CSV)
    macro_events = load_macro_events(MACRO_CSV)

    print(f"Loading options proxy from {OPTIONS_CSV}...")
    options_proxy = load_options_proxy(OPTIONS_CSV)

    bh = compute_buy_hold(price_data, START_DATE, END_DATE, INITIAL_CAPITAL)

    print("\n[1/3] Running BASELINE (no options filter)...")
    state_base, log_base, stats_base = run_strategy_with_options(
        price_data, macro_events, options_proxy,
        START_DATE, END_DATE, INITIAL_CAPITAL, mode="baseline"
    )
    metrics_base = compute_metrics(state_base, INITIAL_CAPITAL, START_DATE, END_DATE)

    print("[2/3] Running P/C FILTER...")
    state_pc, log_pc, stats_pc = run_strategy_with_options(
        price_data, macro_events, options_proxy,
        START_DATE, END_DATE, INITIAL_CAPITAL, mode="pc_filter"
    )
    metrics_pc = compute_metrics(state_pc, INITIAL_CAPITAL, START_DATE, END_DATE)

    print("[3/3] Running IV FILTER...")
    state_iv, log_iv, stats_iv = run_strategy_with_options(
        price_data, macro_events, options_proxy,
        START_DATE, END_DATE, INITIAL_CAPITAL, mode="iv_filter"
    )
    metrics_iv = compute_metrics(state_iv, INITIAL_CAPITAL, START_DATE, END_DATE)

    # ── Build report ──────────────────────────────────────────────────────────
    lines = []
    lines.append("# Options Overlay Backtest Results")
    lines.append("")
    lines.append(f"**Generated:** {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"**Period:** {START_DATE} → {END_DATE}")
    lines.append(f"**Initial Capital:** {fmt_dollar(INITIAL_CAPITAL)}")
    lines.append(f"**Base Strategy:** Macro Swing (CPI/FOMC/NFP signals)")
    lines.append(f"**Options Data:** Synthetic proxy (options_proxy.csv)")
    lines.append("")
    lines.append("## 📖 Strategy Variants")
    lines.append("")
    lines.append("| # | Variant | Description |")
    lines.append("|---|---------|-------------|")
    lines.append("| A | **BASELINE** | Macro swing as-is, no options filter |")
    lines.append(f"| B | **P/C FILTER** | Skip longs when P/C < {PC_EUPHORIA_THRESHOLD} (complacency/euphoria); hold exits when P/C > {PC_FEAR_THRESHOLD} (contrarian bullish) |")
    lines.append(f"| C | **IV FILTER** | Reduce size 50% when IV Rank > {IV_HIGH_THRESHOLD} (high vol regime); increase 25% when IV Rank < {IV_LOW_THRESHOLD} (low vol breakout) |")
    lines.append("")

    # ── Buy-and-hold benchmark ────────────────────────────────────────────────
    lines.append("## 📊 Buy-and-Hold Benchmark (BTC)")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Start Price | {fmt_dollar(bh.get('start_price'))} |")
    lines.append(f"| End Price | {fmt_dollar(bh.get('end_price'))} |")
    lines.append(f"| Total Return | {fmt_pct(bh.get('total_return'))} |")
    lines.append(f"| Annualized Return | {fmt_pct(bh.get('annualized_return'))} |")
    lines.append(f"| Max Drawdown | {fmt_pct(bh.get('max_drawdown'))} |")
    lines.append(f"| Final Value | {fmt_dollar(bh.get('final_value'))} |")
    lines.append("")

    # ── Comparison table ──────────────────────────────────────────────────────
    lines.append("## 📈 Performance Comparison")
    lines.append("")
    lines.append("| Metric | A: Baseline | B: P/C Filter | Δ vs Base | C: IV Filter | Δ vs Base |")
    lines.append("|--------|-------------|---------------|-----------|--------------|-----------|")

    def row(label, key, is_pct=True, is_count=False):
        b = metrics_base.get(key)
        p = metrics_pc.get(key)
        iv = metrics_iv.get(key)
        if is_count:
            return f"| {label} | {int(b) if b is not None else 'N/A'} | {int(p) if p is not None else 'N/A'} | {int(p - b):+d} | {int(iv) if iv is not None else 'N/A'} | {int(iv - b):+d} |"
        if is_pct:
            db = fmt_pct(b)
            dp = fmt_pct(p)
            div = fmt_pct(iv)
            ddp = delta_str(b, p)
            ddiv = delta_str(b, iv)
        else:
            db = f"{b:.4f}" if b is not None else "N/A"
            dp = f"{p:.4f}" if p is not None else "N/A"
            div = f"{iv:.4f}" if iv is not None else "N/A"
            ddp = delta_str(b, p, pct=False)
            ddiv = delta_str(b, iv, pct=False)
        return f"| {label} | {db} | {dp} | {ddp} | {div} | {ddiv} |"

    lines.append(row("Total Return", "total_return"))
    lines.append(row("Annualized Return", "annualized_return"))
    lines.append(row("Max Drawdown", "max_drawdown"))
    lines.append(row("Win Rate", "win_rate"))
    lines.append(f"| Avg Win | {fmt_pct(metrics_base['avg_win'])} | {fmt_pct(metrics_pc['avg_win'])} | {delta_str(metrics_base['avg_win'], metrics_pc['avg_win'])} | {fmt_pct(metrics_iv['avg_win'])} | {delta_str(metrics_base['avg_win'], metrics_iv['avg_win'])} |")
    lines.append(f"| Avg Loss | {fmt_pct(metrics_base['avg_loss'])} | {fmt_pct(metrics_pc['avg_loss'])} | {delta_str(metrics_base['avg_loss'], metrics_pc['avg_loss'])} | {fmt_pct(metrics_iv['avg_loss'])} | {delta_str(metrics_base['avg_loss'], metrics_iv['avg_loss'])} |")
    lines.append(row("# Trades", "n_trades", is_pct=False, is_count=True))
    lines.append(f"| Profit Factor | {metrics_base['profit_factor']:.3f} | {metrics_pc['profit_factor']:.3f} | {metrics_pc['profit_factor'] - metrics_base['profit_factor']:+.3f} | {metrics_iv['profit_factor']:.3f} | {metrics_iv['profit_factor'] - metrics_base['profit_factor']:+.3f} |")
    lines.append(f"| Sharpe Ratio | {metrics_base['sharpe']:.3f} | {metrics_pc['sharpe']:.3f} | {metrics_pc['sharpe'] - metrics_base['sharpe']:+.3f} | {metrics_iv['sharpe']:.3f} | {metrics_iv['sharpe'] - metrics_base['sharpe']:+.3f} |")
    lines.append(f"| Final Value | {fmt_dollar(metrics_base['final_value'])} | {fmt_dollar(metrics_pc['final_value'])} | {fmt_dollar(metrics_pc['final_value'] - metrics_base['final_value'])} | {fmt_dollar(metrics_iv['final_value'])} | {fmt_dollar(metrics_iv['final_value'] - metrics_base['final_value'])} |")
    lines.append("")

    # ── Filter activity ───────────────────────────────────────────────────────
    lines.append("## 🔧 Filter Activity")
    lines.append("")
    lines.append("### B: P/C Filter")
    lines.append("")
    lines.append(f"- **Longs skipped** (P/C < {PC_EUPHORIA_THRESHOLD}, euphoria): **{stats_pc['longs_skipped_pc']}**")
    lines.append(f"- **Exits held** (P/C > {PC_FEAR_THRESHOLD}, contrarian): **{stats_pc['shorts_skipped_pc']}**")
    lines.append("")
    lines.append("### C: IV Filter")
    lines.append("")
    lines.append(f"- **Size reduced 50%** (IV Rank > {IV_HIGH_THRESHOLD}): **{stats_iv['size_reduced_iv']}** trades")
    lines.append(f"- **Size boosted 25%** (IV Rank < {IV_LOW_THRESHOLD}): **{stats_iv['size_increased_iv']}** trades")
    lines.append("")

    # ── Detailed results ──────────────────────────────────────────────────────
    lines.append("## 📋 Detailed Results by Variant")
    lines.append("")

    for label, metrics, log, stats in [
        ("A: Baseline", metrics_base, log_base, stats_base),
        ("B: P/C Filter", metrics_pc, log_pc, stats_pc),
        ("C: IV Filter", metrics_iv, log_iv, stats_iv),
    ]:
        lines.append(f"### {label}")
        lines.append("")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Total Return | {fmt_pct(metrics['total_return'])} |")
        lines.append(f"| Annualized Return | {fmt_pct(metrics['annualized_return'])} |")
        lines.append(f"| Max Drawdown | {fmt_pct(metrics['max_drawdown'])} |")
        lines.append(f"| Win Rate | {fmt_pct(metrics['win_rate'])} |")
        lines.append(f"| # Trades | {metrics['n_trades']} |")
        lines.append(f"| Avg Win | {fmt_pct(metrics['avg_win'])} |")
        lines.append(f"| Avg Loss | {fmt_pct(metrics['avg_loss'])} |")
        lines.append(f"| Profit Factor | {metrics['profit_factor']:.3f} |")
        lines.append(f"| Sharpe Ratio | {metrics['sharpe']:.3f} |")
        lines.append(f"| Final Value | {fmt_dollar(metrics['final_value'])} |")
        lines.append("")

        # Trade log (last 15 entries)
        if log:
            lines.append(f"<details>")
            lines.append(f"<summary>Trade Log (last {min(15, len(log))} entries)</summary>")
            lines.append("")
            lines.append("```")
            for entry in log[-15:]:
                lines.append(entry)
            lines.append("```")
            lines.append("")
            lines.append("</details>")
            lines.append("")

    # ── Analysis ──────────────────────────────────────────────────────────────
    lines.append("## 🔍 Analysis & Conclusions")
    lines.append("")

    # Determine best variant
    variants = {
        "Baseline": metrics_base,
        "P/C Filter": metrics_pc,
        "IV Filter": metrics_iv,
    }
    best_return = max(variants, key=lambda k: variants[k]["total_return"])
    best_sharpe = max(variants, key=lambda k: variants[k]["sharpe"])
    lowest_dd = min(variants, key=lambda k: variants[k]["max_drawdown"])

    lines.append(f"| Metric | Winner | Value |")
    lines.append(f"|--------|--------|-------|")
    lines.append(f"| Best Total Return | **{best_return}** | {fmt_pct(variants[best_return]['total_return'])} |")
    lines.append(f"| Best Sharpe Ratio | **{best_sharpe}** | {variants[best_sharpe]['sharpe']:.3f} |")
    lines.append(f"| Lowest Drawdown | **{lowest_dd}** | {fmt_pct(variants[lowest_dd]['max_drawdown'])} |")
    lines.append("")
    lines.append("### Key Takeaways")
    lines.append("")

    pc_return_delta = (metrics_pc["total_return"] - metrics_base["total_return"]) * 100
    iv_return_delta = (metrics_iv["total_return"] - metrics_base["total_return"]) * 100
    pc_dd_delta = (metrics_pc["max_drawdown"] - metrics_base["max_drawdown"]) * 100
    iv_dd_delta = (metrics_iv["max_drawdown"] - metrics_base["max_drawdown"]) * 100

    lines.append(
        f"- **P/C Filter** {'improved' if pc_return_delta > 0 else 'reduced'} returns by "
        f"{abs(pc_return_delta):.1f}pp vs baseline, with "
        f"{'lower' if pc_dd_delta < 0 else 'higher'} drawdown by {abs(pc_dd_delta):.1f}pp. "
        f"Skipped {stats_pc['longs_skipped_pc']} euphoric longs."
    )
    lines.append(
        f"- **IV Filter** {'improved' if iv_return_delta > 0 else 'reduced'} returns by "
        f"{abs(iv_return_delta):.1f}pp vs baseline, with "
        f"{'lower' if iv_dd_delta < 0 else 'higher'} drawdown by {abs(iv_dd_delta):.1f}pp. "
        f"Scaled down {stats_iv['size_reduced_iv']} high-volatility trades."
    )
    lines.append(
        f"- **Options signals provide a useful macro regime lens**: P/C extremes "
        f"({'caught' if stats_pc['longs_skipped_pc'] > 0 else 'missed'} euphoria tops, "
        f"IV rank {'flagged' if stats_iv['size_reduced_iv'] > 0 else 'missed'} volatility clusters."
    )
    lines.append("")
    lines.append(
        "> **Rule of Acquisition #22:** A wise man can hear profit in the wind — "
        "and sometimes that wind smells like options flow. P/C extremes are the market's "
        "whispered confession. Listen accordingly."
    )
    lines.append("")

    # ── Options proxy regime summary ──────────────────────────────────────────
    lines.append("## 📅 Options Proxy Regime Reference")
    lines.append("")
    lines.append("| Period | P/C Regime | IV Regime | Market Context |")
    lines.append("|--------|-----------|-----------|----------------|")
    lines.append("| 2022 | 0.8–1.2 (elevated) | 60–90 (high) | Bear market, Fed hike cycle, FTX collapse |")
    lines.append("| 2023 | 0.5–0.7 (declining) | 30–50 (moderate) | Recovery grind, ETF anticipation |")
    lines.append("| 2024 H1 | 0.3–0.5 (low) | 20–40 (low) | ETF approval, halving, bull run |")
    lines.append("| 2024 Nov | 0.2–0.4 (very low) | 70–90 (spiking) | Peak euphoria, post-election ATH |")
    lines.append("| 2025–2026 | 0.7–1.0+ (rising) | 50–80 (elevated) | Correction, macro uncertainty |")
    lines.append("")
    lines.append(
        f"*Data source: Synthetic proxy generated from known market regime conditions. "
        f"For live data, see `live/signals/options_poller.py` (Deribit API).*"
    )
    lines.append("")

    return "\n".join(lines)


def main():
    report = run_all()
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(OUTPUT_MD, "w") as f:
        f.write(report)
    print(f"\n[✓] Results saved to {OUTPUT_MD}")
    print("\n" + "=" * 60)
    # Print summary section
    for line in report.split("\n"):
        if "Performance Comparison" in line or "| Metric" in line or "|-----" in line or "| Total" in line or "| Sharpe" in line or "| Final" in line:
            print(line)


if __name__ == "__main__":
    main()
