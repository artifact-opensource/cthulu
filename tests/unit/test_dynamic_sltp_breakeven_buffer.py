from cthulu.risk.dynamic_sltp import DynamicSLTPManager


def test_breakeven_buffer_capped_by_sl_distance():
    mgr = DynamicSLTPManager(config={})

    # Small ATR -> small sl_distance
    atr = 0.2
    entry = 4499.41
    side = 'SELL'
    balance = 1000
    equity = 1000
    drawdown = 0
    initial_balance = 1000

    dyn = mgr.calculate_dynamic_sltp(entry_price=entry, side=side, atr=atr, balance=balance, equity=equity, drawdown_pct=drawdown, initial_balance=initial_balance)

    # sl_distance should be small: atr*base_sl_atr_mult
    sl_distance = dyn.sl_distance
    assert sl_distance is not None and sl_distance > 0

    # Now simulate should_move_to_breakeven using that sl_distance: buffer must be <= sl_distance * 0.5
    should, new_sl = mgr.should_move_to_breakeven(ticket=1, entry_price=entry, current_price=entry - (sl_distance * 0.6), side=side, current_sl=None, breakeven_level=dyn.breakeven_level, sl_distance=sl_distance)
    assert should is True
    buffer_used = entry - new_sl
    assert buffer_used <= sl_distance * 0.5 + 1e-6
