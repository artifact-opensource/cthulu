"""External trade detection and adoption manager.

Scans MT5 for positions that were not opened by Cthulu (different magic number) and
adopts them into the PositionManager for management under configured policy.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import logging

from cthulu.position.manager import PositionInfo, PositionManager
from cthulu.connector.mt5_connector import mt5

logger = logging.getLogger('cthulu.trade_manager')


@dataclass
class TradeAdoptionPolicy:
    enabled: bool = True
    adopt_symbols: List[str] = field(default_factory=list)
    ignore_symbols: List[str] = field(default_factory=list)
    apply_exit_strategies: bool = True
    max_adoption_age_hours: float = 0.0
    log_only: bool = False


class TradeManager:
    def __init__(self, position_manager: PositionManager, policy: Optional[TradeAdoptionPolicy] = None, magic_number: int = 0):
        self.position_manager = position_manager
        self.policy = policy or TradeAdoptionPolicy()
        self.magic_number = magic_number or 0
        self._adopted_tickets = set()
        self._adoption_log: List[Dict[str, Any]] = []

    def scan_for_external_trades(self) -> List[PositionInfo]:
        if not self.policy.enabled:
            return []

        try:
            positions = mt5.positions_get()
        except Exception:
            logger.exception('Failed to fetch positions from MT5')
            return []

        result = []
        now_ts = datetime.now(timezone.utc).timestamp()
        for p in positions or []:
            try:
                # Skip if Cthulu's own magic number
                if getattr(p, 'magic', None) == self.magic_number:
                    continue

                symbol = getattr(p, 'symbol', None)
                if not symbol:
                    continue

                if self.policy.adopt_symbols and symbol not in self.policy.adopt_symbols:
                    continue
                if symbol in self.policy.ignore_symbols:
                    continue

                # Age check
                if self.policy.max_adoption_age_hours and getattr(p, 'time', None):
                    age_hours = (now_ts - float(getattr(p, 'time')))/3600.0
                    if age_hours > float(self.policy.max_adoption_age_hours):
                        continue

                side = 'BUY' if getattr(p, 'type', None) == getattr(mt5, 'ORDER_TYPE_BUY', 0) else 'SELL'

                pos = PositionInfo(
                    ticket=int(getattr(p, 'ticket', 0)),
                    symbol=symbol,
                    volume=float(getattr(p, 'volume', 0.0)),
                    open_price=float(getattr(p, 'price_open', getattr(p, 'open_price', 0.0))),
                    open_time=datetime.fromtimestamp(float(getattr(p, 'time', now_ts)), tz=timezone.utc),
                    current_price=float(getattr(p, 'price_current', getattr(p, 'price', 0.0))),
                    side=side,
                    metadata={'magic': getattr(p, 'magic', None), 'comment': getattr(p, 'comment', None)}
                )
                result.append(pos)
            except Exception:
                logger.exception('Failed to process MT5 position')
                continue

        return result

    def adopt_trades(self, trades: List[PositionInfo]) -> int:
        if not trades:
            return 0

        count = 0
        for t in trades:
            if self.is_adopted(t.ticket):
                continue

            if self.policy.log_only:
                self._adoption_log.append({'ticket': t.ticket, 'symbol': t.symbol, 'ts': datetime.utcnow().isoformat()})
                continue

            # Adopt into position manager
            try:
                self.position_manager.add_position(t)
                self._adopted_tickets.add(t.ticket)
                self._adoption_log.append({'ticket': t.ticket, 'symbol': t.symbol, 'ts': datetime.utcnow().isoformat()})
                count += 1
            except Exception:
                logger.exception('Failed to adopt trade')
        return count

    def is_adopted(self, ticket: int) -> bool:
        return ticket in self._adopted_tickets

    def get_adoption_log(self) -> List[Dict[str, Any]]:
        return list(self._adoption_log)

    # Backwards compatible name used in trading loop
    def scan_and_adopt(self) -> int:
        trades = self.scan_for_external_trades()
        if not trades:
            return 0
        return self.adopt_trades(trades)




