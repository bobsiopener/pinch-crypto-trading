#!/usr/bin/env python3
"""
Kill Switch & Emergency Procedures — Pinch Crypto Trading
==========================================================
Standalone script to immediately flatten all positions on Kraken.

Usage:
  python3 kill_switch.py kill    — execute kill switch (flatten all)
  python3 kill_switch.py check   — run health check
  python3 kill_switch.py status  — show current drawdown vs HWM

Rule of Acquisition #74: Knowledge equals profit.
"""

import sys
import os
import time
import json
import csv
from datetime import datetime, timezone

# Add the secrets path so we can import the Kraken client
sys.path.insert(0, '/home/bob/.openclaw/workspace-pinch/.secrets')
import kraken_trader as kraken

# Paths
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RISK_STATE_PATH = os.path.join(REPO_ROOT, 'live', 'config', 'risk_state.json')
KILL_LOG_PATH   = os.path.join(REPO_ROOT, 'logs', 'trades', 'kill_switch_log.csv')

# Asset → Kraken pair map for market sell
ASSET_PAIR_MAP = {
    'XETH': 'XETHZUSD',
    'ETH':  'XETHZUSD',
    'XXBT': 'XXBTZUSD',
    'XBT':  'XXBTZUSD',
    'BTC':  'XXBTZUSD',
    'SOL':  'SOLUSD',
}

# Minimum volumes below which we skip (Kraken minimums)
MIN_VOLUME = {
    'XETHZUSD': 0.002,
    'XXBTZUSD': 0.0001,
    'SOLUSD':   0.5,
}

USD_ASSETS = {'ZUSD', 'USD'}

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def load_risk_state():
    if not os.path.exists(RISK_STATE_PATH):
        return {
            "high_water_mark": 0.0,
            "consecutive_losses": 0,
            "last_trade_date": None,
            "circuit_breaker_status": "OK",
            "kill_switch_armed": True,
            "last_health_check": None,
        }
    with open(RISK_STATE_PATH) as f:
        return json.load(f)

def save_risk_state(state):
    os.makedirs(os.path.dirname(RISK_STATE_PATH), exist_ok=True)
    with open(RISK_STATE_PATH, 'w') as f:
        json.dump(state, f, indent=2)

def log_kill_switch_event(trigger: str, initial_usd: float, final_usd: float,
                           assets_sold: list, orders_cancelled: int):
    os.makedirs(os.path.dirname(KILL_LOG_PATH), exist_ok=True)
    header = ['timestamp', 'trigger', 'initial_usd', 'final_usd', 'pnl_usd',
              'assets_sold', 'orders_cancelled']
    file_exists = os.path.exists(KILL_LOG_PATH)
    with open(KILL_LOG_PATH, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=header)
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            'timestamp':        datetime.now(timezone.utc).isoformat(),
            'trigger':          trigger,
            'initial_usd':      f'{initial_usd:.2f}',
            'final_usd':        f'{final_usd:.2f}',
            'pnl_usd':          f'{final_usd - initial_usd:.2f}',
            'assets_sold':      '|'.join(assets_sold),
            'orders_cancelled': orders_cancelled,
        })
    print(f"  📋 Kill event logged → {KILL_LOG_PATH}")

def get_usd_price(asset: str) -> float:
    """Return current USD price of an asset (0 if unknown)."""
    pair = ASSET_PAIR_MAP.get(asset)
    if not pair:
        return 0.0
    try:
        t = kraken.get_ticker(pair)
        return t['bid']  # use bid (conservative sell estimate)
    except Exception as e:
        print(f"  ⚠️  Could not fetch price for {asset}/{pair}: {e}")
        return 0.0

def get_total_usd(balances: dict) -> float:
    total = 0.0
    for asset, amount in balances.items():
        amt = float(amount)
        if amt < 1e-8:
            continue
        if asset in USD_ASSETS:
            total += amt
        else:
            price = get_usd_price(asset)
            total += amt * price
    return total

# ─────────────────────────────────────────────
# 1. KILL SWITCH
# ─────────────────────────────────────────────

def kill_switch(trigger: str = 'MANUAL') -> dict:
    """
    Immediately flatten all positions on Kraken.
    1. Cancel all open orders
    2. Market sell all non-USD assets worth > $1
    3. Verify & report final USD balance
    4. Log the event
    """
    print("\n" + "═" * 60)
    print("  🚨  KILL SWITCH ACTIVATED")
    print(f"  Trigger: {trigger}")
    print(f"  Time:    {datetime.now(timezone.utc).isoformat()}")
    print("═" * 60)

    assets_sold = []
    orders_cancelled = 0

    # ── Step 1: Get initial balance ──────────────────────────
    print("\n[1/4] Fetching initial balances…")
    try:
        initial_balances = kraken.get_balance()
        initial_usd = get_total_usd(initial_balances)
        print(f"  Initial portfolio value: ${initial_usd:,.2f}")
        for asset, amt in initial_balances.items():
            if float(amt) > 1e-8:
                print(f"    {asset}: {float(amt):.6f}")
    except Exception as e:
        print(f"  ❌ Could not fetch balances: {e}")
        return {'status': 'ERROR', 'error': str(e)}

    # ── Step 2: Cancel all open orders ───────────────────────
    print("\n[2/4] Cancelling all open orders…")
    try:
        open_orders = kraken.get_open_orders()
        open_count = len(open_orders.get('open', {}))
        if open_count > 0:
            result = kraken.cancel_all()
            orders_cancelled = result.get('count', open_count)
            print(f"  ✅ Cancelled {orders_cancelled} open order(s)")
        else:
            print("  ✅ No open orders to cancel")
    except Exception as e:
        print(f"  ⚠️  Error cancelling orders: {e}")

    # ── Step 3: Market sell all non-USD assets ───────────────
    print("\n[3/4] Liquidating non-USD positions…")
    for asset, amount_str in initial_balances.items():
        if asset in USD_ASSETS:
            continue
        amount = float(amount_str)
        if amount < 1e-8:
            continue

        pair = ASSET_PAIR_MAP.get(asset)
        if not pair:
            print(f"  ⚠️  Unknown pair for {asset} — skipping")
            continue

        # Estimate USD value
        price = get_usd_price(asset)
        usd_value = amount * price
        if usd_value < 1.0:
            print(f"  ⏭️  {asset}: ${usd_value:.4f} < $1.00 — skipping (dust)")
            continue

        min_vol = MIN_VOLUME.get(pair, 0.0)
        if amount < min_vol:
            print(f"  ⏭️  {asset}: {amount:.6f} < min order {min_vol} — skipping")
            continue

        print(f"  🔴 Selling {amount:.6f} {asset} (~${usd_value:.2f})…")
        try:
            result = kraken.place_order(pair, 'sell', 'market', round(amount, 6))
            txid = result.get('txid', ['?'])[0] if result.get('txid') else '?'
            print(f"     ✅ Order placed: {txid}")
            assets_sold.append(f"{asset}:{amount:.6f}")
        except Exception as e:
            print(f"     ❌ Failed to sell {asset}: {e}")

    # ── Step 4: Wait and verify ───────────────────────────────
    print("\n[4/4] Waiting 3s for fills to settle…")
    time.sleep(3)

    try:
        final_balances = kraken.get_balance()
        final_usd = get_total_usd(final_balances)

        remaining_crypto = {
            a: float(v) for a, v in final_balances.items()
            if a not in USD_ASSETS and float(v) > 1e-8
        }

        print(f"\n  Final portfolio value: ${final_usd:,.2f}")
        if remaining_crypto:
            print("  ⚠️  Remaining crypto (may be processing):")
            for asset, amt in remaining_crypto.items():
                price = get_usd_price(asset)
                print(f"    {asset}: {amt:.6f} (~${amt*price:.2f})")
        else:
            print("  ✅ All positions closed — fully in USD")

    except Exception as e:
        print(f"  ⚠️  Could not fetch final balances: {e}")
        final_usd = 0.0

    # ── Log event ─────────────────────────────────────────────
    log_kill_switch_event(trigger, initial_usd, final_usd, assets_sold, orders_cancelled)

    # ── Update risk state ─────────────────────────────────────
    state = load_risk_state()
    state['circuit_breaker_status'] = 'LOCKED'
    state['kill_switch_armed'] = False
    save_risk_state(state)

    print("\n" + "═" * 60)
    print(f"  Kill switch complete. Final USD: ${final_usd:,.2f}")
    print("  Circuit breaker set to LOCKED — manual override required.")
    print("═" * 60 + "\n")

    return {
        'status': 'COMPLETE',
        'trigger': trigger,
        'initial_usd': initial_usd,
        'final_usd': final_usd,
        'assets_sold': assets_sold,
        'orders_cancelled': orders_cancelled,
    }

# ─────────────────────────────────────────────
# 2. CIRCUIT BREAKER
# ─────────────────────────────────────────────

def circuit_breaker(account_value: float, high_water_mark: float) -> str:
    """
    Evaluate drawdown from high-water mark and return action string.

    Returns:
      "OK"      — drawdown ≤ 5%  (normal operations)
      "TIGHTEN" — drawdown > 5%  (tighten stops)
      "REDUCE"  — drawdown > 10% (half position sizes)
      "HALT"    — drawdown > 15% (trigger kill switch)
      "LOCKED"  — drawdown > 20% (no trading, manual override required)
    """
    if high_water_mark <= 0:
        return "OK"

    drawdown = (high_water_mark - account_value) / high_water_mark

    if drawdown > 0.20:
        status = "LOCKED"
    elif drawdown > 0.15:
        status = "HALT"
    elif drawdown > 0.10:
        status = "REDUCE"
    elif drawdown > 0.05:
        status = "TIGHTEN"
    else:
        status = "OK"

    # Auto-trigger kill switch on HALT
    if status == "HALT":
        print(f"  🚨 Circuit breaker HALT: drawdown {drawdown:.1%} from HWM ${high_water_mark:,.2f}")
        kill_switch(trigger=f'CIRCUIT_BREAKER_HALT_drawdown_{drawdown:.1%}')
        status = "LOCKED"

    return status

# ─────────────────────────────────────────────
# 3. HEALTH CHECK
# ─────────────────────────────────────────────

def health_check() -> dict:
    """
    Check API connectivity and order health.

    Returns dict with:
      status: "OK" | "DEGRADED" | "OFFLINE"
      api_ok: bool
      stuck_orders: list of txids open > 1 hour
      message: human-readable summary
    """
    print("\n── Health Check ──────────────────────────────────────")
    result = {
        'status': 'OK',
        'api_ok': False,
        'stuck_orders': [],
        'message': '',
        'timestamp': datetime.now(timezone.utc).isoformat(),
    }

    # ── API connectivity ──────────────────────────────────────
    try:
        balances = kraken.get_balance()
        result['api_ok'] = True
        usd_bal = sum(float(v) for k, v in balances.items() if k in USD_ASSETS)
        print(f"  ✅ API connected — USD balance: ${usd_bal:,.2f}")
    except Exception as e:
        result['api_ok'] = False
        result['status'] = 'OFFLINE'
        result['message'] = f"API unreachable: {e}"
        print(f"  ❌ API OFFLINE: {e}")
        return result

    # ── Stuck orders (open > 1 hour) ─────────────────────────
    try:
        open_orders = kraken.get_open_orders()
        now_ts = time.time()
        one_hour = 3600
        stuck = []

        for txid, order in open_orders.get('open', {}).items():
            open_time = order.get('opentm', now_ts)
            age_secs = now_ts - open_time
            if age_secs > one_hour:
                age_h = age_secs / 3600
                stuck.append({'txid': txid, 'age_hours': round(age_h, 2),
                               'descr': order.get('descr', {})})
                print(f"  ⚠️  Stuck order {txid}: open {age_h:.1f}h — {order.get('descr', {})}")

        result['stuck_orders'] = stuck
        if stuck:
            result['status'] = 'DEGRADED'
            result['message'] = f"{len(stuck)} stuck order(s) > 1h"
        else:
            print(f"  ✅ No stuck orders")

    except Exception as e:
        result['status'] = 'DEGRADED'
        result['message'] = f"Could not check open orders: {e}"
        print(f"  ⚠️  Order check failed: {e}")

    if result['status'] == 'OK':
        result['message'] = 'All systems nominal'

    # ── Update last health check in risk state ────────────────
    try:
        state = load_risk_state()
        state['last_health_check'] = result['timestamp']
        save_risk_state(state)
    except Exception:
        pass

    print(f"  Status: {result['status']} — {result['message']}")
    print("─" * 54 + "\n")
    return result

# ─────────────────────────────────────────────
# 4. STATUS — drawdown vs HWM
# ─────────────────────────────────────────────

def show_status():
    """Show current account value vs HWM and circuit breaker status."""
    print("\n── Risk Status ───────────────────────────────────────")
    state = load_risk_state()
    hwm = state.get('high_water_mark', 0.0)

    try:
        summary = kraken.get_balance_summary()
        current_value = summary.get('_total_usd', 0.0)
    except Exception as e:
        print(f"  ❌ Could not fetch balance: {e}")
        return

    drawdown = (hwm - current_value) / hwm if hwm > 0 else 0.0
    cb_status = circuit_breaker.__wrapped__ if hasattr(circuit_breaker, '__wrapped__') else None

    # Evaluate without triggering kill switch for display purposes
    if hwm <= 0:
        cb_label = "OK"
    elif drawdown > 0.20:
        cb_label = "LOCKED"
    elif drawdown > 0.15:
        cb_label = "HALT ⚠️"
    elif drawdown > 0.10:
        cb_label = "REDUCE"
    elif drawdown > 0.05:
        cb_label = "TIGHTEN"
    else:
        cb_label = "OK"

    print(f"  Current value:      ${current_value:,.2f}")
    print(f"  High-water mark:    ${hwm:,.2f}")
    print(f"  Drawdown:           {drawdown:.2%}")
    print(f"  Circuit breaker:    {cb_label}")
    print(f"  Consecutive losses: {state.get('consecutive_losses', 0)}")
    print(f"  CB status (stored): {state.get('circuit_breaker_status', 'OK')}")
    print(f"  Kill switch armed:  {state.get('kill_switch_armed', True)}")
    print(f"  Last health check:  {state.get('last_health_check', 'never')}")
    print(f"  Last trade:         {state.get('last_trade_date', 'never')}")
    print("─" * 54 + "\n")

# ─────────────────────────────────────────────
# CLI ENTRYPOINT
# ─────────────────────────────────────────────

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'help'

    if cmd == 'kill':
        confirm = input("⚠️  Type CONFIRM to execute kill switch: ").strip()
        if confirm == 'CONFIRM':
            kill_switch(trigger='CLI_MANUAL')
        else:
            print("Aborted. No positions changed.")

    elif cmd == 'check':
        result = health_check()
        sys.exit(0 if result['status'] == 'OK' else 1)

    elif cmd == 'status':
        show_status()

    elif cmd == 'kill-force':
        # Non-interactive kill for automation (no confirmation prompt)
        kill_switch(trigger='CLI_FORCE')

    else:
        print(__doc__)
        print("Commands:")
        print("  kill       — interactive kill switch (requires CONFIRM)")
        print("  kill-force — non-interactive kill switch (automation use)")
        print("  check      — health check (exits 0=OK, 1=DEGRADED/OFFLINE)")
        print("  status     — show drawdown vs HWM")
