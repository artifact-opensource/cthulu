"""
Cthulu Exception Handling Module

Provides structured exception handling to eliminate silent failures.
All exceptions are categorized, logged, and handled appropriately.

Categories:
- CriticalTradingError: Must halt trading (order failures, position issues)
- RecoverableError: Can continue with degraded functionality
- ConfigurationError: Invalid setup, needs user intervention
- ConnectionError: MT5/network issues, can retry
- DataError: Invalid/missing market data

Usage:
    from cthulu.core.exceptions import (
        handle_exception, CriticalTradingError, RecoverableError,
        safe_execute, log_and_continue
    )
"""

import logging
import traceback
import functools
from typing import Optional, Any, Callable, TypeVar, Type
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Error severity levels"""
    CRITICAL = "CRITICAL"   # Must halt trading
    ERROR = "ERROR"         # Logged, may impact functionality
    WARNING = "WARNING"     # Logged, continues normally
    INFO = "INFO"           # Informational, expected failures


class CthulhuBaseException(Exception):
    """Base exception for all Cthulu errors"""
    severity = ErrorSeverity.ERROR
    
    def __init__(self, message: str, details: Optional[dict] = None):
        self.message = message
        self.details = details or {}
        self.timestamp = datetime.utcnow()
        super().__init__(message)
    
    def to_dict(self) -> dict:
        return {
            "type": self.__class__.__name__,
            "message": self.message,
            "severity": self.severity.value,
            "details": self.details,
            "timestamp": self.timestamp.isoformat()
        }


class CriticalTradingError(CthulhuBaseException):
    """Critical error that must halt trading operations"""
    severity = ErrorSeverity.CRITICAL


class OrderExecutionError(CriticalTradingError):
    """Failed to execute an order"""
    pass


class PositionManagementError(CriticalTradingError):
    """Failed to manage a position (close, modify SL/TP)"""
    pass


class RiskViolationError(CriticalTradingError):
    """Risk limits violated"""
    pass


class RecoverableError(CthulhuBaseException):
    """Error that allows trading to continue with degraded functionality"""
    severity = ErrorSeverity.WARNING


class IndicatorError(RecoverableError):
    """Indicator calculation failed"""
    pass


class SignalError(RecoverableError):
    """Signal generation failed"""
    pass


class MetricsError(RecoverableError):
    """Metrics collection failed"""
    pass


class ConfigurationError(CthulhuBaseException):
    """Configuration is invalid or missing"""
    severity = ErrorSeverity.ERROR


class ConnectionError(CthulhuBaseException):
    """Connection to MT5 or external service failed"""
    severity = ErrorSeverity.ERROR


class MT5ConnectionError(ConnectionError):
    """Specifically MT5 connection issues"""
    pass


class DataError(CthulhuBaseException):
    """Invalid or missing market data"""
    severity = ErrorSeverity.WARNING


class DatabaseError(RecoverableError):
    """Database operation failed - non-critical"""
    pass


# Type variable for generic functions
T = TypeVar('T')


def handle_exception(
    exc: Exception,
    context: str = "",
    reraise: bool = False,
    default: Any = None,
    log_level: int = logging.ERROR
) -> Any:
    """
    Centralized exception handler that logs and optionally reraises.
    
    Args:
        exc: The caught exception
        context: Description of what was being attempted
        reraise: Whether to reraise the exception
        default: Default value to return if not reraising
        log_level: Logging level to use
    
    Returns:
        default value if not reraising
    
    Raises:
        The original exception if reraise=True
    """
    exc_type = type(exc).__name__
    exc_msg = str(exc)
    tb = traceback.format_exc()
    
    # Determine if this is a Cthulu exception
    if isinstance(exc, CthulhuBaseException):
        severity = exc.severity.value
        details = exc.details
    else:
        severity = "UNKNOWN"
        details = {}
    
    # Build log message
    log_msg = f"[{severity}] {context}: {exc_type}: {exc_msg}"
    if details:
        log_msg += f" | Details: {details}"
    
    # Log appropriately
    if log_level == logging.CRITICAL:
        logger.critical(log_msg)
        logger.critical(f"Traceback:\n{tb}")
    elif log_level == logging.ERROR:
        logger.error(log_msg)
        logger.debug(f"Traceback:\n{tb}")
    elif log_level == logging.WARNING:
        logger.warning(log_msg)
    else:
        logger.info(log_msg)
    
    if reraise:
        raise exc
    
    return default


def safe_execute(
    func: Callable[..., T],
    *args,
    default: T = None,
    context: str = "",
    on_error: Optional[Callable[[Exception], None]] = None,
    **kwargs
) -> T:
    """
    Execute a function safely, catching and logging exceptions.
    
    Args:
        func: Function to execute
        *args: Positional arguments
        default: Default return value on failure
        context: Description for logging
        on_error: Optional callback on error
        **kwargs: Keyword arguments
    
    Returns:
        Function result or default value
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        ctx = context or f"{func.__module__}.{func.__name__}"
        handle_exception(e, context=ctx, log_level=logging.WARNING)
        if on_error:
            try:
                on_error(e)
            except Exception:
                pass
        return default


def log_and_continue(context: str = "", default: Any = None, log_level: int = logging.WARNING):
    """
    Decorator that logs exceptions and continues with default value.
    
    Usage:
        @log_and_continue(context="Loading indicator", default=None)
        def load_indicator(name):
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                ctx = context or f"{func.__module__}.{func.__name__}"
                handle_exception(e, context=ctx, log_level=log_level)
                return default
        return wrapper
    return decorator


def critical_section(context: str = ""):
    """
    Decorator for critical sections that must not fail silently.
    Logs and reraises all exceptions.
    
    Usage:
        @critical_section(context="Order execution")
        def execute_order(order):
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            try:
                return func(*args, **kwargs)
            except CriticalTradingError:
                raise  # Already a critical error, just reraise
            except Exception as e:
                ctx = context or f"{func.__module__}.{func.__name__}"
                logger.critical(f"Critical section failure in {ctx}: {e}")
                logger.critical(traceback.format_exc())
                # Wrap in critical error
                raise CriticalTradingError(
                    f"Critical failure in {ctx}: {e}",
                    details={"original_error": str(e), "type": type(e).__name__}
                ) from e
        return wrapper
    return decorator


def retry_on_connection_error(max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """
    Decorator that retries on connection errors.
    
    Args:
        max_retries: Maximum retry attempts
        delay: Initial delay between retries (seconds)
        backoff: Multiplier for delay after each retry
    """
    import time
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_error = None
            current_delay = delay
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except (ConnectionError, MT5ConnectionError, OSError) as e:
                    last_error = e
                    if attempt < max_retries:
                        logger.warning(f"Connection error in {func.__name__}, retry {attempt + 1}/{max_retries} in {current_delay}s: {e}")
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(f"Connection error in {func.__name__} after {max_retries} retries: {e}")
                except Exception:
                    raise  # Non-connection errors are not retried
            
            raise last_error
        return wrapper
    return decorator


# Import guards with logging
def safe_import(module_name: str, fallback: Any = None, log: bool = True) -> Any:
    """
    Safely import a module, returning fallback on failure.
    
    Args:
        module_name: Full module path
        fallback: Value to return if import fails
        log: Whether to log import failures
    
    Returns:
        Imported module or fallback
    """
    try:
        import importlib
        return importlib.import_module(module_name)
    except ImportError as e:
        if log:
            logger.debug(f"Optional module {module_name} not available: {e}")
        return fallback
    except Exception as e:
        if log:
            logger.warning(f"Failed to import {module_name}: {e}")
        return fallback


def safe_import_from(module_name: str, attr_name: str, fallback: Any = None, log: bool = True) -> Any:
    """
    Safely import an attribute from a module.
    
    Args:
        module_name: Full module path
        attr_name: Attribute/class to import
        fallback: Value to return if import fails
        log: Whether to log import failures
    
    Returns:
        Imported attribute or fallback
    """
    try:
        import importlib
        module = importlib.import_module(module_name)
        return getattr(module, attr_name)
    except (ImportError, AttributeError) as e:
        if log:
            logger.debug(f"Optional {attr_name} from {module_name} not available: {e}")
        return fallback
    except Exception as e:
        if log:
            logger.warning(f"Failed to import {attr_name} from {module_name}: {e}")
        return fallback


# Database operation wrapper
def db_safe(default: Any = None, log_errors: bool = True):
    """
    Decorator for database operations that should not crash the system.
    
    Usage:
        @db_safe(default=None)
        def record_trade(self, trade):
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if log_errors:
                    logger.error(f"Database error in {func.__name__}: {e}")
                    logger.debug(traceback.format_exc())
                return default
        return wrapper
    return decorator
