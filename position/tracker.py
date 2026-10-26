"""
Position Tracker Module

Pure state tracking for open positions. This module maintains the current state
of all open positions without any execution logic, following single responsibility principle.

Responsibilities:
- Track open positions in memory
- Update position prices and P&L
- Calculate exposure metrics
- Query position state

Does NOT:
- Open or close positions (see lifecycle.py)
- Execute trades (see execution/engine.py)
- Make risk decisions (see risk/evaluator.py)
- Handle external trades (see adoption.py)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class PositionInfo:
    """
    Data structure representing a tracked position.
    
    This is a pure data container with no business logic.
    """
    ticket: int
    symbol: str
    type: str  # "buy" or "sell"
    volume: float
    open_price: float
    current_price: float
    sl: Optional[float] = None
    tp: Optional[float] = None
    profit: float = 0.0
    open_time: datetime = field(default_factory=datetime.now)
    magic_number: int = 0
    comment: str = ""
    
    # Strategy tracking
    strategy_name: Optional[str] = None
    entry_reason: Optional[str] = None
    
    # Risk tracking
    initial_risk: float = 0.0
    max_profit: float = 0.0
    max_drawdown: float = 0.0
    
    # Cthulu-specific
    is_external: bool = False  # True if adopted from manual trade
    
    def calculate_profit(self, current_price: float) -> float:
        """Calculate current profit for this position."""
        if self.type == "buy":
            return (current_price - self.open_price) * self.volume
        else:  # sell
            return (self.open_price - current_price) * self.volume
    
    def update_price(self, current_price: float):
        """Update current price and recalculate profit."""
        self.current_price = current_price
        self.profit = self.calculate_profit(current_price)
        
        # Track high water marks
        if self.profit > self.max_profit:
            self.max_profit = self.profit
        if self.profit < self.max_drawdown:
            self.max_drawdown = self.profit


class PositionTracker:
    """
    Tracks open positions in memory with real-time P&L updates.
    
    This class maintains the state of all open positions but does not
    execute any trades. It's designed to be easily testable with mock data.
    """
    
    def __init__(self):
        """Initialize the position tracker."""
        self._positions: Dict[int, PositionInfo] = {}
        logger.info("PositionTracker initialized")
    
    def track_position(self, position: PositionInfo) -> None:
        """
        Add a position to tracking.
        
        Args:
            position: PositionInfo object to track
        """
        self._positions[position.ticket] = position
        logger.info(f"Now tracking position {position.ticket} ({position.symbol} {position.type})")
    
    def update_position(self, ticket: int, current_price: float, 
                       profit: Optional[float] = None) -> None:
        """
        Update a tracked position with new price/profit data.
        
        Args:
            ticket: Position ticket number
            current_price: Current market price
            profit: Optional profit override (if not calculated)
        """
        if ticket not in self._positions:
            logger.warning(f"Attempted to update untracked position {ticket}")
            return
        
        position = self._positions[ticket]
        position.update_price(current_price)
        
        if profit is not None:
            position.profit = profit
    
    def remove_position(self, ticket: int) -> Optional[PositionInfo]:
        """
        Remove a position from tracking (when closed).
        
        Args:
            ticket: Position ticket number
            
        Returns:
            The removed PositionInfo, or None if not found
        """
        position = self._positions.pop(ticket, None)
        if position:
            logger.info(f"Stopped tracking position {ticket}")
        return position
    
    def get_position(self, ticket: int) -> Optional[PositionInfo]:
        """
        Retrieve a specific position by ticket.
        
        Args:
            ticket: Position ticket number
            
        Returns:
            PositionInfo if found, None otherwise
        """
        return self._positions.get(ticket)
    
    def get_all_positions(self) -> List[PositionInfo]:
        """
        Get all tracked positions.
        
        Returns:
            List of all PositionInfo objects
        """
        return list(self._positions.values())
    
    def get_positions_by_symbol(self, symbol: str) -> List[PositionInfo]:
        """
        Get all positions for a specific symbol.
        
        Args:
            symbol: Trading symbol (e.g., "EURUSD")
            
        Returns:
            List of PositionInfo for the symbol
        """
        return [p for p in self._positions.values() if p.symbol == symbol]
    
    def update_prices(self, price_data: Dict[str, float]) -> None:
        """
        Batch update prices for multiple symbols.
        
        Args:
            price_data: Dict mapping symbol -> current price
        """
        for position in self._positions.values():
            if position.symbol in price_data:
                position.update_price(price_data[position.symbol])
    
    def calculate_total_exposure(self) -> float:
        """
        Calculate total exposure across all positions.
        
        Returns:
            Sum of absolute values of all position volumes
        """
        return sum(abs(p.volume) for p in self._positions.values())
    
    def get_position_count(self) -> int:
        """
        Get count of tracked positions.
        
        Returns:
            Number of open positions
        """
        return len(self._positions)
    
    def get_exposure_by_symbol(self) -> Dict[str, float]:
        """
        Calculate exposure grouped by symbol.
        
        Returns:
            Dict mapping symbol -> total volume
        """
        exposure = {}
        for position in self._positions.values():
            if position.symbol not in exposure:
                exposure[position.symbol] = 0.0
            exposure[position.symbol] += abs(position.volume)
        return exposure
    
    def get_total_profit(self) -> float:
        """
        Calculate total profit/loss across all positions.
        
        Returns:
            Sum of all position profits
        """
        return sum(p.profit for p in self._positions.values())
    
    def clear(self) -> None:
        """Clear all tracked positions (for testing/reset)."""
        self._positions.clear()
        logger.info("Position tracker cleared")




