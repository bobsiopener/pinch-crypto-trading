#!/usr/bin/env python3
"""
generate_options_proxy.py — Generate synthetic BTC options proxy data.

Produces options_proxy.csv with daily P/C ratio and IV rank from 2022-01 to 2026-03.
Based on known market regime conditions with smooth transitions and daily noise.
"""

import csv
import datetime
import random
import math
import os

OUTPUT = os.path.join(os.path.dirname(__file__), "options_proxy.csv")

random.seed(42)  # reproducible


def lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation."""
    return a + (b - a) * max(0.0, min(1.0, t))


def smooth_noise(val: float, noise_scale: float, lo: float, hi: float) -> float:
    """Add Gaussian noise, clamp to [lo, hi]."""
    noisy = val + random.gauss(0, noise_scale)
    return max(lo, min(hi, noisy))


# ─── Market regime definitions ────────────────────────────────────────────────
# Each segment: (start, end, pc_center, pc_noise, iv_center, iv_noise)
# PC ratio: 0.0 - 2.0, IV rank: 0 - 100

REGIMES = [
    # 2022 Bear market — Fed hike cycle, crypto crash
    ("2022-01-01", "2022-03-31", 0.90, 0.08, 72.0, 6.0),
    ("2022-04-01", "2022-06-30", 1.05, 0.10, 80.0, 7.0),   # Terra/LUNA collapse
    ("2022-07-01", "2022-09-30", 1.00, 0.08, 75.0, 6.0),
    ("2022-10-01", "2022-11-15", 0.95, 0.08, 72.0, 6.0),
    ("2022-11-16", "2022-12-31", 1.15, 0.10, 85.0, 5.0),   # FTX collapse — peak fear

    # 2023 Recovery — slow grind up, declining macro fear
    ("2023-01-01", "2023-03-31", 0.70, 0.07, 45.0, 5.0),
    ("2023-04-01", "2023-06-30", 0.65, 0.06, 40.0, 5.0),
    ("2023-07-01", "2023-09-30", 0.60, 0.06, 38.0, 4.0),
    ("2023-10-01", "2023-12-31", 0.55, 0.06, 35.0, 4.0),   # ETF anticipation

    # 2024 H1 Bull — ETF approval, BTC halving
    ("2024-01-01", "2024-01-10", 0.50, 0.05, 35.0, 4.0),
    ("2024-01-11", "2024-01-31", 0.35, 0.05, 28.0, 4.0),   # ETF approval Jan 11
    ("2024-02-01", "2024-03-31", 0.38, 0.05, 30.0, 4.0),
    ("2024-04-01", "2024-04-30", 0.40, 0.06, 35.0, 5.0),   # Halving month
    ("2024-05-01", "2024-07-31", 0.42, 0.05, 32.0, 4.0),
    ("2024-08-01", "2024-10-31", 0.45, 0.05, 35.0, 4.0),

    # 2024 H2 Euphoria — Post-election, BTC to 100K
    ("2024-11-01", "2024-11-07", 0.40, 0.05, 55.0, 6.0),   # Pre-election
    ("2024-11-08", "2024-11-30", 0.28, 0.06, 75.0, 7.0),   # Election pump — euphoria
    ("2024-12-01", "2024-12-20", 0.25, 0.06, 82.0, 6.0),   # Peak euphoria (BTC ATH)
    ("2024-12-21", "2024-12-31", 0.35, 0.06, 70.0, 6.0),   # Year-end cooldown

    # 2025 Correction to Bear — macro headwinds, uncertainty
    ("2025-01-01", "2025-03-31", 0.55, 0.07, 55.0, 5.0),
    ("2025-04-01", "2025-06-30", 0.70, 0.08, 62.0, 6.0),
    ("2025-07-01", "2025-09-30", 0.80, 0.08, 68.0, 6.0),
    ("2025-10-01", "2025-12-31", 0.85, 0.09, 72.0, 6.0),

    # 2026 Q1 Continued bear/uncertainty
    ("2026-01-01", "2026-03-31", 0.90, 0.10, 70.0, 7.0),
]


def get_regime_params(date_str: str) -> tuple[float, float, float, float]:
    """Get (pc_center, pc_noise, iv_center, iv_noise) for a given date."""
    # Find enclosing regime, with blending at boundaries
    d = datetime.date.fromisoformat(date_str)

    for i, (start, end, pc_c, pc_n, iv_c, iv_n) in enumerate(REGIMES):
        start_d = datetime.date.fromisoformat(start)
        end_d = datetime.date.fromisoformat(end)
        if start_d <= d <= end_d:
            # Blend in/out with next regime for smooth transitions
            total_days = (end_d - start_d).days
            days_in = (d - start_d).days
            t = days_in / total_days if total_days > 0 else 0.0

            if i + 1 < len(REGIMES) and t > 0.7:
                # Blend with next regime in last 30% of period
                next_start, next_end, npc_c, npc_n, niv_c, niv_n = REGIMES[i + 1]
                blend_t = (t - 0.7) / 0.3
                pc_c = lerp(pc_c, npc_c, blend_t)
                iv_c = lerp(iv_c, niv_c, blend_t)

            return pc_c, pc_n, iv_c, iv_n

    # Default fallback
    return 0.65, 0.07, 50.0, 5.0


def generate():
    """Generate and write the options proxy CSV."""
    start = datetime.date(2022, 1, 1)
    end = datetime.date(2026, 3, 31)

    # Low-frequency random walk component for realism
    pc_walk = 0.0
    iv_walk = 0.0
    walk_decay = 0.85  # mean reversion

    rows = []
    current = start
    while current <= end:
        date_str = current.strftime("%Y-%m-%d")
        pc_c, pc_n, iv_c, iv_n = get_regime_params(date_str)

        # Random walk (slowly mean-reverting)
        pc_walk = pc_walk * walk_decay + random.gauss(0, 0.02)
        iv_walk = iv_walk * walk_decay + random.gauss(0, 2.0)

        pc_raw = pc_c + pc_walk
        iv_raw = iv_c + iv_walk

        pc = smooth_noise(pc_raw, pc_n * 0.5, 0.10, 1.80)
        iv = smooth_noise(iv_raw, iv_n * 0.5, 5.0, 99.0)

        rows.append((date_str, round(pc, 4), round(iv, 2)))
        current += datetime.timedelta(days=1)

    with open(OUTPUT, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Date", "pc_ratio", "iv_rank"])
        writer.writerows(rows)

    print(f"[✓] Generated {len(rows)} rows → {OUTPUT}")
    print(f"    Date range: {rows[0][0]} to {rows[-1][0]}")
    # Show sample stats
    pcs = [r[1] for r in rows]
    ivs = [r[2] for r in rows]
    print(f"    P/C ratio: min={min(pcs):.2f} max={max(pcs):.2f} avg={sum(pcs)/len(pcs):.2f}")
    print(f"    IV rank:   min={min(ivs):.1f} max={max(ivs):.1f} avg={sum(ivs)/len(ivs):.1f}")


if __name__ == "__main__":
    generate()
