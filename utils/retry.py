"""
Retry utilities with exponential backoff.
"""

import time
import logging
from typing import Callable, TypeVar, Optional, Type, Tuple

T = TypeVar('T')

logger = logging.getLogger(__name__)


def exponential_backoff(
    func: Callable[..., T],
    max_retries: int = 5,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[int, Exception], None]] = None
) -> Optional[T]:
    """
    Execute function with exponential backoff retry.
    
    Args:
        func: Function to execute
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        exponential_base: Base for exponential backoff calculation
        exceptions: Tuple of exception types to catch and retry
        on_retry: Optional callback function called on each retry
        
    Returns:
        Result from func or None if all retries failed
        
    Example:
        result = exponential_backoff(
            lambda: risky_api_call(),
            max_retries=3,
            initial_delay=1.0
        )
    """
    delay = initial_delay
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            result = func()
            if attempt > 0:
                logger.info(f"Operation succeeded after {attempt} retries")
            return result
            
        except exceptions as e:
            last_exception = e
            
            if attempt == max_retries - 1:
                logger.error(f"Operation failed after {max_retries} attempts: {e}")
                raise
            
            # Call retry callback if provided
            if on_retry:
                on_retry(attempt + 1, e)
            
            # Calculate next delay with exponential backoff
            current_delay = min(delay, max_delay)
            logger.warning(
                f"Retry {attempt + 1}/{max_retries} after {current_delay:.1f}s delay. Error: {e}"
            )
            
            time.sleep(current_delay)
            delay *= exponential_base
    
    return None


class RetryConfig:
    """Configuration for retry behavior."""
    
    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 30.0,
        exponential_base: float = 2.0
    ):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base


def with_retry(config: RetryConfig):
    """
    Decorator for adding retry logic to functions.
    
    Usage:
        retry_config = RetryConfig(max_retries=3)
        
        @with_retry(retry_config)
        def my_function():
            # function implementation
            pass
    """
    def decorator(func: Callable[..., T]) -> Callable[..., Optional[T]]:
        def wrapper(*args, **kwargs) -> Optional[T]:
            return exponential_backoff(
                lambda: func(*args, **kwargs),
                max_retries=config.max_retries,
                initial_delay=config.initial_delay,
                max_delay=config.max_delay,
                exponential_base=config.exponential_base
            )
        return wrapper
    return decorator




