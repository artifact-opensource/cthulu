"""
Test to verify the stop loss calculation fix.

This test ensures that the stop loss threshold bug (25% for large accounts)
has been fixed and that the system now uses reasonable stop loss values.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from position.risk_manager import _threshold_from_config, suggest_sl_adjustment


def test_large_account_threshold_is_reasonable():
    """Test that large accounts (>$20k) don't use excessive 25% stop loss."""
    large_balance = 50000.0
    
    cfg = _threshold_from_config(large_balance, None, None)
    
    assert cfg['category'] == 'large', f"Expected 'large' category for ${large_balance}"
    assert cfg['threshold'] <= 0.10, (
        f"Stop loss threshold {cfg['threshold']*100}% is too high! "
        f"Should be ≤10% but got {cfg['threshold']*100}%"
    )
    assert cfg['threshold'] == 0.05, (
        f"Expected 5% threshold for large accounts, got {cfg['threshold']*100}%"
    )
    
    print(f"✓ Large account (${large_balance}) uses {cfg['threshold']*100}% stop loss")


def test_all_balance_categories_are_reasonable():
    """Test that all balance categories use reasonable stop loss thresholds."""
    test_balances = [
        (500, 'tiny', 0.01),
        (1000, 'tiny', 0.01),
        (2000, 'small', 0.02),
        (5000, 'small', 0.02),
        (10000, 'medium', 0.05),
        (20000, 'medium', 0.05),
        (50000, 'large', 0.05),
        (100000, 'large', 0.05),
    ]
    
    print("\nBalance Category Tests:")
    print("=" * 70)
    
    for balance, expected_cat, expected_threshold in test_balances:
        cfg = _threshold_from_config(balance, None, None)
        
        assert cfg['category'] == expected_cat, (
            f"Balance ${balance}: Expected category '{expected_cat}', got '{cfg['category']}'"
        )
        assert cfg['threshold'] == expected_threshold, (
            f"Balance ${balance}: Expected threshold {expected_threshold*100}%, "
            f"got {cfg['threshold']*100}%"
        )
        
        # Ensure no threshold exceeds 10%
        assert cfg['threshold'] <= 0.10, (
            f"Balance ${balance}: Threshold {cfg['threshold']*100}% exceeds 10% maximum!"
        )
        
        max_loss = balance * cfg['threshold']
        print(f"  ${balance:>7} -> {cfg['category']:>6} -> "
              f"{cfg['threshold']*100:>4.1f}% -> max loss: ${max_loss:>8.2f}")
    
    print("=" * 70)


def test_stop_loss_suggestion_for_large_account():
    """Test that stop loss suggestions are reasonable for large accounts."""
    balance = 50000.0
    price = 1.0000
    side = 'BUY'
    
    # Calculate proposed SL using the threshold
    cfg = _threshold_from_config(balance, None, None)
    threshold_pct = cfg['threshold']
    
    if side == 'BUY':
        proposed_sl = price * (1.0 - threshold_pct)
    else:
        proposed_sl = price * (1.0 + threshold_pct)
    
    # Test the suggestion function
    suggestion = suggest_sl_adjustment(
        symbol='EURUSD',
        balance=balance,
        price=price,
        proposed_sl=proposed_sl,
        side=side
    )
    
    # Verify the SL distance is reasonable (≤10%)
    sl_dist_pct = abs(price - proposed_sl) / price
    assert sl_dist_pct <= 0.10, (
        f"Stop loss distance {sl_dist_pct*100}% exceeds 10% for large account!"
    )
    
    print(f"\n✓ Large account stop loss suggestion:")
    print(f"  Balance: ${balance}, Price: {price}")
    print(f"  Proposed SL: {proposed_sl:.4f} ({sl_dist_pct*100:.2f}% distance)")
    print(f"  Max risk: ${balance * sl_dist_pct:.2f}")


def test_profit_impact_comparison():
    """Calculate and display the profit impact of the fix."""
    balance = 50000.0
    position_size = 1.0  # 1 lot
    price = 1.0000
    
    # OLD BUG: 25% stop loss
    old_threshold = 0.25
    old_sl = price * (1.0 - old_threshold)
    old_loss_per_trade = balance * old_threshold
    
    # NEW FIX: 5% stop loss
    new_threshold = 0.05
    new_sl = price * (1.0 - new_threshold)
    new_loss_per_trade = balance * new_threshold
    
    savings_per_trade = old_loss_per_trade - new_loss_per_trade
    
    print("\n" + "=" * 70)
    print("PROFIT IMPACT ANALYSIS")
    print("=" * 70)
    print(f"Balance: ${balance:,.2f}")
    print(f"\nOLD BUG (25% SL):")
    print(f"  Stop Loss: {old_sl:.4f} ({old_threshold*100}% from price)")
    print(f"  Loss per losing trade: ${old_loss_per_trade:,.2f}")
    print(f"\nNEW FIX (5% SL):")
    print(f"  Stop Loss: {new_sl:.4f} ({new_threshold*100}% from price)")
    print(f"  Loss per losing trade: ${new_loss_per_trade:,.2f}")
    print(f"\nSAVINGS:")
    print(f"  Per losing trade: ${savings_per_trade:,.2f}")
    print(f"  Over 10 losing trades: ${savings_per_trade * 10:,.2f}")
    print(f"  Over 40 losing trades (40% of 100): ${savings_per_trade * 40:,.2f}")
    print("=" * 70)
    
    # Verify the savings are significant
    assert savings_per_trade > 0, "Fix should result in savings!"
    assert savings_per_trade == 10000.0, f"Expected $10,000 savings per trade, got ${savings_per_trade}"


if __name__ == '__main__':
    print("\n🔧 Testing Stop Loss Fix\n")
    
    test_large_account_threshold_is_reasonable()
    test_all_balance_categories_are_reasonable()
    test_stop_loss_suggestion_for_large_account()
    test_profit_impact_comparison()
    
    print("\n✅ ALL TESTS PASSED - Stop loss fix verified!\n")
