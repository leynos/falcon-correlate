"""Rendering rules that keep correlation metadata out of log lines.

``ContextualLogFormatter`` uses this module to escape ``correlation_id`` and
``user_id`` at the output boundary. The rules live here so the formatter module
stays within the repository's file-size budget and the translation table has a
single owner.
"""

from __future__ import annotations

import copy
import logging
import re

LOG_FIELD_NAMES: tuple[str, ...] = ("correlation_id", "user_id")

# Values arrive from task producers and remote callers, so every character that
# can start a new line in ``str.splitlines()`` must be escaped. The mapping is
# built once: generic ``\xNN`` forms first, then the readable short forms and
# the two Unicode separators override their generic entries.
_LOG_FIELD_ESCAPES: dict[int, str] = {
    **{code: f"\\x{code:02x}" for code in (*range(0x20), 0x7F, *range(0x80, 0xA0))},
    ord("\\"): "\\\\",
    ord("\r"): "\\r",
    ord("\n"): "\\n",
    ord("\t"): "\\t",
    0x2028: "\\u2028",
    0x2029: "\\u2029",
}
_TRANSLATION_TABLE = str.maketrans(_LOG_FIELD_ESCAPES)

# Percent-style conversions whose output must be escaped explicitly, and those
# whose output is safe by construction because it can only contain digits,
# signs, a decimal point, and exponent letters. ``%c`` is absent deliberately:
# it renders an integer as an arbitrary character and is rejected.
_PERCENT_FIELD_RE = re.compile(
    r"%\((?P<field>correlation_id|user_id)\)"
    r"[#0+ -]*(?:\*|\d+)?(?:\.(?:\*|\d+))?"
    r"(?P<conversion>[diouxXeEfFgGcrsa])"
)
_REPR_CONVERSIONS = frozenset("ra")
_NUMERIC_CONVERSIONS = frozenset("diouxXeEfFgG")


class UnsafeLogFormatError(ValueError):
    """Raised when a format string cannot render correlation metadata safely."""

    @classmethod
    def for_brace_style(cls) -> UnsafeLogFormatError:
        """Create an error for an unsupported brace-style format string."""
        return cls(
            "ContextualLogFormatter does not support brace-style format "
            "strings; use percent or template style"
        )

    @classmethod
    def for_character_conversion(cls, field: str) -> UnsafeLogFormatError:
        """Create an error for a ``%c`` conversion applied to *field*."""
        return cls(
            f"the %c conversion cannot safely render {field}; "
            "escape the value explicitly or use %s"
        )


def field_conversions(style: object, fmt: str | None) -> dict[str, str]:
    """Return the percent conversion used for each correlation metadata field."""
    match style:
        case logging.StrFormatStyle():
            raise UnsafeLogFormatError.for_brace_style()
        case logging.PercentStyle():
            return _percent_conversions(fmt)
        case _:
            return {}


def _percent_conversions(fmt: str | None) -> dict[str, str]:
    """Return the percent conversions used for correlation metadata fields."""
    conversions: dict[str, str] = {}
    for found in _PERCENT_FIELD_RE.finditer(fmt or ""):
        field = found["field"]
        conversion = found["conversion"]
        if conversion == "c":
            raise UnsafeLogFormatError.for_character_conversion(field)
        conversions.setdefault(field, conversion)
    return conversions


def escape_log_field(value: object, conversion: str) -> object:
    """Escape the rendering that *conversion* selects for a log field."""
    # Text conversions render ``str(value)`` (``%s`` and template style) or
    # ``repr(value)``/``ascii(value)``. Numeric conversions only ever produce
    # digits, signs, a decimal point, and exponent letters, so their values are
    # left untouched and keep working with specifications such as ``%d``.
    if conversion in _REPR_CONVERSIONS:
        # ``repr`` of an exact string always escapes line boundaries, so its
        # output is safe and stays byte-identical to the stock formatter. A
        # subclass or other object may override ``__repr__``, so its rendered
        # representation is escaped instead.
        if type(value) is str:
            return value
        text = repr(value) if conversion == "r" else ascii(value)
        escaped = text.translate(_TRANSLATION_TABLE)
        return escaped if escaped != text else value
    if conversion in _NUMERIC_CONVERSIONS:
        return value
    # ``%s`` and template substitutions render ``str(value)``, including any
    # subclass override, so escape exactly that rendering.
    text = str(value)
    escaped = text.translate(_TRANSLATION_TABLE)
    return escaped if escaped != text else value


def copy_with_escaped_fields(
    record: logging.LogRecord,
    conversions: dict[str, str],
) -> logging.LogRecord | None:
    """Return a copy of *record* with escaped correlation fields, if any."""
    present_fields = [name for name in LOG_FIELD_NAMES if hasattr(record, name)]
    if not present_fields:
        return None

    escaped_record = copy.copy(record)
    for name in present_fields:
        setattr(
            escaped_record,
            name,
            escape_log_field(getattr(record, name), conversions.get(name, "s")),
        )
    return escaped_record
