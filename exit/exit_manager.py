from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime


@dataclass
class ExitDecision:
    should_exit: bool
    strategy_name: str
    reason: str
    priority: int
    exit_price: Optional[float] = None
    partial_volume: Optional[float] = None
    timestamp: Optional[datetime] = None
    metadata: dict = None


class ExitStrategyManager:
    """Simple orchestrator for exit strategies; evaluates in priority order and returns the highest priority decision.
    
    Priority semantics: Higher numeric value = higher urgency (0-100 scale)
    - 76-100: Critical (stop loss, adverse movement)
    - 51-75: High (session close)
    - 26-50: Medium (profit targets, time-based)
    - 0-25: Low (trailing stops)
    """

    def __init__(self):
        self.strategies = []

    def register(self, strategy):
        self.strategies.append(strategy)
        # Sort descending by priority (higher number = higher urgency)
        self.strategies.sort(key=lambda x: getattr(x, 'priority', 50), reverse=True)

    def evaluate_exit(self, position, current_data=None) -> Optional[ExitDecision]:
        """Run strategies in priority order and return highest priority exit decision.

        Args:
            position: PositionInfo
            current_data: optional market data dictionary
            
        Returns:
            ExitDecision with highest priority, or None if no exit triggered
        """
        current_data = current_data or {}
        best_decision = None
        for strat in self.strategies:
            try:
                result = strat.should_exit(position, current_data)
                if result is not None:
                    # Wrap ExitSignal into ExitDecision
                    ed = ExitDecision(
                        should_exit=True,
                        strategy_name=str(getattr(result, 'strategy_name', strat.name)),
                        reason=getattr(result, 'reason', 'Exit triggered'),
                        priority=getattr(result, 'priority', getattr(strat, 'priority', 50)),
                        exit_price=getattr(result, 'price', None),
                        partial_volume=getattr(result, 'partial_volume', None),
                        timestamp=getattr(result, 'timestamp', None),
                        metadata=getattr(result, 'metadata', None)
                    )
                    # Pick the highest urgency (higher numeric priority)
                    if best_decision is None or ed.priority > best_decision.priority:
                        best_decision = ed
            except Exception:
                continue
        return best_decision




