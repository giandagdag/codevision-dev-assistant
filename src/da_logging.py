"""Shared logger helper for the Developer Assistant."""

import logging

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def get_logger(name: str) -> logging.Logger:
    """Return a logger that writes one line per message to the console."""
    logger = logging.getLogger(name)
    # Only attach a handler the first time, otherwise every message would print twice.
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
