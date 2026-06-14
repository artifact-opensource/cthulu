"""
Strategy Module

Defines base strategy interface and signal structures.
Provides pluggable strategy architecture with standardized signal generation.
"""

import pandas as pd
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class SignalType(Enum):
    """Signal action types"""
    LONG = "LONG"
    SHORT = "SHORT"
    CLOSE = "CLOSE"
    NONE = "NONE"


@dataclass
class Signal:
    """
    Trading signal structure.
    
    Attributes:
        id: Unique signal identifier
        timestamp: Signal generation time
        symbol: Trading symbol
        timeframe: Analysis timeframe
        side: Signal direction (LONG/SHORT/CLOSE)
        action: Specific action to take
        size_hint: Suggested position size
        price: Entry price (None for market orders)
        stop_loss: Stop loss level
        take_profit: Take profit level
        confidence: Signal confidence (0.0 to 1.0)
        reason: Human-readable explanation
        metadata: Additional signal data
    """
    id: str
    timestamp: datetime
    symbol: str
    timeframe: str
    side: SignalType
    action: str
    size_hint: Optional[float] = None
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    confidence: float = 0.5
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert signal to dictionary."""
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat(),
            'symbol': self.symbol,
            'timeframe': self.timeframe,
            'side': self.side.value,
            'action': self.action,
            'size_hint': self.size_hint,
            'price': self.price,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'confidence': self.confidence,
            'reason': self.reason,
            'metadata': self.metadata
        }


class Strategy(ABC):
    """
    Base strategy interface.
    
    All trading strategies must inherit from this class and implement
    the required methods.
    """
    
    def __init__(self, name: str, config: Dict[str, Any]):
        """
        Initialize strategy.
        
        Args:
            name: Strategy name
            config: Strategy configuration parameters
        """
        self.name = name
        self.config = config
        self.logger = logging.getLogger(f"cthulu.strategy.{name}")
        self._state: Dict[str, Any] = {}
        
    @abstractmethod
    def on_bar(self, bar: pd.Series) -> Optional[Signal]:
        """
        Process new bar and generate signal.
        
        Args:
            bar: Latest OHLCV bar as pandas Series
            
        Returns:
            Signal object or None
        """
        pass
        
    def on_tick(self, tick: Dict[str, Any]) -> Optional[Signal]:
        """
        Process new tick (optional, for high-frequency strategies).
        
        Args:
            tick: Tick data dictionary
            
        Returns:
            Signal object or None
        """
        return None
        
    def configure(self, params: Dict[str, Any]):
        """
        Update strategy parameters.
        
        Args:
            params: Parameter dictionary
        """
        self.config.update(params)
        self.logger.info(f"Strategy {self.name} reconfigured")
        
    def state(self) -> Dict[str, Any]:
        """
        Get current strategy state.
        
        Returns:
            State dictionary
        """
        return self._state.copy()
        
    def reset(self):
        """Reset strategy state."""
        self._state.clear()
        self.logger.info(f"Strategy {self.name} reset")
        
    def generate_signal_id(self) -> str:
        """
        Generate unique signal ID.
        
        Returns:
            Signal ID string
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return f"{self.name}_{timestamp}"
        
    def validate_signal(self, signal: Signal) -> bool:
        """
        Validate signal before returning.
        
        Args:
            signal: Signal to validate
            
        Returns:
            True if valid
        """
        if signal is None:
            return False
            
        # Check required fields
        if not signal.symbol or not signal.side:
            self.logger.error("Signal missing required fields")
            return False
            
        # Validate confidence
        if not 0.0 <= signal.confidence <= 1.0:
            self.logger.warning(f"Invalid confidence: {signal.confidence}")
            signal.confidence = max(0.0, min(1.0, signal.confidence))
            
        # Validate SL/TP if present
        if signal.side == SignalType.LONG:
            if signal.stop_loss and signal.price and signal.stop_loss >= signal.price:
                self.logger.error("Invalid stop loss for LONG signal")
                return False
            if signal.take_profit and signal.price and signal.take_profit <= signal.price:
                self.logger.error("Invalid take profit for LONG signal")
                return False
                
        elif signal.side == SignalType.SHORT:
            if signal.stop_loss and signal.price and signal.stop_loss <= signal.price:
                self.logger.error("Invalid stop loss for SHORT signal")
                return False
            if signal.take_profit and signal.price and signal.take_profit >= signal.price:
                self.logger.error("Invalid take profit for SHORT signal")
                return False
                
        return True




