import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd

from core.multi_symbol import (
    MultiSymbolOrchestrator,
    _MultiSymbolStrategyAdapter,
    _resolve_mt5_timeframe,
)
from cthulu.strategy.base import Signal, SignalType


def test_timeframe_resolution_accepts_prefixed_and_short_mt5_names():
    mt5 = SimpleNamespace(TIMEFRAME_M1=1)

    assert _resolve_mt5_timeframe("TIMEFRAME_M1", mt5) == 1
    assert _resolve_mt5_timeframe("M1", mt5) == 1


def test_orchestrator_uses_timeframe_from_shared_config_schema():
    orchestrator = MultiSymbolOrchestrator(
        SimpleNamespace(),
        {"trading": {"timeframe": "TIMEFRAME_M1"}},
    )

    assert orchestrator.timeframe == "TIMEFRAME_M1"


def test_multi_strategy_factory_isolates_symbols_and_builds_current_indicator_columns():
    config = {
        "watchlist": [
            {"symbol": "BTCUSD", "timeframe": "TIMEFRAME_M1"},
            {"symbol": "GOLD", "timeframe": "TIMEFRAME_M5"},
        ],
        "strategy": {
            "type": "dynamic",
            "params": {},
            "dynamic_selection": {},
            "strategies": [
                {"type": "sma_crossover", "params": {"fast_period": 10, "slow_period": 30}},
                {"type": "ema_crossover", "params": {"fast_period": 12, "slow_period": 26}},
                {"type": "momentum_breakout", "params": {"lookback_period": 20}},
                {"type": "scalping", "params": {"rsi_period": 7}},
                {"type": "mean_reversion", "params": {"rsi_period": 14}},
                {"type": "trend_following", "params": {"adx_period": 14}},
                {"type": "rsi_reversal", "params": {"rsi_period": 14}},
            ],
        },
    }
    orchestrator = MultiSymbolOrchestrator(SimpleNamespace(), config)

    btc_selector = orchestrator._strategy_selectors["BTCUSD"].strategy
    gold_selector = orchestrator._strategy_selectors["GOLD"].strategy
    assert btc_selector is not gold_selector
    assert btc_selector.selector is not gold_selector.selector
    assert (
        btc_selector.selector.strategies["sma_crossover"].config["params"]["symbol"]
        == "BTCUSD"
    )
    assert (
        gold_selector.selector.strategies["sma_crossover"].config["params"]["symbol"]
        == "GOLD"
    )

    close = [100.0 + index * 0.1 + (index % 7) * 0.02 for index in range(60)]
    data = pd.DataFrame(
        {
            "open": close,
            "high": [value + 0.5 for value in close],
            "low": [value - 0.5 for value in close],
            "close": close,
            "volume": [1000 + (index % 5) * 10 for index in range(60)],
        },
        index=pd.date_range("2025-01-01", periods=60, freq="min"),
    )
    indicators = asyncio.run(
        orchestrator._calculate_indicators(data, orchestrator._strategy_selectors["BTCUSD"])
    )

    assert {
        "sma_10",
        "sma_30",
        "ema_12",
        "ema_26",
        "rsi",
        "rsi_7",
        "adx",
        "atr",
        "macd",
        "macd_signal",
        "bb_upper_20_2.0",
        "bb_middle_20",
        "bb_lower_20_2.0",
        "high_20",
        "low_20",
        "volume_avg_20",
    }.issubset(data.columns)
    assert indicators["ATR"] == data["atr"].iloc[-1]


def test_multi_strategy_adapter_normalizes_signal_objects():
    class FakeStrategy:
        name = "test_strategy"

        def on_bar(self, bar):
            return Signal(
                id="test-signal",
                timestamp=bar.name,
                symbol="WRONG",
                timeframe="M1",
                side=SignalType.LONG,
                action="BUY",
                price=100.0,
                stop_loss=99.0,
                take_profit=102.0,
                confidence=0.8,
                metadata={},
            )

    adapter = _MultiSymbolStrategyAdapter(FakeStrategy(), "GOLD")
    signal = adapter.generate_signal(
        pd.DataFrame(
            {"close": [100.0]},
            index=pd.DatetimeIndex([datetime.now(timezone.utc)]),
        ),
        indicators={"ATR": 1.0},
        regime="trending_up",
    )

    assert signal["symbol"] == "GOLD"
    assert signal["direction"] == "buy"
    assert signal["strategy"] == "test_strategy"
    assert signal["metadata"]["market_regime"] == "trending_up"
    assert signal["metadata"]["indicators"]["ATR"] == 1.0


def test_analyzed_multi_signal_is_queued_to_discord_signals_webhook(monkeypatch):
    from integrations.discord_notifier import NotificationChannel

    notifications = []

    class FakeNotifier:
        enabled = True
        webhooks = {NotificationChannel.SIGNALS: "configured"}

        def notify_signal_quality(self, **kwargs):
            notifications.append(kwargs)
            return True

    class FakeSelector:
        def generate_signal(self, **_kwargs):
            return {
                "direction": "buy",
                "confidence": 0.8,
                "strategy_score": 0.9,
                "strategy": "test_strategy",
                "price": 100.0,
                "stop_loss": 99.0,
                "take_profit": 102.0,
            }

    monkeypatch.setattr(
        "integrations.discord_notifier.get_discord_notifier",
        lambda: FakeNotifier(),
    )
    orchestrator = MultiSymbolOrchestrator.__new__(MultiSymbolOrchestrator)
    ctx = SimpleNamespace(
        symbol="GOLD",
        timeframe="M1",
        market_data=None,
        indicators={},
        regime="unknown",
        last_regime_update=0.0,
        last_signal_time=0.0,
        cooldown_until=0.0,
        enabled=True,
        consecutive_losses=0,
    )
    orchestrator.symbols = {"GOLD": ctx}
    orchestrator._strategy_selectors = {"GOLD": FakeSelector()}
    orchestrator.components = SimpleNamespace(
        regime_classifier=None,
        entry_confluence=None,
    )
    orchestrator._current_macro_snapshot = None
    orchestrator._session_scheduler = None
    orchestrator.config = {
        "discord": {"enabled": True, "alert_on_signals": True}
    }
    orchestrator.signal_cooldown_seconds = 300
    data = pd.DataFrame(
        {
            "open": [100.0] * 50,
            "high": [101.0] * 50,
            "low": [99.0] * 50,
            "close": [100.0] * 50,
            "volume": [1000] * 50,
        },
        index=pd.date_range("2025-01-01", periods=50, freq="min"),
    )
    orchestrator._fetch_symbol_data = lambda _symbol, _ctx: data

    async def calculate_indicators(_data, _selector):
        return {"ATR": 1.25, "MACD": (1.0, 2.0)}

    orchestrator._calculate_indicators = calculate_indicators
    orchestrator._publish_legacy_context = lambda *_args, **_kwargs: None

    scored = asyncio.run(orchestrator._analyze_symbol("GOLD", ctx))

    assert scored is not None
    assert len(notifications) == 1
    assert notifications[0]["symbol"] == "GOLD"
    assert notifications[0]["direction"] == "BUY"
    assert notifications[0]["strategy"] == "test_strategy"
    assert notifications[0]["indicators"] == {"ATR": 1.25}
    assert notifications[0]["confluence_quality"] is None

    asyncio.run(orchestrator._analyze_symbol("GOLD", ctx))

    assert len(notifications) == 1


def test_multi_signal_webhook_respects_alert_on_signals_setting(monkeypatch):
    def unexpected_notifier():
        raise AssertionError("disabled signal alerts must not initialize Discord")

    monkeypatch.setattr(
        "integrations.discord_notifier.get_discord_notifier",
        unexpected_notifier,
    )
    orchestrator = MultiSymbolOrchestrator.__new__(MultiSymbolOrchestrator)
    orchestrator.config = {
        "discord": {"enabled": True, "alert_on_signals": False}
    }

    orchestrator._notify_signal(
        {},
        SimpleNamespace(symbol="GOLD"),
        {},
    )


class FakeRiskEvaluator:
    def __init__(self, approved_size=0.1, approved=True):
        self.result = {
            "approved": approved,
            "reason": "test risk result",
            "lot_size": approved_size if approved else 0.0,
        }

    def evaluate(self, signal):
        return self.result


class FakeConnector:
    def __init__(self):
        self.account_info = {"balance": 1000.0, "equity": 1250.0, "leverage": 100}
        self.symbol_info = {
            "volume_min": 0.01,
            "volume_max": 10.0,
            "volume_step": 0.01,
        }

    def get_account_info(self):
        return self.account_info

    def get_symbol_info(self, symbol):
        return self.symbol_info


class FakeSizer:
    def __init__(self, lot_size=None, error=None):
        self.lot_size = lot_size
        self.error = error
        self.kwargs = None

    def calculate_lot_size(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.lot_size


class FakeExecutionEngine:
    def __init__(self):
        self.calls = []
        self.result = {
            "success": True,
            "ticket": 7,
            "price": 100.0,
            "volume": 0.1,
        }

    def execute(self, signal, lot_size):
        self.calls.append((signal, lot_size))
        result = self.result.copy()
        result["volume"] = lot_size
        return result


class FakeTradeManager:
    def __init__(self):
        self.failed_orders = []

    def register_trade(self, **kwargs):
        pass

    def record_failed_order(self, symbol):
        self.failed_orders.append(symbol)


def make_orchestrator(
    *,
    approved_size=0.1,
    approved=True,
    sizer=None,
    drawdown_manager=None,
    lot_size_override=0.5,
):
    connector = FakeConnector()
    execution_engine = FakeExecutionEngine()
    orchestrator = MultiSymbolOrchestrator.__new__(MultiSymbolOrchestrator)
    orchestrator.components = SimpleNamespace(
        risk_evaluator=FakeRiskEvaluator(approved_size, approved),
        mt5_connector=connector,
        adaptive_drawdown_manager=drawdown_manager,
        execution_engine=execution_engine,
        trade_manager=FakeTradeManager(),
    )
    orchestrator._sizer = sizer
    orchestrator._current_macro_snapshot = None
    orchestrator.symbols = {
        "GOLD": SimpleNamespace(
            indicators={"ATR": 1.0},
            lot_size_override=lot_size_override,
        )
    }

    async def apply_sltp(ticket, signal, symbol):
        pass

    orchestrator._apply_sltp = apply_sltp
    scored = SimpleNamespace(
        signal={
            "direction": "buy",
            "confidence": 0.8,
            "session_multiplier": 1.0,
        },
        symbol="GOLD",
        score=0.9,
        strategy="test",
        regime="trend",
    )
    return orchestrator, scored, execution_engine


def test_sizer_uses_equity_and_cannot_exceed_risk_approved_size():
    sizer = FakeSizer(lot_size=0.2)
    orchestrator, scored, execution_engine = make_orchestrator(sizer=sizer)

    executed = asyncio.run(orchestrator._execute_signal(scored))

    assert executed
    assert sizer.kwargs["account_balance"] == 1250.0
    assert execution_engine.calls[0][1] == 0.1


def test_failed_order_starts_symbol_cooldown():
    orchestrator, scored, execution_engine = make_orchestrator()
    execution_engine.result = {"success": False, "error": "broker rejected order"}

    executed = asyncio.run(orchestrator._execute_signal(scored))

    assert not executed
    assert orchestrator.components.trade_manager.failed_orders == ["GOLD"]


def test_candidate_below_broker_minimum_is_not_executed():
    orchestrator, scored, execution_engine = make_orchestrator(
        sizer=FakeSizer(lot_size=0.005)
    )

    executed = asyncio.run(orchestrator._execute_signal(scored))

    assert not executed
    assert execution_engine.calls == []


def test_sizer_candidate_is_floored_to_broker_volume_step():
    orchestrator, scored, execution_engine = make_orchestrator(
        approved_size=0.2,
        sizer=FakeSizer(lot_size=0.19),
    )
    orchestrator.components.mt5_connector.symbol_info.update(
        {"volume_min": 0.05, "volume_step": 0.05}
    )

    executed = asyncio.run(orchestrator._execute_signal(scored))

    assert executed
    assert execution_engine.calls[0][1] == 0.15


def test_sizer_failure_does_not_allow_symbol_override_to_exceed_risk_approval():
    orchestrator, scored, execution_engine = make_orchestrator(
        sizer=FakeSizer(error=RuntimeError("sizer unavailable")),
        lot_size_override=0.5,
    )
    scored.signal["session_multiplier"] = 0.5

    executed = asyncio.run(orchestrator._execute_signal(scored))

    assert executed
    assert execution_engine.calls[0][1] == 0.05


def test_zero_session_multiplier_skips_trade():
    orchestrator, scored, execution_engine = make_orchestrator(
        sizer=FakeSizer(lot_size=0.1)
    )
    scored.signal["session_multiplier"] = 0.0

    executed = asyncio.run(orchestrator._execute_signal(scored))

    assert not executed
    assert execution_engine.calls == []


def test_drawdown_multiplier_uses_balance_and_equity_and_only_reduces_size():
    class FakeDrawdownManager:
        def __init__(self):
            self.account = None

        def update(self, balance, equity):
            self.account = (balance, equity)
            return SimpleNamespace(
                allow_new_trades=True,
                position_size_multiplier=0.5,
            )

    manager = FakeDrawdownManager()
    orchestrator, scored, execution_engine = make_orchestrator(
        drawdown_manager=manager
    )

    executed = asyncio.run(orchestrator._execute_signal(scored))

    assert executed
    assert manager.account == (1000.0, 1250.0)
    assert execution_engine.calls[0][1] == 0.05


def test_drawdown_manager_can_block_new_trades():
    manager = SimpleNamespace(
        update=lambda balance, equity: SimpleNamespace(
            allow_new_trades=False,
            position_size_multiplier=1.0,
        )
    )
    orchestrator, scored, execution_engine = make_orchestrator(
        drawdown_manager=manager
    )

    executed = asyncio.run(orchestrator._execute_signal(scored))

    assert not executed
    assert execution_engine.calls == []


def test_daily_loss_check_fails_closed_when_account_information_is_missing():
    orchestrator = MultiSymbolOrchestrator.__new__(MultiSymbolOrchestrator)
    connector = FakeConnector()
    connector.account_info = None
    orchestrator.components = SimpleNamespace(mt5_connector=connector)
    orchestrator.max_daily_loss_pct = 5.0
    orchestrator._daily_date = datetime.now(timezone.utc).date()
    orchestrator._daily_start_equity = 1000.0
    orchestrator._daily_loss_halt = False
    orchestrator._daily_tracking_initialized = True
    orchestrator._last_daily_limit_failure = None
    orchestrator._execution_halt_reason = None

    allowed = asyncio.run(orchestrator._check_daily_limits())

    assert not allowed
    assert not orchestrator._daily_loss_halt


def test_daily_limit_check_recovers_after_temporary_account_data_outage():
    orchestrator = MultiSymbolOrchestrator.__new__(MultiSymbolOrchestrator)
    connector = FakeConnector()
    connector.account_info = None
    orchestrator.components = SimpleNamespace(mt5_connector=connector)
    orchestrator.max_daily_loss_pct = 5.0
    orchestrator._daily_date = datetime.now(timezone.utc).date()
    orchestrator._daily_start_equity = 1000.0
    orchestrator._daily_loss_halt = False
    orchestrator._daily_tracking_initialized = True
    orchestrator._last_daily_limit_failure = None

    assert not asyncio.run(orchestrator._check_daily_limits())
    assert not orchestrator._daily_loss_halt

    connector.account_info = {"balance": 970.0, "equity": 970.0}
    assert asyncio.run(orchestrator._check_daily_limits())
    assert orchestrator._daily_start_equity == 1000.0
    assert not orchestrator._daily_loss_halt


def test_daily_tracking_initialization_retries_after_account_data_recovers():
    orchestrator = MultiSymbolOrchestrator.__new__(MultiSymbolOrchestrator)
    connector = FakeConnector()
    connector.account_info = None
    orchestrator.components = SimpleNamespace(mt5_connector=connector)
    orchestrator.max_daily_loss_pct = 5.0
    orchestrator._daily_date = None
    orchestrator._daily_start_equity = 0.0
    orchestrator._daily_loss_halt = False
    orchestrator._daily_tracking_initialized = False
    orchestrator._last_daily_limit_failure = None

    assert not asyncio.run(orchestrator._init_daily_tracking())
    assert not orchestrator._daily_loss_halt
    assert not orchestrator._daily_tracking_initialized

    connector.account_info = {"balance": 1000.0, "equity": 1000.0}
    assert asyncio.run(orchestrator._check_daily_limits())
    assert orchestrator._daily_tracking_initialized
    assert orchestrator._daily_start_equity == 1000.0
