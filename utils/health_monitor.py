"""
Connection health monitoring for MT5 connector.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class ConnectionHealthMonitor:
    """
    Monitor connection health and trigger reconnection when needed.
    
    Usage:
        monitor = ConnectionHealthMonitor(connector, check_interval=30)
        
        # In main loop
        if not monitor.health_check():
            logger.error("Connection unhealthy")
    """
    
    def __init__(
        self,
        connector,
        check_interval: int = 30,
        max_failures: int = 3,
        reconnect_callback: Optional[Callable[[], bool]] = None
    ):
        """
        Initialize health monitor.
        
        Args:
            connector: MT5 connector instance
            check_interval: Seconds between health checks
            max_failures: Number of consecutive failures before reconnection
            reconnect_callback: Optional function to call for reconnection
        """
        self.connector = connector
        self.check_interval = check_interval
        self.max_failures = max_failures
        self.reconnect_callback = reconnect_callback
        
        self.last_successful_check: Optional[datetime] = None
        self.last_check_time: Optional[datetime] = None
        self.consecutive_failures = 0
        self.total_failures = 0
        self.total_checks = 0
        
    def should_check(self) -> bool:
        """Determine if health check should be performed."""
        if self.last_check_time is None:
            return True
        
        elapsed = datetime.now() - self.last_check_time
        return elapsed >= timedelta(seconds=self.check_interval)
    
    def health_check(self) -> bool:
        """
        Perform lightweight health check.
        
        Returns:
            True if connection is healthy, False otherwise
        """
        if not self.should_check():
            # Return cached status
            return self.consecutive_failures == 0
        
        self.last_check_time = datetime.now()
        self.total_checks += 1
        
        try:
            # Lightweight check: get account info
            account_info = self.connector.get_account_info()
            
            if account_info:
                self._on_success()
                return True
            else:
                self._on_failure("Account info returned None")
                return False
                
        except Exception as e:
            self._on_failure(str(e))
            return False
    
    def _on_success(self):
        """Handle successful health check."""
        if self.consecutive_failures > 0:
            logger.info(
                f"Connection recovered after {self.consecutive_failures} failures"
            )
        
        self.last_successful_check = datetime.now()
        self.consecutive_failures = 0
    
    def _on_failure(self, reason: str):
        """Handle failed health check."""
        self.consecutive_failures += 1
        self.total_failures += 1
        
        logger.warning(
            f"Health check failed ({self.consecutive_failures}/{self.max_failures}): {reason}"
        )
        
        if self.consecutive_failures >= self.max_failures:
            logger.error(
                f"Connection unhealthy after {self.consecutive_failures} consecutive failures"
            )
            self._trigger_reconnection()
    
    def _trigger_reconnection(self):
        """Attempt to reconnect."""
        logger.info("Attempting reconnection...")
        
        try:
            # Use callback if provided, otherwise use connector's reconnect
            if self.reconnect_callback:
                success = self.reconnect_callback()
            else:
                self.connector.disconnect()
                import time
                time.sleep(5)
                success = self.connector.connect()
            
            if success:
                logger.info("Reconnection successful")
                self.consecutive_failures = 0
            else:
                logger.error("Reconnection failed")
                
        except Exception as e:
            logger.error(f"Reconnection error: {e}")
    
    def get_stats(self) -> dict:
        """Get health monitoring statistics."""
        uptime_pct = 0.0
        if self.total_checks > 0:
            uptime_pct = ((self.total_checks - self.total_failures) / self.total_checks) * 100
        
        return {
            'total_checks': self.total_checks,
            'total_failures': self.total_failures,
            'consecutive_failures': self.consecutive_failures,
            'uptime_percentage': uptime_pct,
            'last_successful_check': self.last_successful_check,
            'is_healthy': self.consecutive_failures < self.max_failures
        }
    
    def reset(self):
        """Reset health monitor statistics."""
        self.consecutive_failures = 0
        self.total_failures = 0
        self.total_checks = 0
        logger.info("Health monitor reset")




