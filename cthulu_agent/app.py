"""Wires the pieces together. One App per process."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from . import envfile
from .broker import Broker, BrokerError, make_broker
from .events import EventBus
from .journal import Journal
from .llm import LLMManager
from .risk import RiskEngine
from .agent import AgentRuntime
from .settings import Settings
from .world import WorldIntel


def _load_selected_environment(selected_env: Optional[Path]) -> None:
    envfile.load_env(selected_env)
    if not selected_env:
        return

    root_env = Path(__file__).resolve().parent.parent / ".env"
    root_values = envfile.read_env(root_env)
    for key in ("CLOUDFLARE_API_KEY", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_AI_GATEWAY_ID"):
        if key in root_values:
            os.environ.setdefault(key, root_values[key])
    for key in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_PATH"):
        if root_values.get(key):
            os.environ[key] = root_values[key]


class App:
    def __init__(self, db_path: Optional[str] = None, env_path: Optional[str] = None):
        selected_env = Path(env_path) if env_path else None
        _load_selected_environment(selected_env)
        self.bus = EventBus()
        self.settings = Settings()
        root = Path(__file__).resolve().parent.parent
        self.journal = Journal(db_path or os.environ.get("AGENT_DB_PATH") or (root / "data" / "agent.db"))
        self.llm = LLMManager(on_event=self.bus.emit)
        self.risk = RiskEngine(self.settings, self.journal)
        self.world = WorldIntel(self.journal)
        self.runtime: Optional[AgentRuntime] = None
        self.broker_error = ""

    def start_runtime(self, broker: Optional[Broker] = None, autostart: bool = True) -> bool:
        if self.runtime:
            self.runtime.stop()
            try:
                self.runtime.broker.shutdown()
            except Exception:
                pass
            self.runtime = None
        try:
            b = broker or make_broker(self.settings.broker, self.settings.float("PAPER_BALANCE"))
            b.connect()
        except BrokerError as e:
            self.broker_error = str(e)
            self.bus.emit("alert", level="error", message=f"Broker connection failed: {e}")
            return False
        if self.settings.raw("AGENT_SYMBOLS").strip() == "*":
            try:
                symbols = b.tradeable_symbols(self.settings.float("AGENT_SYMBOL_MAX_SPREAD_PCT"))
                if not symbols:
                    raise BrokerError("No tradable symbols passed the spread, quote-freshness, and M1-history filters")
                self.settings.set_dynamic_symbols(symbols)
            except BrokerError as e:
                b.shutdown()
                self.broker_error = str(e)
                self.bus.emit("alert", level="error", message=f"Broker universe discovery failed: {e}")
                return False
        self.broker_error = ""
        if b.name == "paper":  # a fresh simulated account must not inherit an old equity peak
            bal = b.account().equity
            self.journal.kv_set("equity_peak", bal)
            self.journal.kv_set("equity_start", bal)
        self.runtime = AgentRuntime(self.settings, b, self.journal, self.llm, self.risk, self.world, self.bus)
        if autostart:
            self.runtime.start()
        return True
