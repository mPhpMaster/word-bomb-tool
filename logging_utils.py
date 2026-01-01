# logging_utils.py - Logging utilities and setup

import logging
import logging.handlers
import sys
import io
from datetime import datetime
from config import LOG_FILE, LOG_FORMAT, LOG_LEVEL

def setup_logging():
    """Setup logging configuration with proper encoding."""
    logger = logging.getLogger()
    logger.setLevel(LOG_LEVEL)
    
    # File handler with UTF-8 encoding
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=5*1024*1024,  # 5MB
        backupCount=3,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(LOG_FORMAT)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    # Console handler with error handling for Unicode
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(LOG_FORMAT)
    console_handler.setFormatter(console_formatter)
    
    # Force UTF-8 encoding on console (Windows fix)
    if sys.platform == 'win32':
        # Reconfigure stdout for UTF-8
        if hasattr(sys.stdout, 'reconfigure'):
            try:
                sys.stdout.reconfigure(encoding='utf-8')
            except:
                pass
    
    logger.addHandler(console_handler)
    
    return logger

class LogQueue:
    """Thread-safe log message queue for UI display."""
    
    def __init__(self, max_size: int = 500):
        self.queue = []
        self.max_size = max_size
        self.lock = __import__('threading').Lock()
    
    def add(self, message: str, level: str = "INFO"):
        """
        Add message to queue.
        
        Args:
            message: Message text
            level: Log level (INFO, WARNING, ERROR)
        """
        from config import THEME
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Choose color based on level
        if level == "ERROR":
            color = THEME["error"]
        elif level == "WARNING":
            color = THEME["warning"]
        else:
            color = THEME["log_fg"]
        
        formatted_msg = f"[{timestamp}] {message}"
        
        with self.lock:
            self.queue.append((formatted_msg, color))
            if len(self.queue) > self.max_size:
                self.queue.pop(0)
    
    def pop_all(self) -> list:
        """Get and clear all messages."""
        with self.lock:
            messages = self.queue.copy()
            self.queue.clear()
            return messages
    
    def has_messages(self) -> bool:
        """Check if queue has messages."""
        with self.lock:
            return len(self.queue) > 0