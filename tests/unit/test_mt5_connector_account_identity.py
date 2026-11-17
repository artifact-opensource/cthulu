import logging
from types import SimpleNamespace
from unittest.mock import Mock

from cthulu.connector import mt5_connector as connector_module
from cthulu.connector.mt5_connector import ConnectionConfig, MT5Connector


def _account(login, server="Demo Server"):
    return SimpleNamespace(
        login=login,
        server=server,
        balance=1000.0,
        trade_allowed=True,
    )


def test_connector_uses_configured_path_and_blocks_account_switch(monkeypatch):
    terminal_path = r"C:\MT5 Demo\terminal64.exe"
    mt5 = SimpleNamespace(
        __version__="test",
        version=None,
        terminal_info=Mock(side_effect=[None, SimpleNamespace(connected=True)]),
        initialize=Mock(return_value=True),
        account_info=Mock(side_effect=[_account(12345), _account(67890)]),
        shutdown=Mock(),
        last_error=Mock(return_value=(0, "ok")),
    )
    monkeypatch.setattr(connector_module, "mt5", mt5)
    monkeypatch.setenv("MT5_LOGIN", "")
    monkeypatch.setenv("MT5_PASSWORD", "")
    monkeypatch.setenv("MT5_SERVER", "")
    connector = MT5Connector(ConnectionConfig(
        login=12345,
        password="test-password",
        server="Demo Server",
        path=terminal_path,
        max_retries=1,
        retry_delay=0,
    ))

    assert connector.connect()
    assert mt5.initialize.call_args.kwargs["path"] == terminal_path
    assert not connector.is_connected()


def test_connector_rejects_wrong_server_at_connect(monkeypatch):
    mt5 = SimpleNamespace(
        __version__="test",
        version=None,
        terminal_info=Mock(return_value=None),
        initialize=Mock(return_value=True),
        account_info=Mock(side_effect=[
            _account(12345, "Other Server"),
            _account(12345, "Demo Server"),
        ]),
        shutdown=Mock(),
        last_error=Mock(return_value=(0, "ok")),
    )
    monkeypatch.setattr(connector_module, "mt5", mt5)
    monkeypatch.setenv("MT5_LOGIN", "")
    monkeypatch.setenv("MT5_PASSWORD", "")
    monkeypatch.setenv("MT5_SERVER", "")
    connector = MT5Connector(ConnectionConfig(
        login=12345,
        password="test-password",
        server="Demo Server",
        max_retries=2,
        retry_delay=0,
    ))

    assert connector.connect()
    assert mt5.account_info.call_count == 2


def test_connector_reports_terminal_disconnected(monkeypatch, caplog):
    mt5 = SimpleNamespace(
        __version__="test",
        version=None,
        terminal_info=Mock(side_effect=[None, SimpleNamespace(connected=False)]),
        initialize=Mock(return_value=True),
        account_info=Mock(return_value=_account(12345)),
        shutdown=Mock(),
        last_error=Mock(return_value=(0, "ok")),
    )
    monkeypatch.setattr(connector_module, "mt5", mt5)
    monkeypatch.setenv("MT5_LOGIN", "")
    monkeypatch.setenv("MT5_PASSWORD", "")
    monkeypatch.setenv("MT5_SERVER", "")
    connector = MT5Connector(ConnectionConfig(
        login=12345,
        password="test-password",
        server="Demo Server",
        max_retries=1,
        retry_delay=0,
    ))

    assert connector.connect()
    with caplog.at_level(logging.WARNING, logger="cthulu.connector"):
        assert not connector.is_connected()

    assert "terminal reports disconnected" in caplog.text


def test_connector_reconnect_respects_cooldown(monkeypatch):
    connector = MT5Connector(ConnectionConfig(
        login=12345,
        password="test-password",
        server="Demo Server",
    ))
    now = [100.0]
    monkeypatch.setattr(connector_module.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(connector_module.time, "sleep", lambda _: None)
    connector.disconnect = Mock()
    connector.connect = Mock(return_value=False)

    assert not connector.reconnect()
    assert not connector.reconnect()
    assert connector.connect.call_count == 1

    now[0] += connector.RECONNECT_COOLDOWN_SECONDS
    assert not connector.reconnect()
    assert connector.connect.call_count == 2


def test_connector_does_not_reconnect_a_responsive_wrong_account():
    connector = MT5Connector(ConnectionConfig(
        login=12345,
        password="test-password",
        server="Demo Server",
    ))
    connector.connected = True
    connector.disconnect = Mock()
    connector.connect = Mock()

    assert not connector.reconnect()
    connector.disconnect.assert_not_called()
    connector.connect.assert_not_called()


def test_connector_recovers_terminal_health_failure():
    connector = MT5Connector(ConnectionConfig(
        login=12345,
        password="test-password",
        server="Demo Server",
    ))
    connector.connected = True
    connector._last_terminal_health_failure = "terminal reports disconnected"
    connector.is_connected = Mock(return_value=False)
    connector.reconnect = Mock(return_value=True)

    assert connector._ensure_connected()
    connector.reconnect.assert_called_once()
