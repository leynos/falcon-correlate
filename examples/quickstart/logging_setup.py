"""Logging setup from the quickstart guide.

This module shows how a Falcon application can add correlation context to
standard-library log records. `configure_logging()` creates a small isolated
logger with `ContextualLogFilter` and `RECOMMENDED_LOG_FORMAT` attached, and
`log_request()` demonstrates using that logger from request-handling code.
"""

from __future__ import annotations

import logging

from falcon_correlate import RECOMMENDED_LOG_FORMAT, ContextualLogFilter


# [quickstart:logging-config]
def configure_logging() -> logging.Logger:
    """Create a logger that includes correlation context.

    Returns
    -------
    logging.Logger
        Logger named ``quickstart`` with one stream handler, the recommended
        formatter, and the contextual logging filter attached.

    Notes
    -----
    The example clears existing handlers on the named logger so repeated
    quickstart runs do not duplicate output.

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

    Parameters
    ----------
    logger : logging.Logger
        Logger returned by ``configure_logging()``.

    Returns
    -------
    None
        The function emits a log record for its side effect.

    Examples
    --------
    >>> logger = configure_logging()
    >>> log_request(logger)
    """
    return logger.info("handled request")


# [/quickstart:logging-usage]
