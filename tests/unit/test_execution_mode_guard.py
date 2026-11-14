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
    components = SimpleNamespace(mt5_connector=connector, config={"watchlist": ["BTCUSD#", "GOLDm#"]})
    with patch("execution_mode.get_execution_mode", return_value="agentic"), \
         patch("main_multi.require_trading_enabled"), \
         patch("core.bootstrap.CthuluBootstrap") as bootstrap, \
         patch("core.multi_symbol.MultiSymbolOrchestrator") as orchestrator:
        bootstrap.return_value.bootstrap.return_value = components
        orchestrator.return_value.run = AsyncMock()
        with patch("sys.argv", ["main_multi.py", "config_multi.json"]):
            asyncio.run(multi_symbol_main())

    bootstrap.assert_called_once_with("config_multi.json")
    orchestrator.assert_called_once_with(components, components.config)
    orchestrator.return_value.run.assert_awaited_once()

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
