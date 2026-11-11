"""Runtime helpers for Falcon correlation middleware.

This module owns context-variable management, the contextual logging filter
and formatter, and UUID generation and validation tooling for the correlation
middleware. Its key exports include ``correlation_id_var``, ``user_id_var``,
``CORRELATION_ID_RESET_TOKEN_ATTR``, ``ContextualLogFilter``,
``ContextualLogFormatter``, ``default_uuid7_generator``, and
``default_uuid_validator``.

Both ``middleware.py`` and ``middleware_config.py`` import this module, and it
does not import from either of them. That boundary keeps the shared runtime
helpers available without introducing circular imports.
"""

from __future__ import annotations

import contextvars
import importlib
import logging
import typing as typ
import uuid

from ._log_safety import copy_with_escaped_fields, field_conversions

if typ.TYPE_CHECKING:
    import collections.abc as cabc

correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)
"""Request-local correlation ID storage shared by middleware and integrations."""

user_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "user_id", default=None
)
"""Request-local user ID storage for applications that attach user context."""

CORRELATION_ID_RESET_TOKEN_ATTR = "_correlation_id_reset_token"  # ruff: ignore[hardcoded-password-string] - attribute-name string is not a secret
MISSING_CONTEXT_PLACEHOLDER: str = "-"

RECOMMENDED_LOG_FORMAT: str = (
    "%(asctime)s - [%(levelname)s] - [%(correlation_id)s] - "
    "[%(user_id)s] - %(name)s - %(message)s"
)
"""Logging format string including correlation and user ID placeholders.

Pair this format string with :class:`ContextualLogFormatter` rather than the
plain :class:`logging.Formatter`, so that correlation metadata cannot inject
control characters into plaintext log output.
"""


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

    The filter does not escape values. Correlation metadata can be supplied by
    a task producer and may contain control characters, so pair the filter with
    :class:`ContextualLogFormatter` for plaintext handlers.

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
        from falcon_correlate import (
            ContextualLogFilter,
            ContextualLogFormatter,
        )

        handler = logging.StreamHandler()
        handler.addFilter(ContextualLogFilter())
        handler.setFormatter(
            ContextualLogFormatter(
                "%(asctime)s [%(correlation_id)s] "
                "[%(user_id)s] %(message)s"
            )
        )

    Using the recommended format constant::

        import logging
        from falcon_correlate import (
            ContextualLogFilter,
            ContextualLogFormatter,
            RECOMMENDED_LOG_FORMAT,
        )

        handler = logging.StreamHandler()
        handler.addFilter(ContextualLogFilter())
        handler.setFormatter(
            ContextualLogFormatter(RECOMMENDED_LOG_FORMAT),
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
                    "class": "falcon_correlate.ContextualLogFormatter",
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

    def filter(  # ruff: ignore[no-self-use] - logging.Filter requires an instance method.
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


class ContextualLogFormatter(logging.Formatter):
    r"""Plaintext logging formatter that escapes correlation metadata.

    :class:`ContextualLogFilter` copies correlation metadata onto a
    ``LogRecord`` without escaping it, because the filter must preserve the
    original value for propagation. This formatter closes the rendering gap:
    before formatting, it escapes text held in the ``correlation_id`` and
    ``user_id`` attributes on a shallow copy of the record.

    Escaped forms are ``\r``, ``\n`` and ``\t`` for carriage return, line feed
    and tab; ``\xNN`` for other C0 controls, DEL and C1 controls; and
    ``\u2028``/``\u2029`` for the Unicode line and paragraph separators.
    Backslashes are doubled so an escaped value cannot be confused with the
    original. Printable text, including non-ASCII identifiers, is unchanged.
    The escape is applied to the rendering selected by the format string, not
    just to ``str(value)``. Text conversions render the escaped text, so a
    ``%r`` or ``%a`` conversion cannot carry control characters through a
    custom ``__repr__``. Numeric conversions only produce digits, signs, a
    decimal point, and exponent letters, so their values pass through
    untouched and specifications like ``%(user_id)d`` keep working.

    Percent (``%``) and template (``$``) styles are supported. The ``%c``
    conversion is rejected because it renders an integer as an arbitrary
    character, and brace (``{``) style is rejected because its format-spec
    language can render arbitrary text that the formatter cannot intercept.
    Other constructor arguments match :class:`logging.Formatter`: ``fmt``,
    ``datefmt``, ``validate`` and the keyword-only ``defaults`` argument all
    work.

    Notes
    -----
    The formatter expects records enriched by :class:`ContextualLogFilter`, or
    by a caller that sets ``correlation_id`` and ``user_id`` itself. Fields
    absent from the record stay absent, so a format string that references a
    missing field still raises the standard ``ValueError``.

    The original record is never modified: messages, timestamps, exception
    text, ``extra=`` metadata, defaults and context variables keep their raw
    values for other handlers and downstream propagation. Escaping belongs to
    this handler, not to the logging pipeline as a whole; a structured
    formatter such as JSON serializes the raw value instead.

    Examples
    --------
    >>> import logging
    >>> record = logging.LogRecord(
    ...     "demo", logging.INFO, __file__, 1, "started", (), None
    ... )
    >>> record.correlation_id = "abc\r\n2026-01-01 - [CRITICAL] - forged"
    >>> ContextualLogFormatter("%(correlation_id)s - %(message)s").format(record)
    'abc\\r\\n2026-01-01 - [CRITICAL] - forged - started'
    >>> record.correlation_id
    'abc\r\n2026-01-01 - [CRITICAL] - forged'

    """

    # pylint: disable-next=too-many-arguments  # Mirrors logging.Formatter.
    def __init__(  # ruff: ignore[too-many-arguments] - mirrors logging.Formatter
        self,
        fmt: str | None = None,
        datefmt: str | None = None,
        style: typ.Literal["%", "{", "$"] = "%",
        validate: bool = True,  # ruff: ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument] - mirrors logging.Formatter
        *,
        defaults: cabc.Mapping[str, object] | None = None,
    ) -> None:
        """Create a formatter that escapes correlation metadata.

        Parameters
        ----------
        fmt : str | None
            Format string, using the style selected by *style*.
        datefmt : str | None
            Date format passed to :class:`logging.Formatter`.
        style : Literal["%", "{", "$"]
            Either ``"%"`` for percent style or ``"$"`` for template style;
            ``"{"`` is accepted by the signature but rejected at construction.
        validate : bool
            Whether the format string is validated by the base class.
        defaults : collections.abc.Mapping[str, object] | None
            Default values for fields missing from the record.

        Raises
        ------
        ValueError
            If *style* requests brace formatting, or if the percent format
            string uses the ``%c`` conversion for a correlation metadata field.

        """  # ruff: ignore[docstring-extraneous-exception] - raised via field_conversions.
        super().__init__(
            fmt,
            datefmt,
            style,
            validate,
            defaults=defaults,
        )
        self._field_conversions = field_conversions(self._style, fmt)

    def format(self, record: logging.LogRecord) -> str:
        """Format *record*, escaping correlation metadata on a copy.

        Parameters
        ----------
        record : logging.LogRecord
            Record to format. When it carries ``correlation_id`` or
            ``user_id``, the escaped values are applied to a shallow copy so
            *record* itself is left unchanged.

        Returns
        -------
        str
            The formatted log line, with no control characters contributed by
            the correlation fields.

        """
        escaped_record = copy_with_escaped_fields(record, self._field_conversions)
        if escaped_record is None:
            return super().format(record)
        return super().format(escaped_record)


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
    """Return whether hyphens appear at standard UUID separator positions."""
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
