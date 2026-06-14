import pytest
from position.profit_scaler import ProfitScaler, ScalingConfig, ScalingTier


class DummyConnector:
    pass


class DummyEngine:
    def close_position(self, ticket, volume=None):
        class R:
            status = type('s', (), {'value': 'FILLED'})
            fill_price = 100.0
            order = 123
            volume = volume
            profit = 10.0
            metadata = {'profit': 10.0}
        return R()


def test_full_close_on_min_lot():
    cfg = ScalingConfig()
    cfg.allow_full_close_on_min_lot = True
    ps = ProfitScaler(connector=DummyConnector(), execution_engine=DummyEngine(), config=cfg, use_ml_optimizer=False)

    # Register a min-lot position
    ticket = 999
    ps.register_position(ticket, 'GOLDM#', 0.01, 100.0, sl=90.0, tp=110.0)
    # Force a tier that would trigger here (high profit pct)
    actions = ps.evaluate_position(ticket, current_price=110.0, side='BUY', balance=1000.0, bars_elapsed=10)

    # Find a close action scheduled due to min lot
    found_close = any(a['type'] == 'close_partial' and a['volume'] >= 0.01 for a in actions)
    assert found_close, "Expected a full close action to be scheduled for min-lot position"