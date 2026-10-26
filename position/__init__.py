"""
Position Management Module - Consolidated Architecture

Real-time position tracking, lifecycle management, and external trade adoption.

New modular structure:
- tracker.py: Pure state tracking (no execution)
- lifecycle.py: Position operations (open, close, modify, exits)
- adoption.py: External trade management

Legacy modules (deprecated, will be removed):
- manager.py: Split into tracker + lifecycle
- trade_manager.py: Renamed to adoption.py
- risk_manager.py: Merged into risk/evaluator.py
- dynamic_manager.py: Removed (rarely used)
"""

"""Position package exports.

Note: Import concrete classes from their modules where needed to prevent 
circular imports. For example:
  from position.tracker import PositionTracker
  from position.lifecycle import PositionLifecycle
"""

__all__ = [
    # Intentionally minimal to avoid circular imports
    # Import specific classes from submodules as needed
]





