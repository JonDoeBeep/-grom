"""
Centralized logging for the bot.
No more monkey-patching debug_log across modules.
"""

import logging
from datetime import datetime


# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
    datefmt='%H:%M:%S'
)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for a module."""
    return logging.getLogger(name)


def set_debug_mode(enabled: bool):
    """Enable or disable debug logging globally."""
    level = logging.DEBUG if enabled else logging.INFO
    logging.getLogger().setLevel(level)


# Convenience function for modules that were using debug_log
def debug_log(message: str, level: str = "INFO", logger_name: str = "bot"):
    """
    Legacy-compatible debug logging function.
    Prefer using get_logger() for new code.
    """
    logger = get_logger(logger_name)
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARN": logging.WARNING,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
    }
    log_level = level_map.get(level.upper(), logging.INFO)
    logger.log(log_level, message)
