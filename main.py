#!/usr/bin/env python3
"""
Cthulu Rule-Based Trading System - Entry Point
"""
import sys
import os
import asyncio
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S'
)
logger = logging.getLogger(__name__)


def print_banner():
    """Print startup banner."""
    banner = """
_________   __  .__          .__          
\\_   ___ \\_/  |_|  |__  __ __|  |  __ __  
/    \\  \\/\\   __\\  |  \\|  |  \\  | |  |  \\ 
\\     \\____|  | |   Y  \\  |  /  |_|  |  / 
 \\______  /|__| |___|  /____/|____/____/  
        \\/           \\/                   
                                          
    ─────────────────────────────
       Cthulu v6.0.0 Rule-Based
    """
    print(banner)


async def main():
    """Main entry point."""
    print_banner()
    
    try:
        # Import bootstrap
        from core.bootstrap import CthuluBootstrap
        from core.trading_loop import TradingLoop
        
        # Bootstrap system
        logger.info("Phase 1: Bootstrapping system...")
        bootstrap = CthuluBootstrap("config.json")
        components = bootstrap.bootstrap()
        
        # Connect to MT5
        logger.info("Phase 2: Connecting to MT5...")
        if not components.mt5_connector.connect():
            logger.error("Failed to connect to MT5")
            return
        
        # Initialize trading loop
        logger.info("Phase 3: Starting trading loop...")
        trading_loop = TradingLoop(components)
        
        # Run
        await trading_loop.run()
        
    except KeyboardInterrupt:
        logger.info("Shutdown requested...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        logger.info("Cthulu shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
