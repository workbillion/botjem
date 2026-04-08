"""
LOGGER SETUP
=============
Colored console + file logging
"""

import logging
import os
from datetime import datetime


class ColorFormatter(logging.Formatter):
    """Colored terminal output"""
    
    COLORS = {
        "DEBUG":    "\033[36m",   # Cyan
        "INFO":     "\033[97m",   # White
        "WARNING":  "\033[33m",   # Yellow
        "ERROR":    "\033[31m",   # Red
        "CRITICAL": "\033[1;31m", # Bold Red
    }
    RESET = "\033[0m"
    
    # Emoji untuk specific messages
    EMOJI_MAP = {
        "💰": "\033[92m",  # Green
        "💸": "\033[91m",  # Red
        "🎯": "\033[93m",  # Yellow
        "✅": "\033[92m",  # Green
        "❌": "\033[91m",  # Red
        "🚀": "\033[95m",  # Magenta
        "🛑": "\033[91m",  # Red bold
        "⚡": "\033[93m",  # Yellow
    }

    def format(self, record):
        color = self.COLORS.get(record.levelname, self.RESET)
        
        # Check for emoji untuk override color
        msg = str(record.getMessage())
        for emoji, emoji_color in self.EMOJI_MAP.items():
            if emoji in msg:
                color = emoji_color
                break
        
        formatter = logging.Formatter(
            f"{color}%(asctime)s [%(name)s] %(message)s{self.RESET}",
            datefmt="%H:%M:%S"
        )
        return formatter.format(record)


def setup_logger(name: str, log_file: str = None) -> logging.Logger:
    """Setup logger dengan console + file handler"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    
    if logger.handlers:
        return logger
    
    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(ColorFormatter())
    logger.addHandler(ch)
    
    # File handler
    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(
            "%(asctime)s [%(name)s] [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        logger.addHandler(fh)
    
    return logger
