"""Shared helpers for contextual log filter tests.

Classes
-------
HasCorrelationID
    Describe records with a correlation ID.
HasUserID
    Describe records with a user ID.
HasContextIDs
    Describe records with both context IDs.

Functions
---------
make_log_record
    Create a minimal log record for filter tests.
"""

from __future__ import annotations

import logging
import typing as typ


class HasCorrelationID(typ.Protocol):
    """Protocol for objects exposing a ``correlation_id`` attribute."""

    correlation_id: str


class HasUserID(typ.Protocol):
    """Protocol for objects exposing a ``user_id`` attribute."""

    user_id: str


class HasContextIDs(HasCorrelationID, HasUserID, typ.Protocol):
    """LogRecord enriched by ContextualLogFilter with both IDs."""


def make_log_record(msg: str = "test message") -> logging.LogRecord:
    """Create a minimal LogRecord for testing."""
    return logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg=msg,
        args=None,
        exc_info=None,
    )
