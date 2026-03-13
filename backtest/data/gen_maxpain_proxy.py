"""
Generate maxpain_proxy.csv for BTC monthly/quarterly expiries 2022-01 through 2026-02.
Max pain is estimated based on known BTC price history and typical options OI patterns.
"""

import csv
import random
from datetime import date, timedelta

random.seed(42)  # reproducible

def last_friday(year, month):
    """Return the last Friday of the given month."""
    # Start from last day of month
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    last_day = next_month - timedelta(days=1)
    # Friday = weekday 4
    offset = (last_day.weekday() - 4) % 7
    return last_day - timedelta(days=offset)

def monday_of_expiry_week(expiry_date):
    """Return Monday of the week containing expiry (Friday)."""
    return expiry_date - timedelta(days=4)

# BTC approximate monthly close prices (end of month)
# Format: (year, month) -> approximate price
btc_monthly = {
    (2022, 1): 38500,
    (2022, 2): 43200,
    (2022, 3): 46500,
    (2022, 4): 38000,
    (2022, 5): 28000,
    (2022, 6): 19000,
    (2022, 7): 24000,
    (2022, 8): 19800,
    (2022, 9): 19400,
    (2022, 10): 20400,
    (2022, 11): 16600,
    (2022, 12): 16500,
    (2023, 1): 22900,
    (2023, 2): 23400,
    (2023, 3): 28400,
    (2023, 4): 29400,
    (2023, 5): 27100,
    (2023, 6): 30500,
    (2023, 7): 29300,
    (2023, 8): 26000,
    (2023, 9): 26800,
    (2023, 10): 34500,
    (2023, 11): 37800,
    (2023, 12): 42700,
    (2024, 1): 42500,
    (2024, 2): 61300,
    (2024, 3): 71000,
    (2024, 4): 60000,
    (2024, 5): 67500,
    (2024, 6): 62400,
    (2024, 7): 66000,
    (2024, 8): 59000,
    (2024, 9): 63300,
    (2024, 10): 72000,
    (2024, 11): 96500,
    (2024, 12): 93000,
    (2025, 1): 102000,
    (2025, 2): 84000,
    (2025, 3): 82000,
    (2025, 4): 93000,
    (2025, 5): 103000,
    (2025, 6): 107000,
    (2025, 7): 98000,
    (2025, 8): 88000,
    (2025, 9): 81000,
    (2025, 10): 72000,
    (2025, 11): 74000,
    (2025, 12): 76000,
    (2026, 1): 76000,
    (2026, 2): 72000,
}

# Approximate prices at START of expiry week (Monday)
btc_start_of_week = {
    (2022, 1): 36500,
    (2022, 2): 38200,
    (2022, 3): 44000,
    (2022, 4): 39500,
    (2022, 5): 30000,
    (2022, 6): 20500,
    (2022, 7): 22500,
    (2022, 8): 21500,
    (2022, 9): 20000,
    (2022, 10): 19500,
    (2022, 11): 20000,
    (2022, 12): 17200,
    (2023, 1): 21000,
    (2023, 2): 23000,
    (2023, 3): 27500,
    (2023, 4): 28000,
    (2023, 5): 27500,
    (2023, 6): 26500,
    (2023, 7): 30000,
    (2023, 8): 29500,
    (2023, 9): 26200,
    (2023, 10): 28000,
    (2023, 11): 36000,
    (2023, 12): 41500,
    (2024, 1): 41000,
    (2024, 2): 52000,
    (2024, 3): 70000,
    (2024, 4): 64000,
    (2024, 5): 62000,
    (2024, 6): 65000,
    (2024, 7): 67000,
    (2024, 8): 63000,
    (2024, 9): 58000,
    (2024, 10): 67000,
    (2024, 11): 90000,
    (2024, 12): 97000,
    (2025, 1): 96000,
    (2025, 2): 97000,
    (2025, 3): 84000,
    (2025, 4): 81000,
    (2025, 5): 96000,
    (2025, 6): 107000,
    (2025, 7): 106000,
    (2025, 8): 95000,
    (2025, 9): 86000,
    (2025, 10): 80000,
    (2025, 11): 66000,
    (2025, 12): 74000,
    (2026, 1): 96000,
    (2026, 2): 83000,
}

QUARTERLY_MONTHS = {3, 6, 9, 12}

ROUND_NUMBERS = [10000, 15000, 20000, 25000, 30000, 35000, 40000, 45000,
                 50000, 55000, 60000, 65000, 70000, 75000, 80000, 85000,
                 90000, 95000, 100000, 105000, 110000, 115000, 120000, 125000]

def snap_to_round(price, tolerance=0.06):
    """Snap price to nearest round number if within tolerance."""
    for rn in ROUND_NUMBERS:
        if abs(price - rn) / rn < tolerance:
            return rn
    return round(price / 1000) * 1000

def estimate_max_pain(year, month, spot_at_expiry, spot_at_start):
    """
    Estimate max pain based on market regime and typical OI patterns.
    
    Bull market: max pain 5-15% below spot (calls dominate OI)
    Bear market: max pain at or slightly above spot
    Consolidation: max pain 2-8% below spot
    """
    # Determine market regime by comparing start vs prior month
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    prev_price = btc_monthly.get((prev_year, prev_month), spot_at_start)
    
    monthly_change = (spot_at_start - prev_price) / prev_price
    
    # Classify regime
    if spot_at_start < 20000:
        # Deep bear
        discount_min, discount_max = -0.02, 0.05  # max pain near or above spot
    elif spot_at_start < 30000:
        # Bear/recovery
        discount_min, discount_max = 0.02, 0.08
    elif monthly_change < -0.10:
        # Crash month
        discount_min, discount_max = -0.03, 0.04  # max pain can be ABOVE crashed spot
    elif monthly_change > 0.10:
        # Strong bull
        discount_min, discount_max = 0.08, 0.15
    elif monthly_change > 0.05:
        # Moderate bull
        discount_min, discount_max = 0.05, 0.10
    else:
        # Consolidation
        discount_min, discount_max = 0.03, 0.08
    
    # Quarterly expiries anchor more strongly to round numbers
    is_quarterly = month in QUARTERLY_MONTHS
    
    discount = random.uniform(discount_min, discount_max)
    raw_max_pain = spot_at_start * (1 - discount)
    
    # Snap to round number (stronger for quarterly)
    snap_tolerance = 0.08 if is_quarterly else 0.05
    max_pain = snap_to_round(raw_max_pain, snap_tolerance)
    
    return max_pain

rows = []
for year in range(2022, 2027):
    for month in range(1, 13):
        if year == 2026 and month > 2:
            break
        if year == 2022 and month < 1:
            continue
        
        expiry = last_friday(year, month)
        is_quarterly = 1 if month in QUARTERLY_MONTHS else 0
        
        spot_start = btc_start_of_week.get((year, month), 0)
        spot_expiry = btc_monthly.get((year, month), 0)
        
        max_pain = estimate_max_pain(year, month, spot_expiry, spot_start)
        
        rows.append({
            'expiry_date': expiry.strftime('%Y-%m-%d'),
            'max_pain': int(max_pain),
            'btc_price_at_start_of_week': spot_start,
            'btc_price_at_expiry': spot_expiry,
            'is_quarterly': is_quarterly,
        })

output_path = '/home/bob/AI_sandbox/pinch-crypto-trading/backtest/data/maxpain_proxy.csv'
with open(output_path, 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['expiry_date','max_pain','btc_price_at_start_of_week','btc_price_at_expiry','is_quarterly'])
    writer.writeheader()
    writer.writerows(rows)

print(f"Generated {len(rows)} rows")
for r in rows[:5]:
    print(r)
print("...")
for r in rows[-5:]:
    print(r)
