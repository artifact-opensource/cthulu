from types import SimpleNamespace

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
    def __init__(self, positions=None, min_lot=0.01):
        self.positions = positions or []
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

    def get_spread(self, symbol):
        return None

    def get_account_info(self):
        return {"balance": 10000, "equity": 10000}


def make_evaluator(connector, tracker, **overrides):
    limits = RiskLimits(
        max_position_size_percent=2.0,
        max_lot_size=1.0,
        max_total_positions=6,
        max_positions_per_symbol=3,
        max_aggregate_open_risk_percent=50.0,
        max_daily_loss=500.0,
        max_daily_loss_percent=10.0,
        min_balance_threshold=1.0,
        **overrides,
    )
    return RiskEvaluator(connector, tracker, limits)


def test_position_size_uses_stop_risk_and_floors_to_volume_step():
    connector = FakeConnector()
    evaluator = make_evaluator(connector, FakeTracker())

    size = evaluator.calculate_position_size(
        "GOLD", 1000, risk_percent=2.0, entry_price=100, stop_loss=90, side="BUY"
    )

    assert size == 0.1


def test_position_is_rejected_when_broker_minimum_exceeds_risk_budget():
    connector = FakeConnector(min_lot=0.1)
    evaluator = make_evaluator(connector, FakeTracker())

    size = evaluator.calculate_position_size(
        "GOLD", 100, risk_percent=2.0, entry_price=100, stop_loss=90, side="BUY"
    )

    assert size == 0.0


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
