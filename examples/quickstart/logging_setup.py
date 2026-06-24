"""Logging setup from the quickstart guide."""

from __future__ import annotations

import logging

from falcon_correlate import RECOMMENDED_LOG_FORMAT, ContextualLogFilter


# [quickstart:logging-config]
def configure_logging() -> logging.Logger:
    """Create a logger that includes correlation context.

    Examples
    --------
    >>> logger = configure_logging()
    >>> logger.name
    'quickstart'
    """
    logger = logging.getLogger("quickstart")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(RECOMMENDED_LOG_FORMAT))
    handler.addFilter(ContextualLogFilter())
    logger.addHandler(handler)
    return logger


# [/quickstart:logging-config]


# [quickstart:logging-usage]
def log_request(logger: logging.Logger) -> None:
    """Log one example request event.

    Examples
    --------
    >>> logger = configure_logging()
    >>> log_request(logger)
    """
    logger.info("handled request")


# [/quickstart:logging-usage]
