#!/usr/bin/env python3
"""Test risk evaluator hedge protection."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Mock connector with existing SELL position
class MockPosition:
    def __init__(self, symbol, position_type):
        self.symbol = symbol
        self.type = position_type  # 0=BUY, 1=SELL

class MockConnector:
    def get_account_info(self):
        return {'balance': 100.0}
    
    def get_positions(self):
        # Simulate existing SELL position on GOLDm#
        return [MockPosition('GOLDm#', 1)]  # 1 = SELL

# Test
from risk.evaluator import RiskEvaluator

config = {
    'max_positions': 5,
    'max_positions_per_symbol': 3,
    'max_risk_per_trade': 0.02,
    'min_balance_threshold': 10.0,
    'default_lot_size': 0.1
}

connector = MockConnector()
evaluator = RiskEvaluator(config, connector)

# Test 1: BUY signal when SELL exists (should reject - hedge)
buy_signal = {
    'symbol': 'GOLDm#',
    'direction': 'buy',
    'confidence': 0.8
}

result = evaluator.evaluate(buy_signal)
print(f"\nTest 1: BUY when SELL exists")
print(f"  Approved: {result['approved']}")
print(f"  Reason: {result['reason']}")
assert not result['approved'], "Should reject hedge!"
assert 'Hedge rejected' in result['reason'], "Should mention hedge"

# Test 2: SELL signal when SELL exists (should allow - same direction)
sell_signal = {
    'symbol': 'GOLDm#',
    'direction': 'sell',
    'confidence': 0.8
}

result = evaluator.evaluate(sell_signal)
print(f"\nTest 2: SELL when SELL exists")
print(f"  Approved: {result['approved']}")
print(f"  Reason: {result['reason']}")
assert result['approved'], "Should allow same direction!"

# Test 3: BUY on different symbol (should allow)
btc_buy_signal = {
    'symbol': 'BTCUSD#',
    'direction': 'buy',
    'confidence': 0.8
}

result = evaluator.evaluate(btc_buy_signal)
print(f"\nTest 3: BUY on different symbol")
print(f"  Approved: {result['approved']}")
print(f"  Reason: {result['reason']}")
assert result['approved'], "Should allow different symbol!"

print("\n✅ All hedge protection tests passed!")
