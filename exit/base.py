"""
Base Exit Strategy Module

Abstract base class for all exit strategies.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

from cthulu.position.manager import PositionInfo


@dataclass
class ExitSignal:
    """
    Exit signal structure.
    
    Attributes:
        ticket: Position ticket to exit
        reason: Exit reason (strategy name + condition)
        price: Optional target exit price
        timestamp: Signal generation time
        strategy_name: Name of strategy generating signal
        confidence: Signal confidence (0.0 to 1.0)
        partial_volume: Optional volume for partial exit
        metadata: Additional signal data
    """
    ticket: int
    reason: str
    price: Optional[float]
    timestamp: datetime
    strategy_name: str
    confidence: float = 1.0
    partial_volume: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class ExitStrategy(ABC):
    """
    Abstract exit strategy base class.
    
    All exit strategies must inherit from this class and implement should_exit().
    Provides standardized interface for exit detection, configuration, and state management.
    """
    
    def __init__(self, name: str, params: Dict[str, Any], priority: int = 50):
        """
        Initialize exit strategy.
        
        Args:
            name: Strategy name
            params: Configuration parameters
            priority: Strategy priority (0-100, higher = more urgent)
                     0-25: Low priority (trailing stops)
                     26-50: Medium priority (profit targets, time-based)
                     51-75: High priority (session close)
                     76-100: Critical priority (adverse movement, emergency)
        """
        self.name = name
        self.params = params
        self.priority = priority
        self.logger = logging.getLogger(f"cthulu.exit.{name}")
        self._state: Dict[str, Any] = {}
        self._enabled = True
        
    @abstractmethod
    def should_exit(
        self,
        position: PositionInfo,
        current_data: Dict[str, Any]
    ) -> Optional[ExitSignal]:
        """
        Determine if position should be exited.
        
        Args:
            position: PositionInfo object with current position data
            current_data: Dictionary with current market data:
                - 'current_price': Current market price
                - 'current_data': Latest OHLCV bar (pd.Series)
                - 'account_info': Account information dict
                - 'indicators': Optional indicator values
                
        Returns:
            ExitSignal if exit conditions met, None otherwise
        """
        pass
        
    def configure(self, params: Dict[str, Any]):
        """
        Update strategy parameters.
        
        Args:
            params: Parameter dictionary
        """
        self.params.update(params)
        self.logger.info(f"Exit strategy {self.name} reconfigured: {params}")
        
    def enable(self):
        """Enable this exit strategy."""
        self._enabled = True
        self.logger.info(f"Exit strategy {self.name} enabled")
        
    def disable(self):
        """Disable this exit strategy."""
        self._enabled = False
        self.logger.info(f"Exit strategy {self.name} disabled")
        
    def is_enabled(self) -> bool:
        """Check if strategy is enabled."""
        return self._enabled
        
    def reset(self):
        """Reset strategy internal state."""
        self._state.clear()
        self.logger.debug(f"{self.name} state reset")
        
    def state(self) -> Dict[str, Any]:
        """
        Get current strategy state.
        
        Returns:
            Dictionary with strategy state and metadata
        """
        return {
            'name': self.name,
            'params': self.params,
            'priority': self.priority,
            'enabled': self._enabled,
            'state': self._state.copy()
        }
        
    def get_metadata(self) -> Dict[str, Any]:
        """
        Get strategy metadata for exit signal enrichment.
        
        Returns:
            Dictionary with strategy name, parameters, and priority
        """
        return {
            'strategy_name': self.name,
            'parameters': self.params,
            'priority': self.priority
        }




