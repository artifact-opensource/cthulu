from types import SimpleNamespace
from unittest.mock import MagicMock

from cthulu.core.trading_loop import TradingLoop, TradingLoopContext
from cthulu.position.manager import PositionInfo


def make_context():
    ctx = SimpleNamespace()
    ctx.connector = MagicMock()
    ctx.position_tracker = MagicMock()
    ctx.position_lifecycle = MagicMock()
    ctx.dynamic_sltp_manager = MagicMock()
    ctx.metrics = MagicMock()
    ctx.logger = MagicMock()
    ctx.config = {'dynamic_sltp': {}}
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


def test_sanity_guard_skips_too_close_sl():
    ctx = make_context()
    ctx.dynamic_sltp_manager = MagicMock()
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
        config={'dynamic_sltp': {'min_sl_distance_pct': 0.002}},
        dynamic_sltp_manager=ctx.dynamic_sltp_manager
    ))

    pos = PositionInfo(ticket=123, symbol='EURUSD', volume=1.0, open_price=100.0)
    pos.current_price = 100.0
    pos.side = 'BUY'
    pos.sl = None
    pos.tp = None

    # dynamic manager suggests SL very close to price (within 0.05)
    loop.ctx.dynamic_sltp_manager.update_position_sltp.return_value = {
        'update_sl': True,
        'new_sl': 100.05,
        'update_tp': False,
        'action': 'breakeven',
        'reasoning': 'would move to breakeven'
    }

    ctx.position_lifecycle.modify_position.side_effect = AssertionError("modify should not be called")

    # Run apply (should not call modify_position because it's too close)
    loop._apply_dynamic_sltp(pos, atr_value=0.1, account_info={'balance': 1000, 'equity': 1000}, df=None)

    assert ctx.position_lifecycle.modify_position.call_count == 0
