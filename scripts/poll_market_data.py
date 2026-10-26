#!/usr/bin/env python3
"""Simple poller to fetch latest bars and print or store them.
Usage: python3 scripts/poll_market_data.py --symbol EURUSD --tf M1 --count 10
"""

import argparse
import requests

parser = argparse.ArgumentParser()
parser.add_argument('--host', default='127.0.0.1')
parser.add_argument('--port', type=int, default=9002)
parser.add_argument('--symbol', default='EURUSD')
parser.add_argument('--tf', default='M1')
parser.add_argument('--count', type=int, default=10)
args = parser.parse_args()

url = f'http://{args.host}:{args.port}/latest_bars?symbol={args.symbol}&tf={args.tf}&count={args.count}'
try:
    r = requests.get(url, timeout=5)
    r.raise_for_status()
    data = r.json()
    bars = data.get('bars', [])
    for b in reversed(bars):
        print(f"{b['time']} O:{b['open']} H:{b['high']} L:{b['low']} C:{b['close']} V:{b['volume']}")
except Exception as e:
    print('error:', e)
