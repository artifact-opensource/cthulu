from types import SimpleNamespace

from cthulu.connector import mt5_connector
from cthulu.connector.mt5_connector import ConnectionConfig, MT5Connector


def test_wti_resolves_to_available_oilcash_symbol(monkeypatch):
    selected = []
    monkeypatch.setattr(
        mt5_connector.mt5,
        "symbols_get",
        lambda: [SimpleNamespace(name="OILCash")],
    )
    monkeypatch.setattr(
        mt5_connector.mt5,
        "symbol_select",
        lambda symbol, enable: selected.append(symbol) or symbol == "OILCash",
    )

    connector = MT5Connector(ConnectionConfig(login=1, password="", server=""))
    connector.get_symbol_info = lambda symbol: {
        "point": 0.01,
        "volume_min": 0.01,
    }

    assert connector.ensure_symbol_selected("WTI") == "OILCash"
    assert selected == ["WTI", "OILCash"]


def test_profitable_stop_has_zero_remaining_downside_risk(monkeypatch):
    connector = MT5Connector(ConnectionConfig(login=1, password="", server=""))
    connector.is_connected = lambda: True
    monkeypatch.setattr(mt5_connector.mt5, "order_calc_profit", lambda *args: 8.0)

    assert connector.calculate_loss_at_stop(
        "OILCash", "BUY", 0.65, 103.72, 103.80
    ) == 0.0


def test_losing_stop_returns_account_currency_loss(monkeypatch):
    connector = MT5Connector(ConnectionConfig(login=1, password="", server=""))
    connector.is_connected = lambda: True
    monkeypatch.setattr(mt5_connector.mt5, "order_calc_profit", lambda *args: -12.5)

    assert connector.calculate_loss_at_stop(
        "OILCash", "BUY", 0.65, 103.72, 103.50
    ) == 12.5
