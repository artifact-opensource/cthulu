"""
Logging Module

Structured logging configuration with color support.
JSON format for production, human-readable with colors for development.
"""

import logging
import sys
import os
from typing import Optional
from pathlib import Path


# ANSI color codes for terminal output (works on Unix/Linux/Mac and Windows 10+)
class LogColors:
    """ANSI color codes for log levels."""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    
    # Level colors
    DEBUG = '\033[36m'      # Cyan
    INFO = '\033[32m'       # Green
    WARNING = '\033[33m'    # Yellow
    ERROR = '\033[31m'      # Red
    CRITICAL = '\033[35m'   # Magenta
    
    # Accent colors for special log types
    SIGNAL = '\033[94m'     # Bright Blue
    POSITION = '\033[96m'   # Bright Cyan
    TRADE = '\033[92m'      # Bright Green


class ColoredFormatter(logging.Formatter):
    """Custom formatter with color support."""
    
    # Level name to color mapping
    COLORS = {
        'DEBUG': LogColors.DEBUG,
        'INFO': LogColors.INFO,
        'WARNING': LogColors.WARNING,
        'ERROR': LogColors.ERROR,
        'CRITICAL': LogColors.CRITICAL,
    }
    
    def __init__(self, fmt: str, datefmt: str, use_colors: bool = True):
        """
        Initialize colored formatter.
        
        Args:
            fmt: Format string
            datefmt: Date format string
            use_colors: Whether to use colors (auto-detected for terminal)
        """
        super().__init__(fmt, datefmt)
        self.use_colors = use_colors and self._supports_color()
    
    def _supports_color(self) -> bool:
        """Check if terminal supports colors."""
        # Check if stdout is a terminal
        if not hasattr(sys.stdout, 'isatty'):
            return False
        if not sys.stdout.isatty():
            return False
        
        # Windows: Check for ANSI support (Windows 10+)
        if os.name == 'nt':
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                # Constants for Windows console
                STD_OUTPUT_HANDLE = -11
                ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
                
                # Enable ANSI escape sequences
                handle = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
                mode = ctypes.c_ulong()
                kernel32.GetConsoleMode(handle, ctypes.byref(mode))
                mode.value |= ENABLE_VIRTUAL_TERMINAL_PROCESSING
                kernel32.SetConsoleMode(handle, mode)
                return True
            except Exception:
                return False
        
        # Unix/Linux/Mac: Usually supported
        return True
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record with colors."""
        if self.use_colors:
            # Add color to level name
            levelname = record.levelname
            if levelname in self.COLORS:
                record.levelname = f"{self.COLORS[levelname]}{levelname}{LogColors.RESET}"
        
        # Format the message
        result = super().format(record)
        
        return result


def setup_logger(
    name: str = "Cthulu",
    level: "str|int" = "INFO",
    log_file: Optional[str] = None,
    json_format: bool = False,
    use_colors: bool = True
) -> logging.Logger:
    """
    Configure structured logger with color support.
    
    Args:
        name: Logger name
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional file path for logs
        json_format: Use JSON format (for production, disables colors)
        use_colors: Use color output (auto-detected for terminal)
        
    Returns:
        Configured logger
    """
    logger = logging.getLogger(name)
    # Support both integer and string levels
    if isinstance(level, int):
        level_value = level
    else:
        level_value = getattr(logging, str(level).upper(), logging.INFO)

    logger.setLevel(level_value)
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level_value)
    
    if json_format:
        # JSON format for production (no colors)
        formatter = logging.Formatter(
            '{"timestamp":"%(asctime)s","level":"%(levelname)s","name":"%(name)s","message":"%(message)s"}',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    else:
        # Compact human-readable format with colors
        # Format: 16:45:32 [INFO] Message
        format_str = '%(asctime)s [%(levelname)s] %(message)s'
        datefmt = '%H:%M:%S'  # Compact time only (no date in every line)
        
        formatter = ColoredFormatter(format_str, datefmt, use_colors=use_colors)
    
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler (optional) - no colors in file
    if log_file:
        log_path = Path(log_file)
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)  # Log everything to file
            
            # File formatter: full timestamp, no colors
            file_formatter = logging.Formatter(
                '%(asctime)s [%(levelname)s] %(name)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
        except PermissionError as e:
            # Cannot write to specified log location; attempt to fallback to per-user logs
            console_handler.emit(logging.LogRecord(name, logging.WARNING, __file__, 0,
                                                  f"Could not open log file '{log_file}' for writing: {e}", None, None))
            try:
                fallback_base = Path(os.getenv('LOCALAPPDATA') or Path.home()) / 'cthulu' / 'logs'
                fallback_base.mkdir(parents=True, exist_ok=True)
                fallback_log = fallback_base / Path(log_file).name
                file_handler = logging.FileHandler(str(fallback_log), encoding='utf-8')
                file_handler.setLevel(logging.DEBUG)
                
                file_formatter = logging.Formatter(
                    '%(asctime)s [%(levelname)s] %(name)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S'
                )
                file_handler.setFormatter(file_formatter)
                logger.addHandler(file_handler)
                console_handler.emit(logging.LogRecord(name, logging.INFO, __file__, 0,
                                                      f"Switched log file to user-local path: {fallback_log}", None, None))
            except Exception as e2:
                console_handler.emit(logging.LogRecord(name, logging.WARNING, __file__, 0,
                                                      f"Fallback log init failed: {e2}", None, None))
        except Exception as e:
            # Other unexpected errors while setting up file logging
            console_handler.emit(logging.LogRecord(name, logging.WARNING, __file__, 0,
                                                  f"Failed to initialize file logging for '{log_file}': {e}", None, None))
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get existing logger.
    
    Args:
        name: Logger name
        
    Returns:
        Logger instance
    """
    return logging.getLogger(name)




