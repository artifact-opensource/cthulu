from types import SimpleNamespace

from cthulu.persistence.database import Database
from cthulu.risk.evaluator import RiskEvaluator, RiskLimits
from cthulu.strategy.base import SignalType


class FakeTracker:
    def __init__(self, positions=None):
        self.positions = positions or []

    def get_all_positions(self):
        return {index: position for index, position in enumerate(self.positions)}

    def get_positions_by_symbol(self, symbol):
        return [position for position in self.positions if position.symbol == symbol]

    def get_position_count(self):
        return len(self.positions)

    def calculate_total_exposure(self):
        return sum(position.volume for position in self.positions)

    def get_exposure_by_symbol(self):
        return {}


class FakeConnector:
    def __init__(self, positions=None, pending=None, min_lot=0.01):
        self.positions = positions or []
        self.pending = pending or []
        self.min_lot = min_lot

    def calculate_loss_at_stop(self, symbol, side, volume, entry, stop):
        distance = entry - stop if side == "BUY" else stop - entry
        if distance <= 0:
            return None
        return distance * volume * 20

    def get_symbol_info(self, symbol):
        return {
            "volume_min": self.min_lot,
            "volume_max": 10.0,
            "volume_step": self.min_lot,
        }

    def get_open_positions(self):
        return self.positions

    def get_pending_orders(self):
        return self.pending

    def get_spread(self, symbol):
        return None

    def get_point_value(self, symbol):
        return 20.0

    def get_account_info(self):
        return {"balance": 10000, "equity": 10000}


def make_evaluator(connector, tracker, state_store=None, **overrides):
    limit_values = {
        "max_position_size_percent": 2.0,
        "max_lot_size": 1.0,
        "max_total_positions": 6,
        "max_positions_per_symbol": 3,
        "max_aggregate_open_risk_percent": 50.0,
        "max_daily_loss": 500.0,
        "max_daily_loss_percent": 10.0,
        "min_balance_threshold": 1.0,
    }
    limit_values.update(overrides)
    limits = RiskLimits(**limit_values)
    return RiskEvaluator(connector, tracker, limits, state_store=state_store)


def test_position_size_uses_stop_risk_and_floors_to_volume_step():
    connector = FakeConnector()
    evaluator = make_evaluator(connector, FakeTracker())

    size = evaluator.calculate_position_size(
        "GOLD", 1000, risk_percent=2.0, entry_price=100, stop_loss=90, side="BUY"
    )

    assert size == 0.1


def test_position_size_respects_high_frequency_small_lot_cap():
    connector = FakeConnector()
    evaluator = make_evaluator(connector, FakeTracker(), max_lot_size=0.02)

    size = evaluator.calculate_position_size(
        "GOLD", 10000, risk_percent=15.0, entry_price=100, stop_loss=90, side="BUY"
    )

    assert size == 0.02


def test_approval_compounds_position_size_from_equity_not_balance():
    connector = FakeConnector()
    evaluator = make_evaluator(connector, FakeTracker())
    evaluator.approve_trade = lambda **kwargs: (True, "approved")

    approved, reason, size = evaluator.approve(
        SimpleNamespace(
            symbol="GOLD",
            price=100,
            stop_loss=90,
            take_profit=120,
            side=SignalType.LONG,
            confidence=0.9,
        ),
        {"balance": 5000, "equity": 1000},
        current_positions=0,
    )

    assert approved
    assert reason == "approved"
    assert size == 0.1


def test_position_is_rejected_when_broker_minimum_exceeds_risk_budget():
    connector = FakeConnector(min_lot=0.1)
    evaluator = make_evaluator(connector, FakeTracker())

    size = evaluator.calculate_position_size(
        "GOLD", 100, risk_percent=2.0, entry_price=100, stop_loss=90, side="BUY"
    )

    assert size == 0.0


def test_volatility_sizing_rejects_minimum_lot_above_equity_risk_budget():
    connector = FakeConnector(min_lot=0.1)
    evaluator = make_evaluator(connector, FakeTracker())

    size = evaluator.calculate_position_size(
        "GOLD", 100, method="volatility", risk_percent=1.0, atr=1.0
    )

    assert size == 0.0


def test_volatility_sizing_floors_to_broker_volume_step():
    connector = FakeConnector(min_lot=0.05)
    connector.get_symbol_info = lambda symbol: {
        "volume_min": 0.05,
        "volume_max": 10.0,
        "volume_step": 0.05,
    }
    evaluator = make_evaluator(connector, FakeTracker())

    size = evaluator.calculate_position_size(
        "GOLD", 100, method="volatility", risk_percent=1.5, atr=1.0
    )

    assert size == 0.05


def test_aggregate_open_risk_blocks_exposure_over_limit():
    open_position = {
        "ticket": 7,
        "symbol": "GOLD",
        "volume": 24.5,
        "price_open": 100,
        "type": 0,
        "sl": 90,
    }
    connector = FakeConnector(positions=[open_position])
    evaluator = make_evaluator(connector, FakeTracker())

    approved, reason, size = evaluator.approve(
        SimpleNamespace(
            symbol="GOLD",
            price=100,
            stop_loss=90,
            take_profit=120,
            side=SignalType.LONG,
            confidence=0.9,
        ),
        {"balance": 10000, "equity": 10000},
        current_positions=1,
    )

    assert not approved
    assert "Aggregate stop risk" in reason
    assert size == 0.0


def test_aggregate_open_risk_fails_closed_when_position_query_is_unavailable():
    connector = FakeConnector()
    connector.get_open_positions = lambda: None
    evaluator = make_evaluator(connector, FakeTracker())

    approved, reason, size = evaluator.approve(
        SimpleNamespace(
            symbol="GOLD",
            price=100,
            stop_loss=90,
            take_profit=120,
            side=SignalType.LONG,
            confidence=0.9,
        ),
        {"balance": 10000, "equity": 10000},
        current_positions=0,
    )

    assert not approved
    assert "open positions are unavailable" in reason
    assert size == 0.0


def test_exposure_limit_counts_pending_orders_toward_total_active_cap():
    connector = FakeConnector(
        positions=[{"symbol": "EURUSD"}],
        pending=[{"symbol": "BTCUSD"}],
    )
    evaluator = make_evaluator(
        connector,
        FakeTracker(),
        max_total_positions=2,
        max_positions_per_symbol=3,
    )

    allowed, reason = evaluator.check_exposure_limits("GOLD", 0.01)

    assert not allowed
    assert "total active orders" in reason


def test_aggregate_open_risk_includes_pending_order_stop_risk():
    connector = FakeConnector(
        pending=[{
            "ticket": 11,
            "symbol": "GOLD",
            "volume": 24.5,
            "price_open": 100,
            "type": 2,
            "sl": 90,
        }]
    )
    evaluator = make_evaluator(
        connector,
        FakeTracker(),
        max_aggregate_open_risk_percent=1.0,
    )

    allowed, reason = evaluator.check_aggregate_open_risk(
        "BTCUSD", "BUY", 0.01, 100, 90, 10000
    )

    assert not allowed
    assert "Aggregate stop risk" in reason


def test_risk_reward_rejects_stop_on_wrong_side_for_direction():
    evaluator = make_evaluator(FakeConnector(), FakeTracker())

    valid, reason = evaluator.validate_risk_reward(
        entry=100, sl=110, tp=120, side="BUY"
    )

    assert not valid
    assert "correct side" in reason


def test_spread_percentage_uses_price_units_not_mt5_points():
    connector = FakeConnector()
    connector.get_spread = lambda symbol: 600
    connector.get_symbol_info = lambda symbol: {
        "point": 0.01,
        "volume_min": 0.01,
        "bid": 9997.0,
        "ask": 10003.0,
    }
    evaluator = make_evaluator(connector, FakeTracker(), max_spread_pct=0.001)

    acceptable, reason = evaluator.check_spread("BTCUSD")

    assert acceptable
    assert "acceptable" in reason


def test_spread_percentage_rejects_genuinely_wide_price_spread():
    connector = FakeConnector()
    connector.get_spread = lambda symbol: 1200
    connector.get_symbol_info = lambda symbol: {
        "point": 0.01,
        "volume_min": 0.01,
        "bid": 94.0,
        "ask": 106.0,
    }
    evaluator = make_evaluator(connector, FakeTracker(), max_spread_pct=0.05)

    acceptable, reason = evaluator.check_spread("BTCUSD")

    assert not acceptable
    assert "Price spread" in reason


def test_minimum_balance_floor_activates_at_threshold_and_persists_per_account(tmp_path):
    database_path = tmp_path / "risk-state.db"
    database = Database(str(database_path))
    connector = FakeConnector()
    account = {
        "login": 12345,
        "server": "test-server",
        "balance": 0.20,
        "equity": 0.20,
        "margin_free": 0.20,
    }

    try:
        evaluator = make_evaluator(
            connector,
            FakeTracker(),
            state_store=database,
            min_balance_threshold=10.0,
        )
        assert evaluator.check_balance_protection(account)[0]

        reached_threshold = {**account, "balance": 10.0, "equity": 10.0, "margin_free": 10.0}
        assert evaluator.check_balance_protection(reached_threshold)[0]
    finally:
        database.close()

    reopened_database = Database(str(database_path))
    try:
        evaluator = make_evaluator(
            connector,
            FakeTracker(),
            state_store=reopened_database,
            min_balance_threshold=10.0,
        )
        below_threshold = {**account, "balance": 9.99, "equity": 9.99, "margin_free": 9.99}
        safe, reason = evaluator.check_balance_protection(below_threshold)
        assert not safe
        assert "below minimum" in reason

        other_account = {**below_threshold, "login": 67890}
        assert evaluator.check_balance_protection(other_account)[0]
    finally:
        reopened_database.close()


def test_zero_free_margin_is_not_replaced_with_account_equity():
    evaluator = make_evaluator(
        FakeConnector(),
        FakeTracker(),
        min_balance_threshold=10.0,
    )

    safe, reason = evaluator.check_balance_protection({
        "balance": 0.20,
        "equity": 0.20,
        "margin_free": 0.0,
    })

    assert not safe
    assert "Insufficient free margin" in reason


def test_small_account_is_not_forced_to_broker_minimum_volume():
    evaluator = make_evaluator(
        FakeConnector(min_lot=0.01),
        FakeTracker(),
        min_balance_threshold=10.0,
    )
    signal = SimpleNamespace(
        symbol="GOLD",
        price=100,
        stop_loss=90,
        take_profit=120,
        side=SignalType.LONG,
        confidence=0.9,
    )

    approved, reason, size = evaluator.approve(
        signal,
        {
            "login": 12345,
            "server": "test-server",
            "balance": 0.20,
            "equity": 0.20,
            "margin_free": 0.20,
        },
        current_positions=0,
    )

    assert not approved
    assert "broker minimum volume" in reason
    assert size == 0.0
