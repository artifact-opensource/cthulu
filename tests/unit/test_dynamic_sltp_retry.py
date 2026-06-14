from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest

from cthulu.core.trading_loop import TradingLoop, TradingLoopContext
from cthulu.position.manager import PositionInfo


class DummyConnector:
    def get_position_by_ticket(self, ticket):
        return {'ticket': ticket, 'symbol': 'EURUSD', 'volume': 1.0, 'price_open': 1.1, 'price_current': 1.2}


def make_context():
    ctx = SimpleNamespace()
    ctx.connector = DummyConnector()
    ctx.position_tracker = MagicMock()
    ctx.position_lifecycle = MagicMock()
    ctx.dynamic_sltp_manager = MagicMock()
    ctx.metrics = MagicMock()
    ctx.logger = MagicMock()
    # minimal required config pieces
    ctx.config = {}
    ctx.args = SimpleNamespace(max_loops=0)
    ctx.symbol = 'EURUSD'
    ctx.timeframe = None
    ctx.poll_interval = 1
    ctx.lookback_bars = 10
    ctx.dry_run = True
    ctx.indicators = []
    ctx.exit_strategies = []
    ctx.trade_adoption_policy = None
    ctx.database = MagicMock()
    return ctx


def test_dynamic_sltp_retry_invokes_modify_twice(monkeypatch):
    ctx = make_context()
    # Create a TradingLoop instance with our context
    loop = TradingLoop(TradingLoopContext(
        connector=ctx.connector,
        data_layer=None,
        execution_engine=None,
        risk_manager=None,
        position_tracker=ctx.position_tracker,
        position_lifecycle=ctx.position_lifecycle,
        trade_adoption_manager=None,
        exit_coordinator=None,
        database=ctx.database,
        metrics=ctx.metrics,
        logger=ctx.logger,
        symbol='EURUSD',
        timeframe=None,
        poll_interval=1,
        lookback_bars=5,
        dry_run=True,
        indicators=[],
        exit_strategies=[],
        trade_adoption_policy=None,
        config={},
        dynamic_sltp_manager=ctx.dynamic_sltp_manager
    ))

    # Prepare a position-like object
    position = PositionInfo(ticket=12345, symbol='EURUSD', volume=1.0, open_price=1.100)
    position.current_price = 1.2
    position.side = 'BUY'
    position.stop_loss = None
    position.take_profit = None

    # Ensure manager internal state exists and will request an SL update
    loop.ctx.dynamic_sltp_manager.positions_managed = {}
    loop.ctx.dynamic_sltp_manager.update_position_sltp.return_value = {
        'update_sl': True,
        'update_tp': False,
        'new_sl': 1.05,
        'new_tp': None,
        'action': 'trail_stop'
    }

    # position_lifecycle.modify_position fails first, then succeeds
    ctx.position_lifecycle.modify_position.side_effect = [False, True]

    # Call internal method
    loop._apply_dynamic_sltp(position, atr_value=0.1, account_info={'balance': 1000, 'equity': 1000}, df=None)

    # Ensure manager was consulted
    assert loop.ctx.dynamic_sltp_manager.update_position_sltp.call_count >= 1, "dynamic_sltp_manager not called"

    # modify_position should have been called at least twice (initial attempt + retry)
    assert ctx.position_lifecycle.modify_position.call_count >= 2, f"modify_position call_count={ctx.position_lifecycle.modify_position.call_count}"
