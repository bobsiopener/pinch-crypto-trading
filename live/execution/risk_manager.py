#!/usr/bin/env python3
"""
Risk Manager — Pinch Crypto Trading
=====================================
Reads and updates risk_state.json. Enforces circuit breaker rules
and provides position sizing based on account health.

Rule of Acquisition #59: Free advice is seldom cheap.
"""

import os
import json
from datetime import datetime, timezone
from typing import Optional

# Paths
_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RISK_STATE_PATH = os.path.join(_HERE, 'config', 'risk_state.json')

# Circuit breaker thresholds
CB_TIGHTEN_PCT = 0.05   # 5%  drawdown → tighten stops
CB_REDUCE_PCT  = 0.10   # 10% drawdown → half size
CB_HALT_PCT    = 0.15   # 15% drawdown → halt + kill switch
CB_LOCKED_PCT  = 0.20   # 20% drawdown → locked, manual override

# Consecutive loss thresholds
LOSS_REDUCE_THRESHOLD = 3   # >= 3 losses → 0.5x size
LOSS_ZERO_THRESHOLD   = 5   # >= 5 losses → 0.0x (go to cash)


class RiskManager:
    """
    Manages account risk state: high-water mark, consecutive losses,
    circuit breaker status, and position sizing.
    """

    def __init__(self, state_path: str = RISK_STATE_PATH):
        self.state_path = state_path
        self.state = self._load()

    # ─────────────────────────────────────────────
    # STATE I/O
    # ─────────────────────────────────────────────

    def _load(self) -> dict:
        if not os.path.exists(self.state_path):
            default = {
                "high_water_mark": 0.0,
                "consecutive_losses": 0,
                "last_trade_date": None,
                "circuit_breaker_status": "OK",
                "kill_switch_armed": True,
                "last_health_check": None,
            }
            self._save(default)
            return default
        with open(self.state_path) as f:
            return json.load(f)

    def _save(self, state: Optional[dict] = None):
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        data = state if state is not None else self.state
        with open(self.state_path, 'w') as f:
            json.dump(data, f, indent=2)

    def reload(self):
        """Reload state from disk (for long-running processes)."""
        self.state = self._load()

    # ─────────────────────────────────────────────
    # HIGH-WATER MARK
    # ─────────────────────────────────────────────

    def update_high_water_mark(self, account_value: float) -> bool:
        """
        Update HWM if account_value exceeds the stored mark.
        Returns True if HWM was updated.
        """
        hwm = self.state.get('high_water_mark', 0.0)
        if account_value > hwm:
            self.state['high_water_mark'] = round(account_value, 2)
            self._save()
            return True
        return False

    @property
    def high_water_mark(self) -> float:
        return self.state.get('high_water_mark', 0.0)

    def drawdown(self, account_value: float) -> float:
        """Return fractional drawdown from HWM (0.0 – 1.0+)."""
        hwm = self.high_water_mark
        if hwm <= 0:
            return 0.0
        return max(0.0, (hwm - account_value) / hwm)

    # ─────────────────────────────────────────────
    # CONSECUTIVE LOSSES
    # ─────────────────────────────────────────────

    def record_trade(self, pnl: float):
        """
        Record a completed trade result.
        Positive pnl → resets loss streak.
        Negative pnl → increments consecutive_losses.
        Updates last_trade_date and saves.
        """
        self.reload()
        if pnl >= 0:
            self.state['consecutive_losses'] = 0
        else:
            self.state['consecutive_losses'] = self.state.get('consecutive_losses', 0) + 1

        self.state['last_trade_date'] = datetime.now(timezone.utc).isoformat()
        self._save()

    @property
    def consecutive_losses(self) -> int:
        return self.state.get('consecutive_losses', 0)

    def reset_losses(self):
        """Manually reset consecutive loss counter."""
        self.state['consecutive_losses'] = 0
        self._save()

    # ─────────────────────────────────────────────
    # CIRCUIT BREAKER
    # ─────────────────────────────────────────────

    def evaluate_circuit_breaker(self, account_value: float) -> str:
        """
        Evaluate drawdown and return circuit breaker status.
        Also updates risk_state.json with the current status.

        Returns one of: OK | TIGHTEN | REDUCE | HALT | LOCKED
        """
        dd = self.drawdown(account_value)

        if dd > CB_LOCKED_PCT:
            status = "LOCKED"
        elif dd > CB_HALT_PCT:
            status = "HALT"
        elif dd > CB_REDUCE_PCT:
            status = "REDUCE"
        elif dd > CB_TIGHTEN_PCT:
            status = "TIGHTEN"
        else:
            status = "OK"

        # Persist
        self.state['circuit_breaker_status'] = status
        self._save()

        # Auto-trigger kill switch on HALT (imports lazily to avoid circular dep)
        if status == "HALT":
            try:
                from kill_switch import kill_switch
                print(f"[RiskManager] ⚠️  HALT triggered — drawdown {dd:.1%}. Executing kill switch.")
                kill_switch(trigger=f'RISK_MANAGER_HALT_dd={dd:.1%}')
                self.state['circuit_breaker_status'] = 'LOCKED'
                self.state['kill_switch_armed'] = False
                self._save()
                status = "LOCKED"
            except Exception as e:
                print(f"[RiskManager] ❌ Kill switch failed: {e}")

        return status

    @property
    def circuit_breaker_status(self) -> str:
        return self.state.get('circuit_breaker_status', 'OK')

    def is_trading_allowed(self, account_value: float) -> bool:
        """
        Returns True only if circuit breaker is OK or TIGHTEN.
        REDUCE, HALT, LOCKED all block new full-size positions.
        """
        status = self.evaluate_circuit_breaker(account_value)
        return status in ('OK', 'TIGHTEN')

    # ─────────────────────────────────────────────
    # POSITION SIZING
    # ─────────────────────────────────────────────

    def position_size_multiplier(self, account_value: Optional[float] = None) -> float:
        """
        Return a multiplier (0.0–1.0) to scale position sizes.

        Factors considered (most restrictive wins):
          - Consecutive losses:
              < 3  → 1.0
              3–4  → 0.5
              ≥ 5  → 0.0  (go to cash)
          - Circuit breaker:
              OK      → 1.0
              TIGHTEN → 1.0  (handle via stops, not size)
              REDUCE  → 0.5
              HALT    → 0.0  (already killing)
              LOCKED  → 0.0  (manual override required)

        Returns the minimum of both factors.
        """
        # Loss-based multiplier
        losses = self.consecutive_losses
        if losses >= LOSS_ZERO_THRESHOLD:
            loss_mult = 0.0
        elif losses >= LOSS_REDUCE_THRESHOLD:
            loss_mult = 0.5
        else:
            loss_mult = 1.0

        # Circuit-breaker multiplier
        if account_value is not None:
            cb = self.evaluate_circuit_breaker(account_value)
        else:
            cb = self.circuit_breaker_status

        cb_mult_map = {
            'OK':      1.0,
            'TIGHTEN': 1.0,
            'REDUCE':  0.5,
            'HALT':    0.0,
            'LOCKED':  0.0,
        }
        cb_mult = cb_mult_map.get(cb, 0.0)

        return min(loss_mult, cb_mult)

    # ─────────────────────────────────────────────
    # CONVENIENCE
    # ─────────────────────────────────────────────

    def on_trade_close(self, account_value: float, pnl: float) -> dict:
        """
        Call after every trade closes. Updates all state and returns
        a summary dict with sizing recommendation.
        """
        self.update_high_water_mark(account_value)
        self.record_trade(pnl)
        cb = self.evaluate_circuit_breaker(account_value)
        mult = self.position_size_multiplier(account_value)

        return {
            'circuit_breaker': cb,
            'position_size_multiplier': mult,
            'consecutive_losses': self.consecutive_losses,
            'high_water_mark': self.high_water_mark,
            'drawdown': round(self.drawdown(account_value), 4),
            'account_value': account_value,
        }

    def summary(self, account_value: Optional[float] = None) -> dict:
        """Return a human-readable state dict."""
        self.reload()
        dd = self.drawdown(account_value) if account_value is not None else None
        return {
            'high_water_mark': self.high_water_mark,
            'consecutive_losses': self.consecutive_losses,
            'circuit_breaker_status': self.circuit_breaker_status,
            'kill_switch_armed': self.state.get('kill_switch_armed', True),
            'last_trade_date': self.state.get('last_trade_date'),
            'last_health_check': self.state.get('last_health_check'),
            'account_value': account_value,
            'drawdown_pct': f'{dd:.2%}' if dd is not None else None,
            'position_size_multiplier': self.position_size_multiplier(account_value),
        }


# ─────────────────────────────────────────────
# MODULE-LEVEL HELPERS (functional interface)
# ─────────────────────────────────────────────

def load_risk_state() -> dict:
    rm = RiskManager()
    return rm.state

def position_size_multiplier(account_value: Optional[float] = None) -> float:
    """Quick functional accessor."""
    rm = RiskManager()
    return rm.position_size_multiplier(account_value)

def record_trade(pnl: float):
    """Record a trade result and update state."""
    rm = RiskManager()
    rm.record_trade(pnl)

def update_high_water_mark(account_value: float) -> bool:
    rm = RiskManager()
    return rm.update_high_water_mark(account_value)


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

if __name__ == '__main__':
    import sys
    rm = RiskManager()

    cmd = sys.argv[1] if len(sys.argv) > 1 else 'summary'

    if cmd == 'summary':
        try:
            sys.path.insert(0, '/home/bob/.openclaw/workspace-pinch/.secrets')
            import kraken_trader as kraken
            summary = kraken.get_balance_summary()
            val = summary.get('_total_usd', None)
        except Exception:
            val = None
        s = rm.summary(val)
        print(json.dumps(s, indent=2))

    elif cmd == 'multiplier':
        mult = position_size_multiplier()
        print(f"Position size multiplier: {mult}")

    elif cmd == 'reset-losses':
        rm.reset_losses()
        print("Consecutive loss counter reset to 0.")

    elif cmd == 'record-win':
        pnl = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
        rm.record_trade(pnl)
        print(f"Recorded win (+{pnl}). Consecutive losses: {rm.consecutive_losses}")

    elif cmd == 'record-loss':
        pnl = float(sys.argv[2]) if len(sys.argv) > 2 else -10.0
        rm.record_trade(-abs(pnl))
        print(f"Recorded loss (-{abs(pnl)}). Consecutive losses: {rm.consecutive_losses}")

    else:
        print("Usage: risk_manager.py [summary|multiplier|reset-losses|record-win|record-loss]")
