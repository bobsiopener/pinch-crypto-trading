"""
Max Pain Expiry Strategy Backtest
Runs 2022-01-01 through 2026-03-01 on BTC daily data.
"""

import csv
import math
import sys
from datetime import date, timedelta
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / 'backtest' / 'data'
RESULTS_DIR = REPO_ROOT / 'backtest' / 'results'
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(REPO_ROOT / 'backtest' / 'strategies'))
from maxpain_expiry import MaxPainExpiryStrategy


# ── Load BTC daily data ───────────────────────────────────────────────────────
def load_btc(path):
    rows = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            d = date.fromisoformat(row['date'])
            rows[d] = {
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close']),
            }
    return rows


# ── Load max pain proxy ───────────────────────────────────────────────────────
def load_maxpain(path):
    """Returns dict: expiry_date -> record"""
    rows = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            d = date.fromisoformat(row['expiry_date'])
            rows[d] = {
                'max_pain': float(row['max_pain']),
                'btc_price_at_start_of_week': float(row['btc_price_at_start_of_week']),
                'btc_price_at_expiry': float(row['btc_price_at_expiry']),
                'is_quarterly': row['is_quarterly'] == '1',
            }
    return rows


def last_friday_of_month(year, month):
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    last_day = next_month - timedelta(days=1)
    offset = (last_day.weekday() - 4) % 7
    return last_day - timedelta(days=offset)


# ── Build expiry calendar ─────────────────────────────────────────────────────
def build_expiry_calendar():
    """
    For each trading date, return metadata about its relation to option expiry.
    Returns dict: date -> {
        expiry_friday, max_pain, days_to_expiry,
        is_expiry_week, is_post_expiry_monday, is_quarterly
    }
    """
    expiries = []
    for year in range(2022, 2027):
        for month in range(1, 13):
            expiries.append(last_friday_of_month(year, month))

    calendar = {}
    for i, exp_fri in enumerate(expiries):
        mon_of_week = exp_fri - timedelta(days=4)   # Monday = Friday - 4
        post_mon = exp_fri + timedelta(days=3)      # Monday after = Friday + 3
        is_quarterly = exp_fri.month in {3, 6, 9, 12}

        # Mark Mon–Fri of expiry week
        for offset in range(5):   # Mon=0 ... Fri=4
            d = mon_of_week + timedelta(days=offset)
            days_to_expiry = offset - 4  # Mon=-4, Tue=-3, ..., Fri=0
            calendar[d] = {
                'expiry_friday': exp_fri,
                'max_pain': None,  # filled from proxy
                'days_to_expiry': days_to_expiry,
                'is_expiry_week': True,
                'is_post_expiry_monday': False,
                'is_quarterly': is_quarterly,
            }

        # Post-expiry Monday
        calendar[post_mon] = {
            'expiry_friday': exp_fri,
            'max_pain': None,
            'days_to_expiry': 3,
            'is_expiry_week': False,
            'is_post_expiry_monday': True,
            'is_quarterly': is_quarterly,
        }

    return calendar


# ── Equity curve & stats ──────────────────────────────────────────────────────
def compute_sharpe(daily_returns, risk_free=0.05):
    """
    Annualized Sharpe ratio.
    For a sparse strategy (mostly 0 returns), compute on non-zero trading days
    but include idle-capital opportunity cost via risk-free rate on full equity.
    """
    if len(daily_returns) < 2:
        return 0
    n = len(daily_returns)
    # Add risk-free return to every day (idle capital earns T-bill rate)
    daily_rf = risk_free / 252
    adj_returns = [r + daily_rf for r in daily_returns]
    avg = sum(adj_returns) / n
    variance = sum((r - avg) ** 2 for r in adj_returns) / (n - 1)
    std = math.sqrt(variance)
    if std == 0:
        return 0
    excess = avg - daily_rf
    return excess / std * math.sqrt(252)


def compute_max_drawdown(equity_curve):
    """Returns max drawdown as a negative fraction."""
    peak = equity_curve[0]
    max_dd = 0
    for v in equity_curve:
        if v > peak:
            peak = v
        dd = (v - peak) / peak
        if dd < max_dd:
            max_dd = dd
    return max_dd


# ── Main backtest ─────────────────────────────────────────────────────────────
def run_backtest():
    btc = load_btc(DATA_DIR / 'btc_daily.csv')
    maxpain_proxy = load_maxpain(DATA_DIR / 'maxpain_proxy.csv')
    expiry_cal = build_expiry_calendar()

    # Merge max pain into calendar
    for exp_date, mp_row in maxpain_proxy.items():
        # Apply this max pain to all days in the expiry week and post-monday
        mon_of_week = exp_date - timedelta(days=4)
        post_mon = exp_date + timedelta(days=3)
        for offset in range(5):
            d = mon_of_week + timedelta(days=offset)
            if d in expiry_cal:
                expiry_cal[d]['max_pain'] = mp_row['max_pain']
        if post_mon in expiry_cal:
            expiry_cal[post_mon]['max_pain'] = mp_row['max_pain']

    strategy = MaxPainExpiryStrategy(initial_capital=100_000)

    start_date = date(2022, 1, 1)
    end_date = date(2026, 2, 28)

    sorted_dates = sorted(d for d in btc if start_date <= d <= end_date)

    equity_curve = [1.0]
    daily_returns = []
    all_events = []

    prev_equity = 1.0

    for d in sorted_dates:
        bar = btc[d]
        cal = expiry_cal.get(d, {
            'expiry_friday': None,
            'max_pain': bar['close'],   # fallback
            'days_to_expiry': 999,
            'is_expiry_week': False,
            'is_post_expiry_monday': False,
            'is_quarterly': False,
        })

        max_pain = cal['max_pain'] or bar['close']

        events = strategy.process_day(
            date=d,
            open_=bar['open'],
            high=bar['high'],
            low=bar['low'],
            close=bar['close'],
            max_pain=max_pain,
            is_expiry_week=cal['is_expiry_week'],
            days_to_expiry=cal['days_to_expiry'],
            is_quarterly=cal['is_quarterly'],
            is_post_expiry_monday=cal['is_post_expiry_monday'],
            expiry_friday=cal.get('expiry_friday'),
        )

        curr_equity = strategy.equity_multiplier
        equity_curve.append(curr_equity)
        daily_ret = (curr_equity - prev_equity) / prev_equity
        daily_returns.append(daily_ret)
        prev_equity = curr_equity

        if events:
            for ev in events:
                all_events.append(f"{d}  {ev}")

    # ── Force-close any open trades at final price ────────────────────────────
    final_date = sorted_dates[-1]
    final_price = btc[final_date]['close']
    for t in strategy.open_trades():
        t.close(final_date, final_price, 'end_of_backtest')
        strategy.equity_multiplier *= (1 + t.pnl_pct)

    # ── Strategy stats ────────────────────────────────────────────────────────
    total_days = (end_date - start_date).days
    years = total_days / 365.25
    total_return = strategy.equity_multiplier - 1.0
    ann_return = (strategy.equity_multiplier ** (1 / years)) - 1.0
    max_dd = compute_max_drawdown(equity_curve)
    sharpe = compute_sharpe(daily_returns)
    stats = strategy.summary_stats()

    # ── Buy-and-hold BTC ──────────────────────────────────────────────────────
    btc_start = btc[sorted_dates[0]]['close']
    btc_end = btc[sorted_dates[-1]]['close']
    bah_total = (btc_end - btc_start) / btc_start
    bah_ann = ((1 + bah_total) ** (1 / years)) - 1.0

    # ── BTC B&H drawdown ─────────────────────────────────────────────────────
    btc_equity = [btc[d]['close'] / btc_start for d in sorted_dates]
    bah_dd = compute_max_drawdown(btc_equity)

    # ── Trade-level Sharpe (better for sparse strategies) ─────────────────────
    closed = strategy.closed_trades()
    trade_pnls = [t.pnl_pct for t in closed]
    if len(trade_pnls) > 1:
        avg_t = sum(trade_pnls) / len(trade_pnls)
        std_t = math.sqrt(sum((p - avg_t) ** 2 for p in trade_pnls) / (len(trade_pnls) - 1))
        avg_hold_days = 5
        trade_sharpe = (avg_t / std_t * math.sqrt(252 / avg_hold_days)) if std_t > 0 else 0
    else:
        trade_sharpe = 0

    # ── Print to console ──────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("MAX PAIN EXPIRY STRATEGY — BACKTEST RESULTS")
    print(f"Period: {start_date} to {end_date}  ({years:.1f} years)")
    print("=" * 70)
    print(f"\n{'Strategy':<30} {'BTC B&H':>12}")
    print(f"  Total Return:        {total_return*100:>8.1f}%   {bah_total*100:>8.1f}%")
    print(f"  Annualized Return:   {ann_return*100:>8.1f}%   {bah_ann*100:>8.1f}%")
    print(f"  Max Drawdown:        {max_dd*100:>8.1f}%   {bah_dd*100:>8.1f}%")
    print(f"  Sharpe (daily eq):   {sharpe:>8.2f}")
    print(f"  Sharpe (trade-lvl):  {trade_sharpe:>8.2f}")
    print(f"\n  Total Trades:        {stats.get('total_trades',0):>4}")
    print(f"  Win Rate:            {stats.get('win_rate',0)*100:>7.1f}%")
    print(f"  Avg P&L/trade:       {stats.get('avg_pnl_per_trade',0)*100:>7.2f}%")
    print(f"  Best Trade:          {stats.get('best_trade',0)*100:>7.2f}%")
    print(f"  Worst Trade:         {stats.get('worst_trade',0)*100:>7.2f}%")

    ew = stats.get('expiry_week', {})
    pe = stats.get('post_expiry', {})
    qr = stats.get('quarterly', {})
    mo = stats.get('monthly', {})

    print("\n  ── Sub-Strategy Breakdown ──────────────────────────")
    print(f"  {'Type':<20} {'Count':>5}  {'Win%':>6}  {'Total P&L':>10}  {'Avg/Trade':>10}")
    for label, d in [('Expiry Week', ew), ('Post-Expiry Rev', pe),
                     ('Quarterly', qr), ('Monthly', mo)]:
        if d.get('count', 0) > 0:
            print(f"  {label:<20} {d['count']:>5}  {d['win_rate']*100:>5.1f}%  "
                  f"{d['total_pnl_pct']*100:>9.2f}%  {d['avg_pnl_pct']*100:>9.2f}%")

    print("\n  ── Trade Log (last 20) ─────────────────────────────")
    for ev in all_events[-20:]:
        print(f"  {ev}")

    # ── Save results markdown ─────────────────────────────────────────────────
    # Promising if: positive total return OR win_rate > 45% with controlled drawdown
    promising = ((total_return > 0.05 or (stats.get('win_rate', 0) > 0.45 and max_dd > -0.15))
                 and max_dd > -0.20)

    md = f"""# Max Pain Expiry Strategy — Backtest Results

**Period:** {start_date} to {end_date} ({years:.1f} years)  
**Generated:** 2026-03-11

## Performance Summary

| Metric | Strategy | BTC Buy & Hold |
|--------|----------|----------------|
| Total Return | {total_return*100:.1f}% | {bah_total*100:.1f}% |
| Annualized Return | {ann_return*100:.1f}% | {bah_ann*100:.1f}% |
| Max Drawdown | {max_dd*100:.1f}% | {bah_dd*100:.1f}% |
| Sharpe Ratio (daily equity) | {sharpe:.2f} | — |
| Sharpe Ratio (trade-level) | {trade_sharpe:.2f} | — |
| Total Trades | {stats.get('total_trades',0)} | — |
| Win Rate | {stats.get('win_rate',0)*100:.1f}% | — |
| Avg P&L / Trade | {stats.get('avg_pnl_per_trade',0)*100:.2f}% | — |
| Best Trade | {stats.get('best_trade',0)*100:.2f}% | — |
| Worst Trade | {stats.get('worst_trade',0)*100:.2f}% | — |

## Sub-Strategy Breakdown

| Type | Count | Win % | Total P&L | Avg/Trade |
|------|-------|-------|-----------|-----------|
"""
    for label, d in [('Expiry Week Magnet', ew), ('Post-Expiry Reversion', pe),
                     ('Quarterly', qr), ('Monthly', mo)]:
        if d.get('count', 0) > 0:
            md += (f"| {label} | {d['count']} | {d['win_rate']*100:.1f}% | "
                   f"{d['total_pnl_pct']*100:.2f}% | {d['avg_pnl_pct']*100:.2f}% |\n")

    md += f"""
## Trade-by-Trade Log

```
"""
    for ev in all_events:
        md += ev + "\n"
    md += "```\n\n"

    md += f"""## Strategy Assessment

**Verdict: {"✅ PROMISING — Recommend Paper Trading as Track D" if promising else "⚠️ MARGINAL — Needs refinement before paper trading"}**

Key observations:
- The max pain gravitational pull {"shows consistent" if stats.get('win_rate',0)>0.5 else "shows inconsistent"} directional signal
- Quarterly expiries {"outperform" if qr.get('avg_pnl_pct',0) > mo.get('avg_pnl_pct',0) else "underperform"} monthly expiries  
- Post-expiry reversion {"adds alpha" if pe.get('total_pnl_pct',0) > 0 else "detracts from performance"}
- Strategy {"beats" if ann_return > bah_ann else "underperforms"} BTC buy-and-hold on annualized basis
- Sharpe of {sharpe:.2f} {"is acceptable for an active strategy" if sharpe > 0.5 else "needs improvement"}

### Risk Management Notes
- Position sizing is conservative (15% expiry week, 10% post-expiry)
- Tight 5% stop-loss limits per-trade damage
- Time stops (Friday close) prevent position drift into post-expiry confusion
- Max 1 open trade per sub-strategy at a time

### Next Steps
{"- Open GitHub issue to begin **Track D: Max Pain Expiry** paper trading" if promising else "- Revisit max pain estimation quality — consider live Deribit OI data"}
- Monitor actual vs. estimated max pain deviation
- Consider adding: IV crush detection, open interest delta confirmation
- Live data source: Deribit `/public/get_book_summary_by_currency` (BTC options)

---
*Rule of Acquisition #22: A wise man can hear profit in the wind.*
"""

    results_path = RESULTS_DIR / 'maxpain_strategy_results.md'
    results_path.write_text(md)
    print(f"\n✅ Results saved to {results_path}")
    print(f"Promising: {promising}")

    return promising, stats, total_return, ann_return, max_dd, sharpe


if __name__ == '__main__':
    run_backtest()
