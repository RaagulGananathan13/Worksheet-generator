"""
Logging configuration for the Handwriting OCR application.

This module provides a centralized logging configuration with file and console handlers,
log rotation, colored output, and exception handling.
"""
import os
import sys
import time
import logging
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, Union, Dict, Any, Callable, TypeVar, cast

from app.config import BASE_DIR

# Type variable for generic function wrapping
F = TypeVar('F', bound=Callable[..., Any])

# Logging format with more detailed information
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()

# Log file paths and settings
LOG_DIR = BASE_DIR / 'logs'
LOG_FILE = LOG_DIR / 'app.log'
ERROR_LOG_FILE = LOG_DIR / 'error.log'
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 5

# Ensure log directory exists with proper error handling
try:
    LOG_DIR.mkdir(exist_ok=True, parents=True)
    # Test if directory is writable
    test_file = LOG_DIR / '.write_test'
    try:
        test_file.touch()
        test_file.unlink()
    except (IOError, PermissionError) as e:
        raise RuntimeError(f"Log directory '{LOG_DIR}' is not writable: {e}")
except (OSError, RuntimeError) as e:
    print(f"Warning: {e}", file=sys.stderr)
    # Fallback to system temp directory if we can't write to LOG_DIR
    import tempfile
    LOG_DIR = Path(tempfile.gettempdir()) / 'handwriting_ocr_logs'
    LOG_DIR.mkdir(exist_ok=True)
    LOG_FILE = LOG_DIR / 'app.log'
    ERROR_LOG_FILE = LOG_DIR / 'error.log'
    print(f"Logs will be written to: {LOG_DIR}", file=sys.stderr)

def get_logger(
    name: str, 
    log_level: Union[str, int, None] = None,
    log_to_file: bool = True,
    log_to_console: bool = True,
    propagate: bool = False
) -> logging.Logger:
    """Get a configured logger instance with file and console handlers.
    
    Args:
        name: Name of the logger (usually __name__)
        log_level: Logging level as string (DEBUG, INFO, etc.) or logging constant
        log_to_file: Whether to log to file
        log_to_console: Whether to log to console
        propagate: Whether to propagate logs to parent loggers
        
    Returns:
        Configured logger instance
    """
    # Create logger
    logger = logging.getLogger(name)
    
    # Set log level
    if isinstance(log_level, str):
        level = getattr(logging, log_level.upper(), logging.INFO)
    else:
        level = log_level or getattr(logging, LOG_LEVEL, logging.INFO)
    
    logger.setLevel(level)
    logger.propagate = propagate
    
    # Return existing logger if already configured
    if logger.handlers:
        return logger
    
    # Create formatters
    class ColoredFormatter(logging.Formatter):
        """Custom formatter that adds colors to log levels."""
        COLORS = {
            'DEBUG': '\033[36m',     # Cyan
            'INFO': '\033[32m',      # Green
            'WARNING': '\033[33m',   # Yellow
            'ERROR': '\033[31m',     # Red
            'CRITICAL': '\033[31;1m',# Bold Red
            'RESET': '\033[0m'       # Reset
        }
        
        def format(self, record):
            # Only add color if we're outputting to a terminal
            if sys.stdout.isatty():
                levelname = record.levelname
                if levelname in self.COLORS:
                    record.levelname = f"{self.COLORS[levelname]}{levelname}{self.COLORS['RESET']}"
                    record.name = f"\033[1m{record.name}{self.COLORS['RESET']}"
                    record.msg = f"{self.COLORS.get(levelname, '')}{record.msg}{self.COLORS['RESET']}"
            return super().format(record)
    
    # Create formatters
    file_formatter = logging.Formatter(LOG_FORMAT)
    console_formatter = ColoredFormatter(LOG_FORMAT)
    
    # Add console handler if enabled
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(console_formatter)
        console_handler.setLevel(level)
        logger.addHandler(console_handler)
    
    # Add file handlers if enabled
    if log_to_file:
        try:
            # Main log file handler (rotating)
            file_handler = RotatingFileHandler(
                LOG_FILE,
                maxBytes=LOG_MAX_BYTES,
                backupCount=LOG_BACKUP_COUNT,
                encoding='utf-8'
            )
            file_handler.setFormatter(file_formatter)
            file_handler.setLevel(level)
            logger.addHandler(file_handler)
            
            # Error log file handler (only errors)
            error_file_handler = RotatingFileHandler(
                ERROR_LOG_FILE,
                maxBytes=LOG_MAX_BYTES // 2,  # Smaller max size for error logs
                backupCount=3,
                encoding='utf-8'
            )
            error_file_handler.setFormatter(file_formatter)
            error_file_handler.setLevel(logging.ERROR)
            logger.addHandler(error_file_handler)
            
        except (IOError, PermissionError) as e:
            logger.error(f"Failed to set up file logging: {e}")
    
    # Add exception hook for unhandled exceptions
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
            
        logger.critical(
            "Uncaught exception",
            exc_info=(exc_type, exc_value, exc_traceback)
        )
    
    sys.excepthook = handle_exception
    
    return logger

# Configure root logger
root_logger = get_logger('handwriting_ocr')

def log_exceptions(logger=None, reraise: bool = True, default: Any = None):
    """Decorator to log exceptions raised by the decorated function.
    
    Args:
        logger: Logger instance to use (default: create one based on module name)
        reraise: Whether to re-raise the exception after logging
        default: Default value to return if an exception occurs and reraise is False
    
    Example:
        @log_exceptions()
        def risky_operation():
            # Code that might raise an exception
            pass
    """
    def decorator(func: F) -> F:
        nonlocal logger
        if logger is None:
            logger = get_logger(func.__module__)
            
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.exception(
                    f"Exception in {func.__qualname__}"
                )
                if reraise:
                    raise
                return default
                
        return cast(F, wrapper)
    return decorator


def log_execution_time(logger=None, level=logging.DEBUG):
    """Decorator to log the execution time of a function.
    
    Args:
        logger: Logger instance to use
        level: Logging level to use for the timing message
        
    Example:
        @log_execution_time()
        def slow_operation():
            # Time-consuming operation
            time.sleep(2)
    """
    def decorator(func: F) -> F:
        nonlocal logger
        if logger is None:
            logger = get_logger(func.__module__)
            
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                end_time = time.time()
                logger.log(
                    level,
                    f"{func.__qualname__} executed in {end_time - start_time:.4f} seconds"
                )
                
        return cast(F, wrapper)
    return decorator

class LoggingContext:
    """Context manager for logging with a specific context.
    
    This allows you to temporarily change the logging configuration
    within a specific context.
    
    Example:
        logger = get_logger(__name__)
        with LoggingContext(logger, level=logging.DEBUG):
            # Logging at DEBUG level here
            logger.debug("Debug message")
    """
    
    def __init__(
        self, 
        logger: logging.Logger, 
        level: Optional[int] = None, 
        handler: Optional[logging.Handler] = None, 
        close: bool = True
    ):
        """Initialize the logging context.
        
        Args:
            logger: The logger to configure
            level: Logging level to set temporarily
            handler: Logging handler to add temporarily
            close: Whether to close the handler when done
        """
        self.logger = logger
        self.level = level
        self.handler = handler
        self.close = close
        self.old_level = None
    
    def __enter__(self) -> None:
        """Enter the runtime context."""
        if self.level is not None:
            self.old_level = self.logger.level
            self.logger.setLevel(self.level)
        if self.handler:
            self.logger.addHandler(self.handler)
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the runtime context."""
        # Restore original log level if it was changed
        if self.level is not None and self.old_level is not None:
            self.logger.setLevel(self.old_level)
        
        # Remove the handler if one was added
        if self.handler:
            self.logger.removeHandler(self.handler)
            if self.close:
                self.handler.close()
        
        # Don't suppress any exceptions
        return False
