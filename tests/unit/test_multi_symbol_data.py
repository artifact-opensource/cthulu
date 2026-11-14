from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from cthulu.connector.mt5_connector import ConnectionConfig, MT5Connector
from core.multi_symbol import MultiSymbolOrchestrator


def test_mt5_connector_maps_legacy_gold_suffix_to_exact_broker_symbol():
    connector = MT5Connector(ConnectionConfig(login=0, password="", server=""))
    fake_mt5 = SimpleNamespace(
        symbols_get=lambda: [SimpleNamespace(name="GoldmSachs"), SimpleNamespace(name="GOLD")]
    )
    with patch("cthulu.connector.mt5_connector.mt5", fake_mt5):
        assert connector._find_matching_symbol("GOLDm#") == ["GOLD"]


def test_multi_symbol_fetch_uses_mt5_rates_and_shared_normalizer():
    frame = object()
    connector = MagicMock()
    connector.get_rates.return_value = [{"time": 1, "close": 2000}]
    data_layer = MagicMock()
    data_layer.normalize_rates.return_value = frame
    orchestrator = MultiSymbolOrchestrator.__new__(MultiSymbolOrchestrator)
    orchestrator.components = SimpleNamespace(mt5_connector=connector, data_layer=data_layer)
    ctx = SimpleNamespace(timeframe="M5")

    with patch("cthulu.connector.mt5_connector.mt5", SimpleNamespace(TIMEFRAME_M5=5)):
        result = orchestrator._fetch_symbol_data("GOLDm#", ctx)

    assert result is frame
    connector.get_rates.assert_called_once_with(symbol="GOLDm#", timeframe=5, count=200)
    data_layer.normalize_rates.assert_called_once_with(connector.get_rates.return_value, symbol="GOLDm#")


def test_multi_symbol_aliases_reuse_legacy_position_context():
    gold_context = object()
    oil_context = object()
    orchestrator = MultiSymbolOrchestrator.__new__(MultiSymbolOrchestrator)
    orchestrator.symbols = {"GOLDm#": gold_context, "WTI": oil_context}
    orchestrator._correlation_groups = {
        "gold": ["GOLDm#", "GOLD"],
        "oil": ["WTI", "OILCash"],
    }

    assert orchestrator._get_symbol_context("GOLD") is gold_context
    assert orchestrator._get_symbol_context("OILCash") is oil_context
    assert orchestrator._get_correlation_group("GOLD") == "gold"
    assert orchestrator._get_correlation_group("OILCash") == "oil"
