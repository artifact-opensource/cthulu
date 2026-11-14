import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

from cthulu.core.multi_symbol import MultiSymbolOrchestrator, SymbolContext
from cthulu.position.manager import PositionInfo
from cthulu.risk.dynamic_sltp import DynamicSLTPManager


def test_multi_symbol_manager_protects_orphan_positions():
    position = PositionInfo(
        ticket=23,
        symbol="EURUSD",
        volume=0.1,
        open_price=1.1,
        current_price=1.1,
        side="BUY",
        stop_loss=0.0,
        take_profit=0.0,
    )
    manager = DynamicSLTPManager({})
    modify_position = Mock(return_value=True)
    orchestrator = MultiSymbolOrchestrator.__new__(MultiSymbolOrchestrator)
    orchestrator.timeframe = "M5"
    orchestrator.symbols = {
        "EURUSD": SymbolContext(symbol="EURUSD", indicators={"ATR": 0.001}),
    }
    orchestrator.components = SimpleNamespace(
        dynamic_sltp_manager=manager,
        position_manager=SimpleNamespace(monitor_positions=lambda: [position]),
        connector=SimpleNamespace(
            get_account_info=lambda: {"balance": 1000.0, "equity": 1000.0},
            get_symbol_info=lambda symbol: {
                "name": symbol,
                "point": 0.0001,
                "trade_stops_level": 10,
            },
        ),
        position_lifecycle=SimpleNamespace(modify_position=modify_position),
    )

    asyncio.run(orchestrator._manage_all_positions())

    modify_position.assert_called_once()
    _, kwargs = modify_position.call_args
    assert kwargs["sl"] < position.current_price
    assert kwargs["tp"] > position.current_price
