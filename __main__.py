#!/usr/bin/env python3
"""
Cthulu Rule-Based Trading System - Main Entry Point

Usage:
    python -m cthulu_rb [--config CONFIG_PATH] [--dry-run]
"""
import asyncio
import argparse
import logging
import sys
import signal
from pathlib import Path

# Setup logging first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S'
)
logger = logging.getLogger(__name__)


def print_banner():
    """Print Cthulu ASCII banner."""
    banner = r"""
    _________   __  .__          .__
    \_   ___ \_/  |_|  |__  __ __|  |  __ __
    /    \  \/\   __\  |  \|  |  \  | |  |  \
    \     \____|  | |   Y  \  |  /  |_|  |  /
     \______  /|__| |___|  /____/|____/____/
            \/           \/

        ─────────────────────────────
           Cthulu v6.0.0 Rule-Based
        ─────────────────────────────
    """
    print(banner)


async def main(config_path: str = "config.json", dry_run: bool = False):
    """Main entry point."""
    print_banner()
    
    logger.info("="*80)
    logger.info("Cthulu Rule-Based Trading System v6.0.0")
    logger.info("="*80)
    
    # Import after logging setup
    from core.bootstrap import CthuluBootstrap
    from core.trading_loop import TradingLoop
    
    # Bootstrap system
    logger.info("Phase 1: Bootstrapping system...")
    bootstrap = CthuluBootstrap(config_path)
    
    # Override dry-run if specified
    if dry_run:
        bootstrap.components.config['mode'] = 'dry_run'
    
    components = bootstrap.bootstrap()
    
    # Connect to MT5
    logger.info("Phase 2: Connecting to MT5...")
    if not components.mt5_connector.connect():
        logger.error("Failed to connect to MT5")
        return 1
    
    # Start monitoring
    logger.info("Phase 3: Starting monitoring...")
    components.trade_monitor.start()
    
    # Setup trading loop
    logger.info("Phase 4: Initializing trading loop...")
    trading_loop = TradingLoop(components)
    
    # Setup signal handlers
    shutdown_event = asyncio.Event()
    
    def handle_shutdown(signum, frame):
        logger.info("Shutdown signal received")
        shutdown_event.set()
        trading_loop.stop()
    
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    
    # Run trading loop
    logger.info("Phase 5: Starting trading loop...")
    logger.info("Press Ctrl+C to stop")
    
    try:
        await trading_loop.run()
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    
    # Cleanup
    logger.info("Phase 6: Shutting down...")
    components.trade_monitor.stop()
    components.mt5_connector.disconnect()
    
    logger.info("="*80)
    logger.info("Cthulu shutdown complete")
    logger.info("="*80)
    
    return 0


def run():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Cthulu Rule-Based Trading System")
    parser.add_argument(
        "--config", "-c",
        default="config.json",
        help="Path to configuration file"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run mode (no real trades)"
    )
    
    args = parser.parse_args()
    
    try:
        exit_code = asyncio.run(main(args.config, args.dry_run))
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)


if __name__ == "__main__":
    run()
