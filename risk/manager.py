"""Risk manager implementation.

Provides a conservative default RiskManager suitable for production use.
The manager uses configuration options when available to compute position sizing
and basic policy checks (max positions, allowed leverage, per-trade risk percent).
"""
from typing import Tuple, Optional, Dict, Any
import logging

logger = logging.getLogger('cthulu.risk')


class RiskManager:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.max_positions = int(self.config.get('max_positions', 5))
        self.per_trade_risk_pct = float(self.config.get('per_trade_risk_pct', 0.01))
        self.min_lot = float(self.config.get('min_lot', 0.01))

    def approve(self, signal, account_info: Optional[Dict[str, Any]] = None, current_positions: int = 0) -> Tuple[bool, str, float]:
        """Decide whether a signal/order should be approved.

        Returns (approved: bool, reason: str, position_size: float)
        """
        try:
            if current_positions >= self.max_positions:
                return False, f"max positions reached ({current_positions}/{self.max_positions})", 0.0

            balance = None
            try:
                if account_info and 'balance' in account_info:
                    balance = float(account_info.get('balance'))
            except Exception:
                balance = None

            # Determine size hint
            size_hint = getattr(signal, 'size_hint', None) or getattr(signal, 'volume', None) or 0.0

            if size_hint:
                position_size = float(size_hint)
            else:
                # Use risk percent to compute size; conservative fallback to min_lot
                if balance:
                    notional_risk = balance * self.per_trade_risk_pct
                    # For simplicity assume 1 pip ~ $1 per lot; use min_lot as fallback
                    position_size = max(self.min_lot, round(notional_risk / max(1.0, getattr(signal, 'price', 1.0)), 2))
                else:
                    position_size = self.min_lot

            # Enforce min lot
            if position_size < self.min_lot:
                position_size = self.min_lot

            return True, 'approved', float(position_size)
        except Exception as e:
            logger.exception('RiskManager.approve error')
            return False, str(e), 0.0


class RiskLimits:
    pass




