#!/usr/bin/env python3
"""
Kalshi Market Scanner — Daily odds check for key prediction markets.
Posts to Discord #investments via Pinch.
Tracks odds changes and flags opportunities.

Usage:
    python3 kalshi_scanner.py              # Full scan + Discord alert
    python3 kalshi_scanner.py --quiet      # Scan only, no Discord
    python3 kalshi_scanner.py --json       # Output JSON to stdout
"""

import sys
import json
import os
import time
import subprocess
from datetime import datetime, timezone, timedelta

# Kalshi client
sys.path.insert(0, '/home/bob/.openclaw/workspace-pinch/.secrets')
from kalshi_client import kalshi_request

ET = timezone(timedelta(hours=-4))
STATE_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'state')
KALSHI_STATE = os.path.join(STATE_DIR, 'kalshi_odds.json')

# ── Key Markets to Track ──────────────────────────────────────────────────

TRACKED_MARKETS = [
    # Recession / Economic path
    'KXRECSSNBER-26',           # Recession in 2026
    'KXECONPATH-26-STAG',       # Stagflation 2026
    # Add more tickers as we find interesting markets
]

# Series to search for additional markets
SERIES_SEARCH = [
    ('KXFEDFF', 'Fed Funds Rate'),
    ('KXRECSSNBER', 'Recession'),
    ('KXECONPATH', 'Economic Path'),
    ('KXCPIYOY', 'CPI YoY'),
    ('KXUNRATE', 'Unemployment'),
    ('KXLCPIMAXYOY', 'CPI Max YoY'),
]

# ── Position rules ────────────────────────────────────────────────────────

MAX_POSITION_DOLLARS = 50   # Max $50 per contract (1% of ~$270 balance)
TAKE_PROFIT_PCT = 100       # Exit at +100%
STOP_LOSS_PCT = 50          # Exit at -50%


def get_market(ticker):
    """Fetch a single market's data."""
    try:
        resp = kalshi_request('GET', f'/markets/{ticker}')
        if resp.status_code == 200:
            return resp.json().get('market', {})
    except Exception as e:
        print(f"Error fetching {ticker}: {e}", file=sys.stderr)
    return None


def get_balance():
    """Get current Kalshi balance and positions."""
    try:
        bal = kalshi_request('GET', '/portfolio/balance')
        pos = kalshi_request('GET', '/portfolio/positions')
        if bal.status_code == 200 and pos.status_code == 200:
            return bal.json(), pos.json()
    except Exception as e:
        print(f"Error fetching portfolio: {e}", file=sys.stderr)
    return None, None


def search_series(series_ticker, limit=5):
    """Search for markets in a series."""
    try:
        resp = kalshi_request('GET', '/markets', params={
            'limit': limit,
            'status': 'active',
            'series_ticker': series_ticker,
        })
        if resp.status_code == 200:
            return resp.json().get('markets', [])
    except:
        pass
    return []


def load_previous_odds():
    """Load previous scan results for change detection."""
    try:
        if os.path.exists(KALSHI_STATE):
            with open(KALSHI_STATE) as f:
                return json.load(f)
    except:
        pass
    return {}


def save_odds(data):
    """Save current scan results."""
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(KALSHI_STATE, 'w') as f:
        json.dump(data, f, indent=2)


def send_discord(message):
    """Send alert to Discord #investments channel."""
    try:
        subprocess.run([
            '/home/bob/.npm-global/bin/openclaw', 'message', 'send',
            '--channel', 'discord', '--account', 'pinch',
            '--target', '1476110474377429124',
            '-m', message
        ], capture_output=True, timeout=30)
    except Exception as e:
        print(f"Discord send failed: {e}", file=sys.stderr)


def scan():
    """Run full Kalshi market scan."""
    now = datetime.now(ET)
    previous = load_previous_odds()
    prev_markets = previous.get('markets', {})

    # Get balance and positions
    bal_data, pos_data = get_balance()
    balance = bal_data.get('balance', 0) / 100 if bal_data else 0
    portfolio_value = bal_data.get('portfolio_value', 0) / 100 if bal_data else 0

    # Parse positions
    positions = {}
    if pos_data:
        for mp in pos_data.get('market_positions', []):
            if float(mp.get('position_fp', 0)) > 0 or float(mp.get('market_exposure_dollars', '0')) > 0:
                positions[mp['ticker']] = {
                    'contracts': float(mp.get('position_fp', 0)),
                    'exposure': float(mp.get('market_exposure_dollars', '0')),
                    'realized_pnl': float(mp.get('realized_pnl_dollars', '0')),
                    'total_cost': float(mp.get('total_traded_dollars', '0')),
                }

    # Scan tracked markets
    markets = {}
    for ticker in TRACKED_MARKETS:
        m = get_market(ticker)
        if m:
            yes_bid = float(m.get('yes_bid_dollars', '0'))
            yes_ask = float(m.get('yes_ask_dollars', '0'))
            last = float(m.get('last_price_dollars', '0'))
            prev_last = prev_markets.get(ticker, {}).get('last', 0)
            change = (last - prev_last) if prev_last else 0
            volume_24h = float(m.get('volume_24h_fp', '0'))
            oi = float(m.get('open_interest_fp', '0'))

            markets[ticker] = {
                'title': m.get('title', ticker),
                'yes_bid': yes_bid,
                'yes_ask': yes_ask,
                'last': last,
                'change': change,
                'volume_24h': volume_24h,
                'open_interest': oi,
                'status': m.get('status', 'unknown'),
                'expires': m.get('expected_expiration_time', ''),
            }
        time.sleep(0.3)  # Rate limit

    # Search for additional interesting markets
    discovered = []
    for series, label in SERIES_SEARCH:
        found = search_series(series, limit=3)
        for m in found:
            t = m.get('ticker', '')
            if t not in TRACKED_MARKETS and t not in markets:
                last = float(m.get('last_price_dollars', '0'))
                vol = float(m.get('volume_24h_fp', '0'))
                if vol > 100:  # Only markets with activity
                    discovered.append({
                        'ticker': t,
                        'title': m.get('title', t),
                        'last': last,
                        'volume_24h': vol,
                        'series': label,
                    })
        time.sleep(0.3)

    # Build result
    result = {
        'timestamp': now.isoformat(),
        'balance': balance,
        'portfolio_value': portfolio_value,
        'total': balance + portfolio_value,
        'positions': positions,
        'markets': markets,
        'discovered': discovered[:10],  # Top 10 by volume
    }

    # Save
    save_odds(result)

    return result


def format_discord(result):
    """Format scan results for Discord."""
    lines = [
        f"🎰 **KALSHI DAILY ODDS** — {result['timestamp'][:10]}",
        f"💰 Balance: ${result['balance']:.2f} | Portfolio: ${result['portfolio_value']:.2f} | Total: ${result['total']:.2f}",
        "",
    ]

    # Positions
    if result['positions']:
        lines.append("📋 **ACTIVE POSITIONS:**")
        for ticker, pos in result['positions'].items():
            market = result['markets'].get(ticker, {})
            title = market.get('title', ticker)
            last = market.get('last', 0)
            cost_per = pos['total_cost'] / pos['contracts'] if pos['contracts'] > 0 else 0
            current_val = last * pos['contracts']
            pnl = current_val - pos['total_cost'] + pos['realized_pnl']
            pnl_pct = (pnl / pos['total_cost'] * 100) if pos['total_cost'] > 0 else 0
            emoji = "🟢" if pnl >= 0 else "🔴"
            lines.append(f"  {emoji} **{ticker}** ({pos['contracts']:.0f} contracts @ ${cost_per:.2f}) → now ${last:.2f} | P&L: ${pnl:+.2f} ({pnl_pct:+.1f}%)")
        lines.append("")

    # Key markets
    lines.append("📊 **KEY MARKETS:**")
    for ticker, m in result['markets'].items():
        change_str = f" ({m['change']:+.2f})" if m['change'] != 0 else ""
        emoji = "📈" if m['change'] > 0.02 else "📉" if m['change'] < -0.02 else "➡️"
        lines.append(f"  {emoji} **{m['title']}**: YES {m['last']:.0%}{change_str} | Vol 24h: {m['volume_24h']:,.0f}")

    # Discovered markets
    if result.get('discovered'):
        lines.append("")
        lines.append("🔍 **OTHER ACTIVE MARKETS:**")
        for d in result['discovered'][:5]:
            lines.append(f"  • {d['title']}: YES {d['last']:.0%} | Vol: {d['volume_24h']:,.0f}")

    return "\n".join(lines)


if __name__ == '__main__':
    quiet = '--quiet' in sys.argv
    as_json = '--json' in sys.argv

    print(f"🎰 Kalshi Scanner — {datetime.now(ET).strftime('%Y-%m-%d %H:%M ET')}")
    result = scan()

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        msg = format_discord(result)
        print(msg)
        if not quiet:
            send_discord(msg)
            print("\n✅ Discord alert sent")

    print(f"\nBalance: ${result['balance']:.2f} | Positions: {len(result['positions'])}")
