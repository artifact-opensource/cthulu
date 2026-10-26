from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd

from core.trading_loop import TradingLoop


def test_dry_run_skips_external_trade_adoption():
    loop = TradingLoop.__new__(TradingLoop)
    loop.ctx = SimpleNamespace(
        dry_run=True,
        logger=MagicMock(),
        trade_adoption_policy=SimpleNamespace(enabled=True),
        trade_adoption_manager=MagicMock(),
    )

    loop._adopt_external_trades()

    loop.ctx.trade_adoption_manager.scan_and_adopt.assert_not_called()


def test_dry_run_skips_profit_scaling_and_dynamic_sltp():
    position = SimpleNamespace(unrealized_pnl=0, ticket=123)
    scaler = MagicMock()
    position_manager = MagicMock()
    position_manager.monitor_positions.return_value = [position]
    connector = MagicMock()
    connector.get_account_info.return_value = {"balance": 1000, "equity": 1000}

    loop = TradingLoop.__new__(TradingLoop)
    loop.ctx = SimpleNamespace(
        dry_run=True,
        logger=MagicMock(),
        position_manager=position_manager,
        connector=connector,
        profit_scaler=scaler,
        cognition_engine=None,
        dynamic_sltp_manager=MagicMock(),
        config={},
        exit_strategies=[],
    )
    loop._apply_dynamic_sltp = MagicMock()

    loop._monitor_positions(pd.DataFrame({"atr": [1.0]}))

    scaler.run_scaling_cycle.assert_not_called()
    loop._apply_dynamic_sltp.assert_not_called()
