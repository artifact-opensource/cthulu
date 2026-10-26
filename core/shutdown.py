"""
Cthulu Shutdown Module

This module handles graceful shutdown of the Cthulu trading system,
extracted from __main__.py for better modularity and testability.

The shutdown process includes:
- Interactive position closure prompts
- Selective position closing (all/none/specific tickets)
- Final metrics persistence
- MT5 disconnection
- Optional component cleanup (News, ML, Monitoring)
- Resource teardown with error isolation
"""

import sys
import os
import logging
from pathlib import Path
from typing import Optional, Callable, Any, Dict


class ShutdownHandler:
    """
    Handles graceful shutdown of the Cthulu trading system.
    
    This class manages the complete shutdown sequence, including:
    - User interaction for position closure decisions
    - Position closing operations
    - Metrics persistence
    - Component cleanup
    - Resource teardown
    
    All error handling is preserved to ensure robust shutdown even
    when individual components fail.
    """
    
    def __init__(
        self,
        position_manager,
        connector,
        database,
        metrics,
        logger: logging.Logger,
        args: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None,
        persist_summary_fn: Optional[Callable] = None,
        summary_path: Optional[Path] = None,
        news_ingestor: Optional[Any] = None,
        ml_collector: Optional[Any] = None,
        trade_monitor: Optional[Any] = None,
        gui_process: Optional[Any] = None,
        observability_process: Optional[Any] = None,
        monitoring_processes: Optional[list] = None
    ):
        """
        Initialize the shutdown handler.
        
        Args:
            position_manager: Position manager instance
            connector: MT5 connector instance
            database: Database instance
            metrics: Metrics collector instance
            logger: Logger instance
            args: Command-line arguments (optional)
            config: System configuration (optional)
            persist_summary_fn: Function to persist metrics summary (optional)
            summary_path: Path to summary file (optional)
            news_ingestor: News ingestor instance (optional)
            ml_collector: ML data collector instance (optional)
            trade_monitor: Trade monitor instance (optional)
            gui_process: GUI subprocess (optional)
            observability_process: Observability service process (optional)
            monitoring_processes: List of monitoring service processes (optional)
        """
        self.position_manager = position_manager
        self.connector = connector
        self.database = database
        self.metrics = metrics
        self.logger = logger
        self.args = args
        self.config = config
        self.persist_summary_fn = persist_summary_fn
        self.summary_path = summary_path
        self.news_ingestor = news_ingestor
        self.ml_collector = ml_collector
        self.trade_monitor = trade_monitor
        self.gui_process = gui_process
        self.observability_process = observability_process
        self.monitoring_processes = monitoring_processes or []
    
    def shutdown(self):
        """
        Execute graceful shutdown sequence.
        
        This method coordinates the entire shutdown process, ensuring that
        all resources are properly cleaned up even if individual steps fail.
        """
        self.logger.info("Initiating graceful shutdown...")
        
        try:
            # 1. Handle open positions
            self._handle_open_positions()
            
            # 2. Persist final metrics
            self._persist_final_metrics()
            
            # 3. Disconnect from MT5
            self._disconnect_mt5()
            
            # 4. Stop optional components
            self._stop_optional_components()
            
            # 5. Final logging
            self._log_shutdown_complete()
        
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}", exc_info=True)
    
    def _handle_open_positions(self):
        """
        Handle open positions during shutdown.
        
        Prompts the user (if not in dry-run mode) for what to do with
        open positions: close all, leave open, or close specific tickets.
        """
        self.logger.info("Checking for open positions during shutdown")
        
        # Check if dry-run mode
        is_dry_run = self.config.get('runtime', {}).get('dry_run', False) if self.config else (self.args.dry_run if self.args else False)
        if is_dry_run:
            self.logger.info("Dry-run mode: skipping position handling")
            return
        
        # Check if there are any open positions (in-memory or from MT5)
        open_positions = self.position_manager.get_all_positions()
        mt5_positions = []
        if self.connector:
            try:
                mt5_positions = self.connector.get_open_positions()
                self.logger.info(f"MT5 positions query returned {len(mt5_positions)} positions")
            except Exception as e:
                self.logger.error(f"Error querying MT5 positions: {e}")
        
        total_positions = len(open_positions) + len(mt5_positions)
        self.logger.info(f"Total positions found: {total_positions} (tracked: {len(open_positions)}, MT5: {len(mt5_positions)})")
        
        if total_positions == 0:
            self.logger.info("No open positions to handle")
            return
        
        self.logger.info(f"Found {total_positions} open positions ({len(open_positions)} tracked, {len(mt5_positions)} in MT5)")
        
        try:
            choice = self._prompt_user_for_position_action()
            
            if choice in ('a', 'all'):
                self._close_all_positions()
            elif choice in ('s', 'select'):
                self._close_selected_positions()
            else:
                self.logger.info("User chose to leave open positions untouched")
        
        except Exception as e:
            self.logger.error(f"Error handling open positions: {e}", exc_info=True)
    
    def _prompt_user_for_position_action(self) -> str:
        """
        Prompt user for what to do with open positions.
        
        Returns:
            User's choice as a string ('a', 'n', 's', etc.)
        """
        prompt_text = (
            "\nShutdown requested. What should I do with open positions?\n"
            "  [A] Close ALL positions\n"
            "  [N] Leave positions OPEN (default)\n"
            "  [S] Close specific tickets (comma-separated)\n"
            "Choose (A/n/s): "
        )
        
        return self._prompt_console(prompt_text, default='n')
    
    def _prompt_console(self, prompt_text: str, default: str = 'n', timeout: float = 10.0) -> str:
        """
        Prompt user for input, with fallback mechanisms and timeout.
        
        This function tries multiple approaches to get user input:
        1. Standard input if available (with timeout)
        2. Platform-specific console access (CONIN$ on Windows, /dev/tty on Unix)
        3. Default value if all else fails
        
        Args:
            prompt_text: Prompt to display to user
            default: Default value if input fails
            timeout: Timeout in seconds for input
            
        Returns:
            User's input as lowercase string
        """
        import threading
        import queue
        
        def input_with_timeout():
            try:
                result = input(prompt_text).strip().lower()
                input_queue.put(result)
            except Exception:
                input_queue.put(default.lower())
        
        try:
            # Try normal input first with timeout
            if sys.stdin.isatty() and not getattr(self.args, 'no_prompt', False):
                input_queue = queue.Queue()
                input_thread = threading.Thread(target=input_with_timeout, daemon=True)
                input_thread.start()
                try:
                    return input_queue.get(timeout=timeout)
                except queue.Empty:
                    self.logger.warning(f"Input timeout after {timeout}s, using default: {default}")
                    return default.lower()
            
            # Fall back to opening the platform console directly
            if os.name == 'nt':
                # Windows: use CONIN$
                with open('CONIN$', 'r') as con:
                    print(prompt_text, end='', flush=True)
                    return con.readline().strip().lower()
            else:
                # Unix: use /dev/tty
                with open('/dev/tty', 'r') as tty:
                    print(prompt_text, end='', flush=True)
                    return tty.readline().strip().lower()
        except KeyboardInterrupt:
            self.logger.warning("Input interrupted, using default: {default}")
            return default.lower()
        except Exception:
            # If all else fails, return default
            return default.lower()
    
    def _close_all_positions(self):
        """Close all open positions."""
        self.logger.info("User requested: close ALL positions")
        
        closed_count = 0
        
        # Close tracked positions
        close_results = self.position_manager.close_all_positions("System shutdown")
        closed_count += len(close_results)
        
        # Close MT5 positions
        if self.connector:
            try:
                mt5_positions = self.connector.get_open_positions()
                for pos in mt5_positions:
                    ticket = pos.get('ticket')
                    if ticket:
                        try:
                            self.connector.close_position(ticket, "System shutdown")
                            closed_count += 1
                        except Exception as e:
                            self.logger.error(f"Failed to close MT5 position {ticket}: {e}")
            except Exception as e:
                self.logger.error(f"Error closing MT5 positions: {e}")
        
        self.logger.info(f"Closed {closed_count} positions total")
    
    def _close_selected_positions(self):
        """Close specific positions selected by user."""
        tickets_input = self._prompt_console("Enter ticket numbers to close (comma-separated): ", '')
        ids = [int(x.strip()) for x in tickets_input.split(',') if x.strip().isdigit()]
        
        closed = 0
        for ticket in ids:
            try:
                res = self.position_manager.close_position(
                    ticket=ticket,
                    reason="User shutdown request"
                )
                if res and hasattr(res, 'status'):
                    closed += 1
            except Exception as e:
                self.logger.error(f"Failed to close ticket {ticket}: {e}")
        
        self.logger.info(f"Closed {closed} user-selected positions")
    
    def _persist_final_metrics(self):
        """Persist final metrics to summary file."""
        self.logger.info("Final performance metrics:")
        
        try:
            if self.persist_summary_fn and self.summary_path:
                self.persist_summary_fn(self.metrics, self.logger, self.summary_path)
        except Exception:
            self.logger.exception('Failed to persist final metrics summary')
    
    def _disconnect_mt5(self):
        """Disconnect from MT5."""
        try:
            self.connector.disconnect()
            self.logger.info("Disconnected from MT5")
        except Exception as e:
            self.logger.error(f"Error disconnecting from MT5: {e}", exc_info=True)
    
    def _stop_optional_components(self):
        """Stop optional components (News, ML, Monitor, GUI, Observability)."""
        # Stop NewsIngestor if it was started
        if self.news_ingestor:
            try:
                self.news_ingestor.stop()
                self.logger.info('NewsIngestor stopped')
            except Exception:
                self.logger.exception('Failed to stop NewsIngestor cleanly')
        
        # Close ML collector if present
        if self.ml_collector:
            try:
                self.ml_collector.close()
                self.logger.info('MLDataCollector closed')
            except Exception:
                self.logger.exception('Failed to close MLDataCollector')
        
        # Stop trade monitor if running
        if self.trade_monitor:
            try:
                if hasattr(self.trade_monitor, 'stop'):
                    self.trade_monitor.stop()
                    self.logger.info('TradeMonitor stopped')
            except Exception:
                self.logger.exception('Failed to stop TradeMonitor')
        
        # Stop trade event bus
        try:
            from observability.trade_event_bus import get_event_bus
            event_bus = get_event_bus()
            if event_bus._running:
                event_bus.stop()
                self.logger.info(f'Trade Event Bus stopped: {event_bus.get_stats()}')
        except Exception:
            self.logger.debug('Failed to stop Trade Event Bus (may not be initialized)')
        
        # Stop Discord notifier
        try:
            from integrations.discord_notifier import stop_discord_notifier
            stop_discord_notifier()
            self.logger.info('Discord notifier stopped')
        except Exception:
            self.logger.debug('Failed to stop Discord notifier (may not be initialized)')
        
        # Stop observability service process
        if self.observability_process:
            try:
                from observability.integration import stop_observability_service
                stop_observability_service(self.observability_process)
                self.logger.info('Observability service stopped')
            except Exception:
                self.logger.exception('Failed to stop observability service')
        
        # Stop monitoring service processes
        if self.monitoring_processes:
            try:
                from monitoring.service import stop_monitoring_services
                stop_monitoring_services(self.monitoring_processes)
                self.logger.info('Monitoring services stopped')
            except Exception:
                self.logger.exception('Failed to stop monitoring services')
        
        # Terminate GUI process if running
        if self.gui_process:
            try:
                if hasattr(self.gui_process, 'terminate'):
                    self.gui_process.terminate()
                    # Give it a moment to terminate gracefully
                    import time
                    time.sleep(1)
                    # Force kill if still running
                    if self.gui_process.poll() is None:
                        self.gui_process.kill()
                    self.logger.info('GUI process terminated')
            except Exception:
                self.logger.exception('Failed to terminate GUI process')
    
    def _log_shutdown_complete(self):
        """Log shutdown completion banner."""
        self.logger.info("=" * 70)
        self.logger.info("Cthulu Autonomous Trading System - Stopped")
        self.logger.info("=" * 70)


def create_shutdown_handler(
    position_manager,
    connector,
    database,
    metrics,
    logger: logging.Logger,
    args: Optional[Any] = None,
    config: Optional[Dict[str, Any]] = None,
    persist_summary_fn: Optional[Callable] = None,
    summary_path: Optional[Path] = None,
    **optional_components
) -> ShutdownHandler:
    """
    Factory function to create a ShutdownHandler with all dependencies.
    
    Args:
        position_manager: Position manager instance
        connector: MT5 connector instance
        database: Database instance
        metrics: Metrics collector instance
        logger: Logger instance
        args: Command-line arguments (optional)
        config: System configuration (optional)
        persist_summary_fn: Function to persist metrics summary (optional)
        summary_path: Path to summary file (optional)
        **optional_components: Additional optional components (news_ingestor, ml_collector, etc.)
        
    Returns:
        Configured ShutdownHandler instance
    """
    return ShutdownHandler(
        position_manager=position_manager,
        connector=connector,
        database=database,
        metrics=metrics,
        logger=logger,
        args=args,
        config=config,
        persist_summary_fn=persist_summary_fn,
        summary_path=summary_path,
        news_ingestor=optional_components.get('news_ingestor'),
        ml_collector=optional_components.get('ml_collector'),
        trade_monitor=optional_components.get('trade_monitor'),
        gui_process=optional_components.get('gui_process'),
        observability_process=optional_components.get('observability_process'),
        monitoring_processes=optional_components.get('monitoring_processes')
    )




