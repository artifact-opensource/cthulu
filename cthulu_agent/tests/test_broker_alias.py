from types import SimpleNamespace
from unittest.mock import MagicMock

from cthulu_agent.broker import MT5Broker


def test_xauusd_alias_resolves_and_reverses_for_legacy_positions():
    broker = MT5Broker()
    broker.mt5 = SimpleNamespace(
        symbol_info=lambda symbol: object() if symbol == "GOLD" else None,
        symbols_get=lambda: [SimpleNamespace(name="GoldmSachs"), SimpleNamespace(name="GOLD")],
        symbol_select=MagicMock(return_value=True),
    )

    assert broker._sym("XAUUSD") == "GOLD"
    assert broker._back("GOLD") == "XAUUSD"
    broker.mt5.symbol_select.assert_called_once_with("GOLD", True)
