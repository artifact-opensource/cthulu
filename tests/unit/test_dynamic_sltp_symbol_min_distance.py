import math
from cthulu.risk.dynamic_sltp import DynamicSLTPManager


def test_min_distance_enforced_and_rounded_buy():
    cfg = {
        'min_sl_distance_pct': 0.05,  # 0.05%
        'min_sl_distance_atr_mult': 0.1,
    }
    mgr = DynamicSLTPManager(cfg)
    entry = 1.20000
    atr = 0.00001
    symbol_info = {'name': 'EURUSD', 'point': 0.00001, 'trade_stops_level': 5}

    dyn = mgr.calculate_dynamic_sltp(
        entry_price=entry,
        side='BUY',
        atr=atr,
        balance=1000,
        equity=1000,
        drawdown_pct=0,
        initial_balance=1000,
        symbol_info=symbol_info
    )

    # Effective mins: pct = entry*(0.05/100)=0.0006, atr*0.1=0.000001, symbol=point*5=0.00005
    assert dyn.sl_distance >= 0.0006 - 1e-12

    # Ensure stop_loss is aligned to tick
    tick = symbol_info['point']
    assert abs(round(dyn.stop_loss / tick) * tick - dyn.stop_loss) < 1e-12


def test_min_distance_enforced_and_rounded_sell():
    cfg = {
        'min_sl_distance_pct': 0.05,
        'min_sl_distance_atr_mult': 0.1,
    }
    mgr = DynamicSLTPManager(cfg)
    entry = 1.20000
    atr = 0.00001
    symbol_info = {'name': 'EURUSD', 'point': 0.00001, 'trade_stops_level': 5}

    dyn = mgr.calculate_dynamic_sltp(
        entry_price=entry,
        side='SELL',
        atr=atr,
        balance=1000,
        equity=1000,
        drawdown_pct=0,
        initial_balance=1000,
        symbol_info=symbol_info
    )

    assert dyn.sl_distance >= 0.0006 - 1e-12

    tick = symbol_info['point']
    assert abs(round(dyn.stop_loss / tick) * tick - dyn.stop_loss) < 1e-12
