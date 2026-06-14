"""
Cthulu Autonomous Trading System

Main entry point - orchestrates system startup, trading loop, and shutdown.

This is the entry point that delegates to modular components:
- core.bootstrap: System initialization
- core.trading_loop: Main trading logic
- core.shutdown: Graceful shutdown
"""

import sys
import signal as sig_module
import logging
import argparse
import atexit
import os
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Singleton lock file path
LOCK_FILE = Path(__file__).parent.parent / "cthulu.lock"


class SingletonLock:
    """Prevents multiple Cthulu instances from running simultaneously."""
    
    def __init__(self):
        self.lock_file = LOCK_FILE
        self.lock_fd = None
        
    def acquire(self) -> bool:
        """Acquire singleton lock. Returns True if successful, False if another instance running."""
        try:
            # Check if lock file exists and contains a running PID
            if self.lock_file.exists():
                try:
                    existing_pid = int(self.lock_file.read_text().strip())
                    # Check if that PID is still running
                    if self._is_process_running(existing_pid):
                        return False  # Another instance is running
                except (ValueError, FileNotFoundError):
                    pass  # Invalid or missing lock file, proceed
            
            # Write our PID to lock file
            self.lock_file.write_text(str(os.getpid()))
            atexit.register(self.release)
            return True
            
        except Exception:
            return True  # On error, allow startup but warn
    
    def _is_process_running(self, pid: int) -> bool:
        """Check if a process with given PID is running."""
        try:
            if sys.platform == 'win32':
                import ctypes
                kernel32 = ctypes.windll.kernel32
                PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
                if handle:
                    kernel32.CloseHandle(handle)
                    return True
                return False
            else:
                os.kill(pid, 0)
                return True
        except (OSError, PermissionError):
            return False
    
    def release(self):
        """Release the singleton lock."""
        try:
            if self.lock_file.exists():
                current_pid = self.lock_file.read_text().strip()
                if current_pid == str(os.getpid()):
                    self.lock_file.unlink()
        except Exception:
            pass


# Global singleton lock
_singleton_lock = SingletonLock()

__version__ = "6.0.0"  # K9 Release - Autonomous Multi-Asset Intelligence

from core.bootstrap import CthuluBootstrap, SystemComponents
from core.trading_loop import TradingLoop, TradingLoopContext, ensure_runtime_indicators
from core.shutdown import ShutdownHandler, create_shutdown_handler
from config_schema import Config
from config.mindsets import apply_mindset, list_mindsets
from observability.logger import setup_logger
from cognition import get_cognition_engine

# Backwards-compatible helper for tests & integrations
# Signature matches older tests: init_ml_collector(config, args, logger)
def init_ml_collector(config=None, args=None, logger=None):
    """Initialize ML collector based on config and CLI args.

    Args:
        config: Application configuration dict/object
        args: Parsed CLI args (may contain flags to enable/disable ML)
        logger: Optional logger
    Returns: MLDataCollector-like object (best-effort stub if unavailable)
    """
    try:
        enabled = False
        prefix = 'events'

        if config is not None:
            try:
                # config may be dict-like
                enabled = bool(config.get('ml', {}).get('enabled', False))
                prefix = config.get('ml', {}).get('prefix', prefix)
            except Exception:
                pass

        # CLI arg override (support both enable_ml and ml flags)
        try:
            if args is not None and getattr(args, 'enable_ml', None) is not None:
                # Explicit CLI override: if False, disable collector (return None)
                if getattr(args, 'enable_ml') is False:
                    return None
                enabled = bool(getattr(args, 'enable_ml'))
            elif args is not None and getattr(args, 'ml', None) is not None:
                enabled = bool(getattr(args, 'ml'))
        except Exception:
            pass

        if not enabled:
            # return a no-op stub
            class _Stub:
                def record_event(self, *args, **kwargs):
                    return
                def record_order(self, *args, **kwargs):
                    return
                def record_execution(self, *args, **kwargs):
                    return
                def close(self, *args, **kwargs):
                    return
            return _Stub()

        from ML_RL.instrumentation import MLDataCollector
        return MLDataCollector(prefix=prefix)
    except Exception:
        # Best-effort stub if ML collector is unavailable or fails to initialize
        class _Stub2:
            def record_event(self, *args, **kwargs):
                return
            def record_order(self, *args, **kwargs):
                return
            def record_execution(self, *args, **kwargs):
                return
            def close(self, *args, **kwargs):
                return
        return _Stub2()

# Global shutdown flag
shutdown_requested = False


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global shutdown_requested
    if not shutdown_requested:
        shutdown_requested = True
        print("\nShutdown signal received, initiating graceful shutdown...")
        # Raise KeyboardInterrupt to interrupt the current execution
        raise KeyboardInterrupt()


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Cthulu Autonomous Trading System v5.0")
    parser.add_argument("--config", type=str, default="config.json",
                       help="Path to configuration file")
    parser.add_argument("--mindset", type=str, default=None,
                       help="Trading mindset (conservative/balanced/aggressive/ultra_aggressive)")
    parser.add_argument("--list-mindsets", action="store_true",
                       help="List available mindsets and exit")
    parser.add_argument("--dry-run", action="store_true",
                       help="Dry run mode (no actual trades)")
    parser.add_argument("--advisory", action="store_true",
                       help="Advisory mode (signals only, no execution)")
    parser.add_argument("--ghost", action="store_true",
                       help="Ghost mode (test strategy without actual trades)")
    parser.add_argument('--skip-setup', action='store_true',
                       help="Skip interactive setup wizard (for automation/headless runs)")
    parser.add_argument("--max-loops", type=int, default=None,
                       help="Maximum iterations (for testing)")
    parser.add_argument('--wizard', action='store_true',
                       help="Open the interactive setup wizard and optionally start profiles")
    parser.add_argument('--wizard-ai', action='store_true',
                       help="Run the lightweight NLP-based wizard (describe intent in natural language)")
    return parser.parse_args()


def main():
    """
    Main entry point for Cthulu trading system.
    
    Flow:
        1. Check singleton lock (prevent duplicate instances)
        2. Parse arguments
        3. Bootstrap system (initialize all components)
        4. Run trading loop
        5. Graceful shutdown
    """
    global shutdown_requested
    
    # CRITICAL: Prevent multiple instances from running simultaneously
    if not _singleton_lock.acquire():
        print("\n" + "=" * 60)
        print("ERROR: Another Cthulu instance is already running!")
        print("=" * 60)
        print("\nOnly one Cthulu instance can trade at a time to prevent")
        print("conflicting signals (e.g., simultaneous BUY and SELL).")
        print("\nTo start a new instance:")
        print("  1. Stop the existing instance first, OR")
        print("  2. Delete the lock file: cthulu.lock")
        print("=" * 60 + "\n")
        return 1
    
    # Parse command line arguments
    args = parse_arguments()
    
    # Handle --list-mindsets
    if args.list_mindsets:
        print("\nAvailable Mindsets:")
        print("=" * 50)
        for name, description in list_mindsets().items():
            print(f"\n{name}:")
            print(f"  {description}")
        print("\n" + "=" * 50)
        return 0
        
    # If user requested the NLP or interactive wizard via CLI, run it now
    if args.wizard_ai:
        from config.wizard import run_nlp_wizard
        result = run_nlp_wizard(args.config)
        if result is None:
            print("Setup cancelled. Exiting.")
            return 0
        # Continue startup using the configured settings
        args.skip_setup = True

    if args.wizard:
        from config.wizard import run_setup_wizard
        result = run_setup_wizard(args.config)
        if result is None:
            print("Setup cancelled. Exiting.")
            return 0
        # Continue startup using the configured settings
        args.skip_setup = True

    # Setup logger
    # Allow overriding log level via environment variable LOG_LEVEL (e.g., DEBUG)
    log_level = os.getenv('LOG_LEVEL', 'INFO')
    logger = setup_logger(
        name="Cthulu",
        log_file="logs/Cthulu.log",
        level=log_level
    )
    
    logger.info("=" * 80)
    logger.info(f"Cthulu Autonomous Trading System v{__version__}")
    logger.info("=" * 80)
    logger.info(f"Configuration: {args.config}")
    logger.info(f"Mindset: {args.mindset or 'default'}")
    logger.info(f"Mode: {'Dry-run' if args.dry_run else 'Advisory' if args.advisory else 'Ghost' if args.ghost else 'Live'}")
    logger.info("=" * 80)
    
    # Register signal handlers
    sig_module.signal(sig_module.SIGINT, signal_handler)
    sig_module.signal(sig_module.SIGTERM, signal_handler)
    
    components: Optional[SystemComponents] = None
    
    try:
        # Phase 1: Bootstrap system
        logger.info("Phase 1: Bootstrapping system...")
        bootstrap = CthuluBootstrap(logger=logger)
        components = bootstrap.bootstrap(args.config, args)
        logger.info("System bootstrap complete")
        
        # Phase 2: Create trading loop context
        logger.info("Phase 2: Initializing trading loop...")
        # Normalize timeframe: convert TIMEFRAME_* strings to MT5 constants where possible
        tf_raw = components.config.get('trading', {}).get('timeframe', 'TIMEFRAME_H1')
        tf_val = tf_raw
        if isinstance(tf_raw, str) and tf_raw.startswith('TIMEFRAME_'):
            try:
                import MetaTrader5 as mt5_pkg
                tf_val = getattr(mt5_pkg, tf_raw, tf_raw)
            except Exception:
                # Fallback mapping for common timeframes
                _tf_map = {
                    'TIMEFRAME_M1': 1,
                    'TIMEFRAME_M5': 5,
                    'TIMEFRAME_M15': 15,
                    'TIMEFRAME_M30': 30,
                    'TIMEFRAME_H1': 60,
                    'TIMEFRAME_H4': 240,
                    'TIMEFRAME_D1': 1440
                }
                tf_val = _tf_map.get(tf_raw, tf_raw)

        trading_context = TradingLoopContext(
            connector=components.connector,
            data_layer=components.data_layer,
            strategy=components.strategy,
            execution_engine=components.execution_engine,
            risk_manager=components.risk_manager,
            position_tracker=components.position_tracker,
            position_manager=components.position_manager,
            position_lifecycle=components.position_lifecycle,
            trade_adoption_manager=components.trade_adoption_manager,
            trade_adoption_policy=components.trade_adoption_policy,
            exit_coordinator=components.exit_coordinator,
            database=components.database,
            metrics=components.metrics,
            logger=logger,
            symbol=components.config.get('trading', {}).get('symbol', 'EURUSD'),
            timeframe=tf_val,
            poll_interval=components.config.get('trading', {}).get('poll_interval', 60),
            lookback_bars=components.config.get('trading', {}).get('lookback_bars', 100),
            dry_run=args.dry_run,
            indicators=components.indicators or [],
            exit_strategies=components.exit_strategies or [],
            config=components.config,
            args=args,
            ml_collector=components.ml_collector,
            advisory_manager=components.advisory_manager,
            exporter=components.exporter,
            dynamic_sltp_manager=components.dynamic_sltp_manager,
            adaptive_drawdown_manager=components.adaptive_drawdown_manager,
            profit_scaler=getattr(components, 'profit_scaler', None),
            adaptive_account_manager=getattr(components, 'adaptive_account_manager', None),
            adaptive_loss_curve=getattr(components, 'adaptive_loss_curve', None),
            indicator_collector=getattr(components, 'indicator_collector', None),
            system_health_collector=getattr(components, 'system_health_collector', None),
            comprehensive_collector=getattr(components, 'comprehensive_collector', None),
            hektor_adapter=getattr(components, 'hektor_adapter', None),
            hektor_retriever=getattr(components, 'hektor_retriever', None),
            ml_enhancement_manager=getattr(components, 'ml_enhancement_manager', None),
        )
        
        # Initialize Cognition Engine (AI/ML layer)
        try:
            cognition_engine = get_cognition_engine()
            trading_context.cognition_engine = cognition_engine
            logger.info("Cognition Engine initialized - AI/ML signal enhancement active")
        except Exception as e:
            logger.warning(f"Cognition Engine not available: {e} - running in rule-based mode")
        
        # Log collector status
        logger.info(f"Context collectors: indicator={trading_context.indicator_collector is not None}, "
                   f"comprehensive={trading_context.comprehensive_collector is not None}, "
                   f"system_health={trading_context.system_health_collector is not None}")
        logger.info(f"Components collectors: indicator={getattr(components, 'indicator_collector', None) is not None}, "
                   f"comprehensive={getattr(components, 'comprehensive_collector', None) is not None}")
        
        # Log Hektor (Vector Studio) status
        if trading_context.hektor_adapter:
            hektor_stats = trading_context.hektor_adapter.get_stats()
            fallback_status = "fallback" if hektor_stats.get('using_fallback', False) else "native"
            logger.info(f"Hektor semantic memory: ACTIVE ({fallback_status})")
        else:
            logger.info("Hektor semantic memory: DISABLED")
        
        trading_loop = TradingLoop(trading_context)
        logger.info("Trading loop initialized")
        
        # Phase 3: Run trading loop
        logger.info("Phase 3: Starting trading loop...")
        logger.info("Press Ctrl+C to stop")
        trading_loop.run()
        
        logger.info("Trading loop completed")
        
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        shutdown_requested = True
        
    except Exception as e:
        logger.error(f"Fatal error in main loop: {e}", exc_info=True)
        shutdown_requested = True
        return 1
        
    finally:
        # Phase 4: Graceful shutdown
        if components:
            logger.info("Phase 4: Initiating graceful shutdown...")
            
            # Close Hektor connection gracefully
            try:
                if getattr(components, 'hektor_adapter', None):
                    components.hektor_adapter.close()
                    logger.info("Hektor semantic memory closed")
            except Exception as e:
                logger.debug(f"Hektor close error: {e}")
            
            try:
                shutdown_handler = create_shutdown_handler(
                    position_manager=components.position_manager,
                    connector=components.connector,
                    database=components.database,
                    metrics=components.metrics,
                    logger=logger,
                    args=args,
                    config=components.config,
                    ml_collector=components.ml_collector,
                    trade_monitor=components.monitor,
                    gui_process=getattr(components, 'gui_process', None),
                    observability_process=getattr(components, 'observability_process', None),
                    monitoring_processes=getattr(components, 'monitoring_processes', None)
                )
                
                shutdown_handler.shutdown()
                logger.info("Graceful shutdown complete")
                
            except Exception as e:
                logger.error(f"Error during shutdown: {e}", exc_info=True)
                
        logger.info("=" * 80)
        logger.info("Cthulu shutdown complete")
        logger.info("=" * 80)
        
    return 0


if __name__ == "__main__":
    sys.exit(main())





