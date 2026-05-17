"""Runtime helpers for Falcon correlation middleware.

This module owns context-variable management, the contextual logging filter,
and UUID generation and validation tooling for the correlation middleware. Its
key exports include ``correlation_id_var``, ``user_id_var``,
``CORRELATION_ID_RESET_TOKEN_ATTR``, ``ContextualLogFilter``,
``default_uuid7_generator``, and ``default_uuid_validator``.

Both ``middleware.py`` and ``middleware_config.py`` import this module, and it
does not import from either of them. That boundary keeps the shared runtime
helpers available without introducing circular imports.
"""

from __future__ import annotations

import contextvars
import importlib
import logging
import uuid

correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)
user_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "user_id", default=None
)
CORRELATION_ID_RESET_TOKEN_ATTR = "_correlation_id_reset_token"  # noqa: S105 - attribute-name string is not a secret
MISSING_CONTEXT_PLACEHOLDER: str = "-"

RECOMMENDED_LOG_FORMAT: str = (
    "%(asctime)s - [%(levelname)s] - [%(correlation_id)s] - "
    "[%(user_id)s] - %(name)s - %(message)s"
)


class ContextualLogFilter(logging.Filter):
    """Logging filter that injects correlation and user IDs into log records.

    This filter reads ``correlation_id_var`` and ``user_id_var`` and copies
    their values onto the ``LogRecord`` as ``correlation_id`` and ``user_id``
    attributes.  When a context variable is not set, the placeholder ``"-"``
    is used.

    Attributes already present on the record (e.g. attached via
    ``extra=`` or a ``LoggerAdapter``) are preserved; the filter only
    fills in missing attributes, never overwrites existing ones.

    The filter never suppresses records; it always returns ``True``.

    The library provides a recommended format string as the constant
    ``RECOMMENDED_LOG_FORMAT``::

        from falcon_correlate import RECOMMENDED_LOG_FORMAT

        # Value:
        # "%(asctime)s - [%(levelname)s] - [%(correlation_id)s] - "
        # "[%(user_id)s] - %(name)s - %(message)s"

    Examples
    --------
    Attach to a handler::

        import logging
        from falcon_correlate import ContextualLogFilter

        handler = logging.StreamHandler()
        handler.addFilter(ContextualLogFilter())
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(correlation_id)s] "
                "[%(user_id)s] %(message)s"
            )
        )

    Using the recommended format constant::

        import logging
        from falcon_correlate import (
            ContextualLogFilter,
            RECOMMENDED_LOG_FORMAT,
        )

        handler = logging.StreamHandler()
        handler.addFilter(ContextualLogFilter())
        handler.setFormatter(
            logging.Formatter(RECOMMENDED_LOG_FORMAT),
        )

    Configure via ``logging.config.dictConfig``::

        import logging.config
        from falcon_correlate import RECOMMENDED_LOG_FORMAT

        LOGGING_CONFIG = {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {
                "contextual": {
                    "()": "falcon_correlate.ContextualLogFilter",
                },
            },
            "formatters": {
                "standard": {
                    "format": RECOMMENDED_LOG_FORMAT,
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "standard",
                    "filters": ["contextual"],
                },
            },
            "root": {
                "handlers": ["console"],
                "level": "INFO",
            },
        }

        logging.config.dictConfig(LOGGING_CONFIG)

    """

    def filter(  # noqa: PLR6301 - logging.Filter requires an instance method.
        self, record: logging.LogRecord
    ) -> bool:
        """Enrich *record* with correlation ID and user ID attributes.

        Attributes already present on the record (e.g. set via
        ``extra=`` or a ``LoggerAdapter``) are preserved.  Context
        variable values are only applied when the record does not
        already carry the attribute, avoiding accidental clobbering
        of explicit caller-provided metadata.

        Parameters
        ----------
        record : logging.LogRecord
            The log record to enrich.

        Returns
        -------
        bool
            Always ``True`` — this filter enriches records but never
            suppresses them.

        """
        if not hasattr(record, "correlation_id"):
            cid = correlation_id_var.get()
            record.correlation_id = (
                cid if cid is not None else MISSING_CONTEXT_PLACEHOLDER
            )
        if not hasattr(record, "user_id"):
            uid = user_id_var.get()
            record.user_id = uid if uid is not None else MISSING_CONTEXT_PLACEHOLDER
        return True


def default_uuid7_generator() -> str:
    """Generate a UUIDv7 correlation ID.

    Uses the standard library ``uuid.uuid7()`` when available and falls back
    to ``uuid_utils.uuid7()`` when the runtime lacks ``uuid.uuid7()``.

    Returns
    -------
    str
        A UUIDv7 hex string representation.

    """
    uuid7 = getattr(uuid, "uuid7", None)
    if uuid7 is not None:
        return uuid7().hex

    uuid_utils = importlib.import_module("uuid_utils")
    return uuid_utils.uuid7().hex


# Maximum length for a valid UUID string (hyphenated format: 8-4-4-4-12)
_MAX_UUID_LENGTH = 36
# Minimum length for a valid UUID string (hex-only format: 32 characters)
_MIN_UUID_LENGTH = 32
# Expected hyphen positions in 8-4-4-4-12 format (indices 8, 13, 18, 23)
_HYPHEN_POSITIONS = frozenset({8, 13, 18, 23})
# Valid UUID versions per RFC 4122 and RFC 9562
_VALID_UUID_VERSIONS = frozenset({1, 2, 3, 4, 5, 6, 7, 8})


def _has_valid_hyphen_placement(value: str) -> bool:
    """Check that hyphens appear exactly at UUID separator positions."""
    for i, char in enumerate(value):
        if char == "-":
            if i not in _HYPHEN_POSITIONS:
                return False
        elif i in _HYPHEN_POSITIONS:
            # Expected a hyphen but found a different character
            return False
    return True


def default_uuid_validator(value: str) -> bool:
    """Validate that a string is a valid UUID (versions 1-8).

    Accepts both hyphenated (8-4-4-4-12) and hex-only (32-character) UUID
    formats. Case-insensitive. Rejects UUIDs with non-standard version nibbles.
    Enforces strict hyphen placement at positions 8, 13, 18, and 23 for
    36-character inputs.

    Parameters
    ----------
    value : str
        The string to validate.

    Returns
    -------
    bool
        ``True`` if the value is a valid UUID (version 1-8), ``False`` otherwise.

    Examples
    --------
    >>> default_uuid_validator("550e8400-e29b-41d4-a716-446655440000")
    True
    >>> default_uuid_validator("550e8400e29b41d4a716446655440000")
    True
    >>> default_uuid_validator("not-a-uuid")
    False

    """
    # Early exit for empty strings
    if not value:
        return False

    # Early exit for out-of-range length strings
    length = len(value)
    if length > _MAX_UUID_LENGTH or length < _MIN_UUID_LENGTH:
        return False

    # Reject strings in the 33-35 character "gap" (neither hex-only nor valid
    # hyphenated format)
    if _MIN_UUID_LENGTH < length < _MAX_UUID_LENGTH:
        return False

    # For 36-character strings, enforce strict 8-4-4-4-12 hyphen placement
    if length == _MAX_UUID_LENGTH and not _has_valid_hyphen_placement(value):
        return False

    try:
        parsed = uuid.UUID(value)
    except ValueError:
        return False
    # Enforce valid UUID version (1-8)
    return parsed.version in _VALID_UUID_VERSIONS
