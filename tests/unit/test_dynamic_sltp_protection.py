from cthulu.risk.dynamic_sltp import DynamicSLTPManager


def test_initial_sltp_uses_dynamic_levels_and_broker_tick_size():
    manager = DynamicSLTPManager({})

    levels = manager.calculate_initial_sltp(
        ticket=7,
        direction="BUY",
        entry_price=100.0,
        atr=1.0,
        balance=1000.0,
        equity=1000.0,
        drawdown_pct=0.0,
        initial_balance=1000.0,
        symbol_info={"point": 0.01, "tick_size": 0.25, "name": "TEST"},
    )

    assert levels["sl"] == 98.0
    assert levels["tp"] == 104.0
    assert levels["sl"] / 0.25 == round(levels["sl"] / 0.25)
    assert levels["tp"] / 0.25 == round(levels["tp"] / 0.25)


def test_survival_mode_locks_profit_with_sl_without_moving_tp_to_market():
    manager = DynamicSLTPManager({
        "survival_drawdown_pct": 5.0,
        "breakeven_activation_pct": 10.0,
    })

    update = manager.update_position_sltp(
        ticket=11,
        entry_price=100.0,
        current_price=100.5,
        side="BUY",
        current_sl=99.0,
        current_tp=104.0,
        atr=1.0,
        balance=100.0,
        equity=80.0,
        drawdown_pct=10.0,
        initial_balance=100.0,
    )

    assert update["action"] == "survival_lock"
    assert update["update_sl"] is True
    assert update["new_sl"] > 99.0
    assert update["update_tp"] is False
    assert update["new_tp"] == 104.0
