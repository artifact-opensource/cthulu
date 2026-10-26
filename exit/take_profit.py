from typing import Dict, Any, Optional
from datetime import datetime
from cthulu.exit.base import ExitStrategy, ExitSignal
from cthulu.position.manager import PositionInfo


class TakeProfitExit(ExitStrategy):
    """Simple take profit strategy, legacy-compatible.

    Accepts `take_profit_pct` kwarg or uses `position.take_profit` if set.
    Returns ExitSignal when take profit is triggered, None otherwise.
    """

    def __init__(self, *args, **kwargs):
        if args and isinstance(args[0], dict):
            params = args[0]
        else:
            params = kwargs
        super().__init__(name='TakeProfitExit', params=params, priority=50)  # Medium priority
        self.take_profit_pct = params.get('take_profit_pct', None)

    def should_exit(self, position: PositionInfo, current_data: Dict[str, Any] = None) -> Optional[ExitSignal]:
        current_price = current_data.get('current_price') if current_data else position.current_price
        if current_price is None:
            return None  # Cannot evaluate without price

        if self.take_profit_pct is not None:
            if position.side == 'BUY' and current_price >= position.open_price * (1 + self.take_profit_pct):
                return ExitSignal(
                    ticket=position.ticket,
                    reason='Take profit hit (pct)',
                    price=current_price,
                    timestamp=datetime.now(),
                    strategy_name=self.name,
                    confidence=1.0,
                    metadata={'take_profit_pct': self.take_profit_pct}
                )
            if position.side == 'SELL' and current_price <= position.open_price * (1 - self.take_profit_pct):
                return ExitSignal(
                    ticket=position.ticket,
                    reason='Take profit hit (pct)',
                    price=current_price,
                    timestamp=datetime.now(),
                    strategy_name=self.name,
                    confidence=1.0,
                    metadata={'take_profit_pct': self.take_profit_pct}
                )

        # Or use explicit position.take_profit if provided
        if position.take_profit and position.take_profit > 0:
            if position.side == 'BUY' and current_price >= position.take_profit:
                return ExitSignal(
                    ticket=position.ticket,
                    reason='Take profit reached',
                    price=current_price,
                    timestamp=datetime.now(),
                    strategy_name=self.name,
                    confidence=1.0,
                    metadata={'take_profit': position.take_profit}
                )
            if position.side == 'SELL' and current_price <= position.take_profit:
                return ExitSignal(
                    ticket=position.ticket,
                    reason='Take profit reached',
                    price=current_price,
                    timestamp=datetime.now(),
                    strategy_name=self.name,
                    confidence=1.0,
                    metadata={'take_profit': position.take_profit}
                )

        return None  # No exit signal

# Backwards-compatible alias
TakeProfit = TakeProfitExit




