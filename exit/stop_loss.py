from typing import Dict, Any, Optional
from datetime import datetime
from cthulu.exit.base import ExitStrategy, ExitSignal
from cthulu.position.manager import PositionInfo


class StopLossExit(ExitStrategy):
    """Simple stop-loss exit strategy compatible with legacy tests.

    Accepts either a `params` dict or direct kwargs such as `stop_loss_pct`.
    
    Returns ExitSignal when stop loss is triggered, None otherwise.
    """

    def __init__(self, *args, **kwargs):
        if args and isinstance(args[0], dict):
            params = args[0]
        else:
            params = kwargs
        super().__init__(name='StopLossExit', params=params, priority=100)  # High priority - emergency exit
        # allow stop_loss_pct param or use stop_loss field on position
        self.stop_loss_pct = params.get('stop_loss_pct', None)

    def should_exit(self, position: PositionInfo, current_data: Dict[str, Any] = None) -> Optional[ExitSignal]:
        current_price = current_data.get('current_price') if current_data else position.current_price
        if current_price is None:
            return None  # Cannot evaluate without price

        # compare to stop_loss or pct
        if self.stop_loss_pct is not None:
            if position.side == 'BUY':
                sl_price = position.open_price * (1 - self.stop_loss_pct)
                if current_price <= sl_price:
                    return ExitSignal(
                        ticket=position.ticket,
                        reason='Stop loss triggered (pct)',
                        price=current_price,
                        timestamp=datetime.now(),
                        strategy_name=self.name,
                        confidence=1.0,
                        metadata={'stop_loss_pct': self.stop_loss_pct, 'sl_price': sl_price}
                    )
            else:
                sl_price = position.open_price * (1 + self.stop_loss_pct)
                if current_price >= sl_price:
                    return ExitSignal(
                        ticket=position.ticket,
                        reason='Stop loss triggered (pct)',
                        price=current_price,
                        timestamp=datetime.now(),
                        strategy_name=self.name,
                        confidence=1.0,
                        metadata={'stop_loss_pct': self.stop_loss_pct, 'sl_price': sl_price}
                    )
        else:
            if position.stop_loss and position.stop_loss > 0:
                if position.side == 'BUY' and current_price <= position.stop_loss:
                    return ExitSignal(
                        ticket=position.ticket,
                        reason='Stop loss triggered',
                        price=current_price,
                        timestamp=datetime.now(),
                        strategy_name=self.name,
                        confidence=1.0,
                        metadata={'stop_loss': position.stop_loss}
                    )
                if position.side == 'SELL' and current_price >= position.stop_loss:
                    return ExitSignal(
                        ticket=position.ticket,
                        reason='Stop loss triggered',
                        price=current_price,
                        timestamp=datetime.now(),
                        strategy_name=self.name,
                        confidence=1.0,
                        metadata={'stop_loss': position.stop_loss}
                    )

        return None  # No exit signal


# Backwards-compatibility alias
StopLoss = StopLossExit




