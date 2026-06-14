# Deprecated Modules Archive

This directory contains legacy code from the Cthulu system before the full architectural overhaul completed in December 2025.

## Archived Files

### Position System (Old)
- `manager.py` (966 lines) - Original PositionManager class
  - **Replaced by:** `position/tracker.py` + `position/lifecycle.py`
  - **Reason:** Split into pure state tracking vs operations for better separation of concerns
  
- `trade_manager.py` (466 lines) - Original TradeManager class  
  - **Replaced by:** `position/adoption.py` (TradeAdoptionManager)
  - **Reason:** Renamed and enhanced with policy-based filtering
  
- `risk_manager.py` (111 lines) - Position-level risk management
  - **Replaced by:** `risk/evaluator.py` (RiskEvaluator)
  - **Reason:** Merged into unified risk evaluation system
  
- `dynamic_manager.py` (121 lines) - Dynamic position evaluation
  - **Replaced by:** Removed (rarely used functionality)
  - **Reason:** Feature was not actively used in production

### Risk System (Old)
- `manager.py` (423 lines) - Original RiskManager class
  - **Replaced by:** `risk/evaluator.py` (RiskEvaluator)
  - **Reason:** Unified risk evaluation with comprehensive checks

### Main Entry Point (Old)
- `__main___old.py` (1,884 lines) - Original god object
  - **Replaced by:** `__main__.py` (192 lines) + core modules
  - **Reason:** 90% reduction through modular architecture

## New Architecture

### Active Modules (Use These)
- `core/indicator_loader.py` - Indicator management
- `core/strategy_factory.py` - Strategy creation
- `core/bootstrap.py` - System initialization
- `core/exit_loader.py` - Exit strategy configuration
- `core/trading_loop.py` - Main trading loop
- `core/shutdown.py` - Graceful shutdown
- `position/tracker.py` - Pure state tracking
- `position/lifecycle.py` - Position operations
- `position/adoption.py` - External trade adoption
- `risk/evaluator.py` - Unified risk evaluation
- `exit/coordinator.py` - Context-aware exit coordination
- `__main__.py` - Clean entry point

## Migration Date
December 27, 2025

## Rollback Instructions
If needed, these files can be restored from this archive. However, the new architecture is production-tested and recommended for all use cases.

## Archived By
GitHub Copilot - Full Architectural Overhaul (Phases 1-10)




