import time
from types import SimpleNamespace
from cthulu.core.trading_loop import TradingLoop, TradingLoopContext


def test_trading_loop_skips_sltp_when_broker_min_distance(monkeypatch, caplog):
    # Setup fake context and position
    ctx = SimpleNamespace()
    ctx.config = {'dynamic_sltp': {'min_sl_distance_pct': 0.0001}}
    ctx.logger = __import__('logging').getLogger('test_trading_loop')
    ctx.metrics = SimpleNamespace()
    ctx.metrics.increment = lambda name: None

    # Fake connector and symbol info: point=0.01, stops_level=50 -> min_dist=0.5
    connector = SimpleNamespace()
    connector.get_symbol_info = lambda s: {'point': 0.01, 'trade_stops_level': 50}

    # Fake dynamic manager proposing an SL update too close to current price
    dynamic_mgr = SimpleNamespace()
    dynamic_mgr.positions_managed = {}
    def update_position_sltp(**kwargs):
        return {'update_sl': True, 'update_tp': False, 'new_sl': kwargs['current_price'] - 0.2, 'new_tp': None, 'action': 'breakeven', 'reasoning': 'test'}
    dynamic_mgr.update_position_sltp = update_position_sltp

    # Prepare trading loop
    ctx.connector = connector
    ctx.dynamic_sltp_manager = dynamic_mgr
    ctx.position_lifecycle = SimpleNamespace()
    ctx.position_lifecycle.modify_position = lambda ticket, sl=None, tp=None: (_ for _ in ()).throw(Exception('modify should not be called'))

    # Use a lightweight context object compatible with TradingLoop
    tl = TradingLoop(ctx)

    # Fake position object
    position = SimpleNamespace()
    position.ticket = 999
    position.open_price = 100.0
    position.current_price = 101.0
    position.symbol = 'GOLDm#'
    position.sl = None
    position.tp = None
    position.type = 'BUY'

    # Run _apply_dynamic_sltp which should skip and not call modify_position
    tl._apply_dynamic_sltp(position, atr_value=0.01, account_info={'balance':1000,'equity':1000}, df=None)

    # Ensure log contains skipping message
    assert any('Skipping SL update' in rec.getMessage() for rec in caplog.records)