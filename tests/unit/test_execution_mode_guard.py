import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from cthulu.execution.engine import ExecutionEngine, OrderRequest, OrderType
from core.shutdown import ShutdownHandler
from core.trading_loop import TradingLoop
from execution_mode import (
    ExecutionModeError,
    get_execution_mode,
    legacy_execution_enabled,
    require_legacy_execution,
    require_trading_enabled,
)
import main_multi
from main_multi import main as multi_symbol_main


def test_execution_mode_reads_file_and_rejects_invalid_values(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("OTHER=value\nCTHULU_EXECUTION_MODE=agentic\n", encoding="utf-8")
    assert get_execution_mode(env_file) == "agentic"

    env_file.write_text("CTHULU_EXECUTION_MODE=both\n", encoding="utf-8")
    try:
        get_execution_mode(env_file)
    except ExecutionModeError:
        pass
    else:
        raise AssertionError("invalid execution owner must fail closed")


def test_persistent_killswitch_blocks_trading_and_can_be_cleared(tmp_path, monkeypatch):
    import execution_mode

    marker = tmp_path / ".cthulu.killswitch"
    monkeypatch.setattr(execution_mode, "KILLSWITCH_FILE", marker)
    require_trading_enabled()

    marker.write_text("stopped\n", encoding="utf-8")
    try:
        require_trading_enabled()
    except ExecutionModeError as exc:
        assert "kill switch" in str(exc).lower()
    else:
        raise AssertionError("active kill switch must block trading")

    marker.unlink()
    require_trading_enabled()


def test_agentic_hybrid_keeps_legacy_execution_enabled():
    with patch("execution_mode.get_execution_mode", return_value="agentic"):
        assert legacy_execution_enabled()
        require_legacy_execution()


def test_legacy_loop_continues_analysis_and_management_in_agentic_mode():
    loop = TradingLoop.__new__(TradingLoop)
    loop.loop_count = 1
    loop.ctx = SimpleNamespace(
        position_manager=None,
        logger=MagicMock(),
        config={},
    )
    loop._ingest_market_data = MagicMock(return_value=object())
    loop._calculate_indicators = MagicMock(side_effect=lambda frame: frame)
    loop._check_pending_entries = MagicMock()
    loop._generate_signal = MagicMock(return_value=None)
    loop._adopt_external_trades = MagicMock()
    loop._monitor_positions = MagicMock()
    loop._check_connection_health = MagicMock()
    loop._report_performance_metrics = MagicMock()

    with patch("core.trading_loop.get_execution_mode", return_value="agentic"):
        loop._execute_loop_iteration()

    loop._check_pending_entries.assert_called_once()
    loop._generate_signal.assert_called_once()
    loop._adopt_external_trades.assert_called_once()
    loop._monitor_positions.assert_called_once()


def test_multi_symbol_guard_allows_legacy_in_agentic_mode():
    with patch("execution_mode.get_execution_mode", return_value="agentic"):
        require_legacy_execution()


def test_shutdown_does_not_close_agent_managed_shared_positions():
    handler = ShutdownHandler.__new__(ShutdownHandler)
    handler.logger = MagicMock()

    with patch("execution_mode.get_execution_mode", return_value="agentic"):
        handler._handle_open_positions()

    handler.logger.warning.assert_called_once()


def test_multi_symbol_launcher_starts_in_agentic_hybrid_mode():
    connector = MagicMock()
    connector.connect.return_value = True
    connector.get_account_info.return_value = {"balance": 1000.0, "equity": 1000.0}
    components = SimpleNamespace(connector=connector, config={"watchlist": ["BTCUSD", "GOLD"]})
    lock = SimpleNamespace(acquire=MagicMock(return_value=True), release=MagicMock())
    with patch("execution_mode.get_execution_mode", return_value="agentic"), \
         patch("main_multi.require_trading_enabled"), \
         patch("main_multi._get_singleton_lock", return_value=lock), \
         patch("main_multi._prepare_multi_components"), \
         patch("core.bootstrap.CthuluBootstrap") as bootstrap, \
         patch("core.multi_symbol.MultiSymbolOrchestrator") as orchestrator:
        bootstrap.return_value.bootstrap.return_value = components
        orchestrator.return_value.run = AsyncMock()
        with patch("sys.argv", ["main_multi.py", "--config", "config_multi.json"]):
            result = asyncio.run(multi_symbol_main())

    assert result == 0
    bootstrap.assert_called_once_with(logger=main_multi.logger)
    bootstrap.return_value.bootstrap.assert_called_once()
    bootstrap_args = bootstrap.return_value.bootstrap.call_args.args
    assert bootstrap_args[0] == "config_multi.json"
    assert bootstrap_args[1].enable_ml is None
    orchestrator.assert_called_once_with(components, components.config)
    orchestrator.return_value.run.assert_awaited_once()
    connector.disconnect.assert_called_once()
    lock.release.assert_called_once()


def test_multi_symbol_launcher_aborts_when_account_information_is_unavailable():
    connector = MagicMock()
    connector.connect.return_value = True
    connector.get_account_info.return_value = None
    components = SimpleNamespace(connector=connector, config={"watchlist": ["BTCUSD", "GOLD"]})
    lock = SimpleNamespace(acquire=MagicMock(return_value=True), release=MagicMock())

    with patch("execution_mode.get_execution_mode", return_value="agentic"), \
         patch("main_multi.require_trading_enabled"), \
         patch("main_multi._get_singleton_lock", return_value=lock), \
         patch("main_multi._prepare_multi_components"), \
         patch("core.bootstrap.CthuluBootstrap") as bootstrap, \
         patch("core.multi_symbol.MultiSymbolOrchestrator") as orchestrator:
        bootstrap.return_value.bootstrap.return_value = components
        with patch("sys.argv", ["main_multi.py", "--config", "config_multi.json"]):
            result = asyncio.run(multi_symbol_main())

    assert result == 1
    orchestrator.assert_not_called()
    connector.disconnect.assert_called_once()
    lock.release.assert_called_once()


def test_prepare_multi_components_adapts_bootstrap_components():
    engine = object()
    components = SimpleNamespace(
        connector=object(),
        risk_manager=object(),
        execution_engine=engine,
        position_tracker=object(),
        position_manager=object(),
        position_lifecycle=object(),
        trade_adoption_manager=object(),
        database=object(),
        exit_strategies=[],
    )

    main_multi._prepare_multi_components(components)

    assert components.mt5_connector is components.connector
    assert isinstance(components.risk_evaluator, main_multi._MultiRiskEvaluatorAdapter)
    assert isinstance(components.trade_manager, main_multi._MultiTradeManagerAdapter)
    assert isinstance(components.execution_engine, main_multi._MultiExecutionEngineAdapter)
    assert components.execution_engine.engine is engine
    assert isinstance(components.exit_coordinator, main_multi._MultiExitCoordinatorAdapter)


def test_multi_execution_adapter_maps_signal_to_shared_execution_engine():
    engine = MagicMock()
    engine.execute_order.return_value = 27
    adapter = main_multi._MultiExecutionEngineAdapter(SimpleNamespace(), engine)

    result = adapter.execute(
        {
            "symbol": "GOLD",
            "direction": "SHORT",
            "price": 100.0,
            "stop_loss": 101.0,
            "take_profit": 98.0,
            "strategy": "test",
        },
        0.02,
    )

    assert result == {"success": True, "ticket": 27, "price": 100.0, "volume": 0.02}
    engine.execute_order.assert_called_once_with(
        symbol="GOLD",
        order_type="sell",
        volume=0.02,
        sl=101.0,
        tp=98.0,
        comment="test",
    )


def test_multi_trade_manager_adapter_tracks_positions_with_current_component_types():
    from cthulu.position.manager import PositionInfo as ManagedPositionInfo
    from cthulu.position.tracker import PositionInfo as TrackedPositionInfo

    connector = SimpleNamespace(
        get_position_by_ticket=lambda ticket: {
            "symbol": "GOLD",
            "type": 1,
            "volume": 0.02,
            "price_open": 100.0,
            "price_current": 99.5,
            "sl": 101.0,
            "tp": 98.0,
            "profit": 0.01,
        }
    )
    tracker = MagicMock()
    lifecycle = MagicMock()
    manager = MagicMock()
    components = SimpleNamespace(
        connector=connector,
        position_tracker=tracker,
        position_lifecycle=lifecycle,
        position_manager=manager,
    )

    registered = main_multi._MultiTradeManagerAdapter(components).register_trade(
        27,
        {"symbol": "GOLD", "direction": "SHORT"},
        {"price": 100.0, "volume": 0.02},
    )

    assert registered
    tracked_position = tracker.track_position.call_args.args[0]
    managed_position = manager.add_position.call_args.args[0]
    assert isinstance(tracked_position, TrackedPositionInfo)
    assert tracked_position.type == "sell"
    assert isinstance(managed_position, ManagedPositionInfo)
    assert managed_position.side == "SELL"
    assert managed_position.stop_loss == 101.0
    assert managed_position.take_profit == 98.0
    lifecycle.persist_position.assert_called_once_with(tracked_position)


def test_multi_risk_adapter_converts_signal_dict_for_shared_risk_evaluator():
    risk_manager = MagicMock()
    risk_manager.approve.return_value = (True, "approved", 0.02)
    components = SimpleNamespace(
        connector=SimpleNamespace(
            get_account_info=lambda: {"balance": 1000, "equity": 1000}
        ),
        position_manager=SimpleNamespace(
            monitor_positions=lambda: [SimpleNamespace(symbol="GOLDm#")]
        ),
        risk_manager=risk_manager,
        config={"trading": {"timeframe": "TIMEFRAME_M1"}},
    )

    result = main_multi._MultiRiskEvaluatorAdapter(components).evaluate({
        "symbol": "GOLD",
        "direction": "SHORT",
        "price": 100.0,
        "stop_loss": 101.0,
        "take_profit": 98.0,
        "confidence": 0.8,
    })

    assert result == {"approved": True, "reason": "approved", "lot_size": 0.02}
    risk_signal, account, current_positions = risk_manager.approve.call_args.args
    assert risk_signal.side.name == "SHORT"
    assert risk_signal.timeframe == "TIMEFRAME_M1"
    assert account["balance"] == 1000
    assert current_positions == 1

def test_trade_cli_execution_gate_accepts_legacy_in_agentic_mode():
    with patch("execution_mode.get_execution_mode", return_value="agentic"):
        require_legacy_execution()


def test_legacy_engine_execution_mode_gate_is_not_blocking_hybrid_mode():
    connector = MagicMock()
    engine = ExecutionEngine(connector)
    request = OrderRequest("GOLD", "BUY", 0.01, OrderType.MARKET, sl=10.0, tp=20.0)
    with patch("cthulu.execution.engine.get_execution_mode", return_value="agentic"):
        placed = engine.place_order(request)
    assert "disabled" not in (placed.error or "").lower()


def test_agent_execution_remains_only_in_agentic_mode():
    from execution_mode import agent_execution_enabled
    assert agent_execution_enabled("agentic")
    assert not agent_execution_enabled("legacy")
