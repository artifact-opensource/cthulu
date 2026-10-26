import sys
from pathlib import Path
import pytest

# Ensure workspace root is on sys.path so `config` package is importable during tests
ROOT = str(Path(__file__).resolve().parents[1])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config.wizard import parse_natural_language_intent


@pytest.mark.parametrize(
    "text,expected",
    [
        (
            "Aggressive GOLD#m M15 H1, 2% risk, $100 max loss",
            {
                'mindset': 'aggressive',
                'symbol': 'GOLD#M',
                'timeframes': ['TIMEFRAME_M15', 'TIMEFRAME_H1'],
                'position_size_pct': 2.0,
                'max_daily_loss': 100.0,
            },
        ),
        (
            "Conservative EURUSD 1m, 0.5% position size, max loss $50",
            {
                'mindset': 'conservative',
                'symbol': 'EURUSD',
                'timeframes': ['TIMEFRAME_M1'],
                'position_size_pct': 0.5,
                'max_daily_loss': 50.0,
            },
        ),
        (
            "Balanced BTCUSD 5m, 1%",
            {
                'mindset': 'balanced',
                'symbol': 'BTCUSD',
                'timeframes': ['TIMEFRAME_M5'],
                'position_size_pct': 1.0,
            },
        ),
        (
            "I want to trade gold on H1 and M15, balanced",
            {
                'mindset': 'balanced',
                'symbol': 'XAUUSD',
                'timeframes': ['TIMEFRAME_M15', 'TIMEFRAME_H1'],
            },
        ),
        (
            "Use EURUSD#, daily, 2 percent, 200 dollars max loss",
            {
                'symbol': 'EURUSD#',
                'timeframes': ['TIMEFRAME_D1'],
                'position_size_pct': 2.0,
                'max_daily_loss': 200.0,
            },
        ),
    ],
)
def test_parse_intent(text, expected):
    intent = parse_natural_language_intent(text)
    # Ensure expected keys exist and match where provided
    for k, v in expected.items():
        assert k in intent, f"Expected key '{k}' in intent for input: {text}\nGot: {intent}"
        assert intent[k] == v, f"Value mismatch for '{k}' for input: {text}\nExpected: {v}\nGot: {intent[k]}"




