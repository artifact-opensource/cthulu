import os
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from cthulu_agent import app as app_module  # noqa: E402
from cthulu_agent.broker import BrokerError, MT5Broker  # noqa: E402


def _account(login, server="Demo Server"):
    return SimpleNamespace(
        login=login,
        server=server,
        trade_mode=0,
        balance=1000.0,
        equity=1000.0,
        margin_free=900.0,
        currency="USD",
        leverage=100,
    )


def _mt5_module(accounts):
    module = ModuleType("MetaTrader5")
    module.initialize = Mock(return_value=True)
    module.account_info = Mock(side_effect=accounts)
    module.last_error = Mock(return_value=(0, "ok"))
    module.shutdown = Mock()
    module.order_send = Mock()
    module.ACCOUNT_TRADE_MODE_DEMO = 0
    return module


class AgentMT5AccountTests(unittest.TestCase):
    def test_selected_agent_env_cannot_override_root_mt5_account(self):
        selected_env = Path("agent.env")
        agent_values = {
            "MT5_LOGIN": "67890",
            "MT5_PASSWORD": "agent-password",
            "MT5_SERVER": "Agent Server",
            "MT5_PATH": "",
        }
        root_values = {
            "MT5_LOGIN": "12345",
            "MT5_PASSWORD": "root-password",
            "MT5_SERVER": "Demo Server",
            "MT5_PATH": r"C:\MT5 Demo\terminal64.exe",
        }

        def read_env(path):
            return agent_values if Path(path) == selected_env else root_values

        def load_env(path):
            os.environ.update(agent_values)

        with patch.dict(os.environ, {}, clear=False):
            for key in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_PATH"):
                os.environ.pop(key, None)
            with patch.object(app_module.envfile, "read_env", side_effect=read_env), \
                    patch.object(app_module.envfile, "load_env", side_effect=load_env):
                app_module._load_selected_environment(selected_env)

            self.assertEqual(os.environ["MT5_LOGIN"], root_values["MT5_LOGIN"])
            self.assertEqual(os.environ["MT5_PASSWORD"], root_values["MT5_PASSWORD"])
            self.assertEqual(os.environ["MT5_SERVER"], root_values["MT5_SERVER"])
            self.assertEqual(os.environ["MT5_PATH"], root_values["MT5_PATH"])

    def test_order_send_fails_closed_after_live_account_changes(self):
        expected = _account(12345)
        switched = _account(67890)
        mt5 = _mt5_module([expected, switched])
        mt5.ACCOUNT_TRADE_MODE_DEMO = 0
        terminal_path = r"C:\MT5 Demo\terminal64.exe"

        with patch.dict(os.environ, {
            "MT5_LOGIN": "12345",
            "MT5_PASSWORD": "test-password",
            "MT5_SERVER": "Demo Server",
            "MT5_PATH": terminal_path,
        }), patch.dict(sys.modules, {"MetaTrader5": mt5}):
            broker = MT5Broker()
            broker.connect()

            self.assertEqual(mt5.initialize.call_args.kwargs["path"], terminal_path)
            with self.assertRaisesRegex(BrokerError, "differs from the configured account"):
                broker._send({"action": 1})

        mt5.order_send.assert_not_called()

    def test_connect_rejects_unexpected_login(self):
        mt5 = _mt5_module([_account(67890)])

        with patch.dict(os.environ, {
            "MT5_LOGIN": "12345",
            "MT5_PASSWORD": "test-password",
            "MT5_SERVER": "Demo Server",
            "MT5_PATH": "",
        }), patch.dict(sys.modules, {"MetaTrader5": mt5}):
            with self.assertRaisesRegex(BrokerError, "differs from the configured account"):
                MT5Broker().connect()

        mt5.order_send.assert_not_called()

    def test_symbol_info_unavailable_raises_broker_error(self):
        mt5 = _mt5_module([_account(12345)])
        mt5.symbol_info = Mock(return_value=None)
        mt5.symbol_info_tick = Mock(return_value=None)
        mt5.symbols_get = Mock(return_value=[SimpleNamespace(name="EURUSD")])
        mt5.symbol_select = Mock(return_value=True)

        with patch.dict(os.environ, {
            "MT5_LOGIN": "12345",
            "MT5_PASSWORD": "test-password",
            "MT5_SERVER": "Demo Server",
            "MT5_PATH": "",
        }), patch.dict(sys.modules, {"MetaTrader5": mt5}):
            broker = MT5Broker()
            broker.connect()

            with self.assertRaisesRegex(BrokerError, "MT5 symbol info unavailable"):
                broker.symbol_info("EURUSD")
