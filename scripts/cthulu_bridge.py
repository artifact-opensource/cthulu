#!/usr/bin/env python3
"""Simple bridge that polls latest bars and posts a trade job when a condition
is met (e.g., last close > prev close -> BUY).
"""
import argparse
import requests
import time

parser = argparse.ArgumentParser()
parser.add_argument('--host', default='127.0.0.1')
parser.add_argument('--port', type=int, default=9002)
parser.add_argument('--symbol', default='EURUSD')
parser.add_argument('--tf', default='M1')
parser.add_argument('--count', type=int, default=2)
args = parser.parse_args()

BASE = f'http://{args.host}:{args.port}'

def get_bars():
    url = f"{BASE}/latest_bars?symbol={args.symbol}&tf={args.tf}&count={args.count}"
    r = requests.get(url, timeout=5)
    if r.status_code != 200:
        return []
    data = r.json()
    return data.get('bars', [])


def post_trade(cmd, symbol, volume=0.01):
    url = f"{BASE}/webhook"
    # Simple confluence heuristic: if price move > 5 pips, send market order; else send limit order at slight improvement
    prev = bars[-2]
    last = bars[-1]
    delta = abs(float(last['close']) - float(prev['close']))
    # threshold for market order (for EURUSD ~ 0.0005 = 5 pips)
    threshold = 0.0005
    if delta >= threshold:
        order_type = 'market'
        price = 0
    else:
        order_type = 'limit'
        offset = 0.0001
        if cmd == 'BUY':
            price = max(0, float(last['close']) - offset)
        else:
            price = float(last['close']) + offset

    payload = {
        'command': cmd,
        'symbol': symbol,
        'volume': volume,
        'price': price,
        'order_type': order_type,
        'sl': 0,
        'tp': 0
    }
    r = requests.post(url, json=payload, timeout=5)
    r.raise_for_status()
    print('posted trade job:', r.json())


if __name__ == '__main__':
    bars = get_bars()
    if len(bars) < 2:
        print('not enough bars, exiting')
        raise SystemExit(1)
    prev = bars[-2]
    last = bars[-1]
    print('prev close', prev['close'], 'last close', last['close'])
    if float(last['close']) > float(prev['close']):
        print('signal BUY')
        post_trade('BUY', args.symbol)
    elif float(last['close']) < float(prev['close']):
        print('signal SELL')
        post_trade('SELL', args.symbol)
    else:
        print('no signal')
