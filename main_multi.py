"""
Multi-Symbol Main Entry Point
Launches the multi-symbol orchestrator instead of single-symbol loop.
"""
import sys
import os
import asyncio
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S'
)
logger = logging.getLogger(__name__)


def print_banner():
    banner = """
_________   __  .__          .__          
\\_   ___ \\_/  |_|  |__  __ __|  |  __ __  
/    \\  \\/\\   __\\  |  \\|  |  \\  | |  |  \\ 
\\     \\____|  | |   Y  \\  |  /  |_|  |  / 
 \\______  /|__| |___|  /____/|____/____/  
        \\/           \\/                   

    ─────────────────────────────
     Cthulu v5.3.0 Multi-Symbol
    ─────────────────────────────
    """
    print(banner)


async def main():
    print_banner()
    
    try:
        from core.bootstrap import CthuluBootstrap
        
        # Determine config
        config_path = sys.argv[1] if len(sys.argv) > 1 else "config.json"
        
        # Bootstrap system
        logger.info("Phase 1: Bootstrapping system...")
        bootstrap = CthuluBootstrap(config_path)
        components = bootstrap.bootstrap()
        
        # Connect
        logger.info("Phase 2: Connecting to MT5 bridge...")
        if not components.mt5_connector.connect():
            logger.error("Failed to connect to MT5 bridge")
            return
        
        # Check if multi-symbol mode
        config = components.config
        if 'watchlist' in config and len(config.get('watchlist', [])) > 1:
            # Multi-symbol orchestrator
            logger.info("Phase 3: Starting MULTI-SYMBOL orchestrator...")
            from core.multi_symbol import MultiSymbolOrchestrator
            orchestrator = MultiSymbolOrchestrator(components, config)
            await orchestrator.run()
        else:
            # Fallback to single-symbol loop
            logger.info("Phase 3: Starting single-symbol trading loop...")
            from core.trading_loop import TradingLoop
            trading_loop = TradingLoop(components)
            await trading_loop.run()
        
    except KeyboardInterrupt:
        logger.info("Shutdown requested...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        logger.info("Cthulu shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
