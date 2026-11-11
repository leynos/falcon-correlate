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
# whose output is safe by construction because numeric conversions cannot emit
# control characters. ``%c`` is absent deliberately: it renders an integer as
# an arbitrary character and is rejected. ``%%`` is a literal percent sign, so
# it must be consumed before a placeholder is looked for inside it, and the
# legacy ``h``/``l``/``L`` length modifiers are ignored by Python but still
# select the conversion that follows them.
_PERCENT_TOKEN_RE = re.compile(
    r"%%|%\((?P<field>correlation_id|user_id)\)"
    r"[#0+ -]*(?:\*|\d+)?(?:\.(?:\*|\d+))?"
    r"(?P<conversion>[hlL]?[diouxXeEfFgGcrsa])"
)

# The token grammar used by ``string.Template``. Only identifiers that name a
# correlation field matter, and ``$$`` is an escaped dollar, not a field.
_TEMPLATE_TOKEN_RE = re.compile(
    r"\$(?:(?P<escaped>\$)|(?P<named>[_a-z][_a-z0-9]*)|\{(?P<braced>[_a-z][_a-z0-9]*)\})",
    re.IGNORECASE,
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

    @classmethod
    def for_mixed_conversions(cls, field: str) -> UnsafeLogFormatError:
        """Create an error for conversions of *field* that render differently."""
        return cls(
            f"{field} cannot mix conversions that render it differently; "
            "use one conversion per field"
        )


def field_conversions(style: object, fmt: str | None) -> dict[str, str]:
    """Return the percent conversion used for each correlation metadata field."""
    # ``StrFormatStyle`` and ``StringTemplateStyle`` both subclass
    # ``PercentStyle``, so the more specific styles must be matched first.
    match style:
        case logging.StrFormatStyle():
            raise UnsafeLogFormatError.for_brace_style()
        case logging.StringTemplateStyle():
            return _template_fields(fmt)
        case logging.PercentStyle():
            return _percent_conversions(fmt)
        case _:
            return {}


def _template_fields(fmt: str | None) -> dict[str, str]:
    """Return the correlation fields that a template-style format uses."""
    used = {
        found["named"] or found["braced"]
        for found in _TEMPLATE_TOKEN_RE.finditer(fmt or "")
    }
    return {name: "s" for name in LOG_FIELD_NAMES if name in used}


def _percent_conversions(fmt: str | None) -> dict[str, str]:
    """Return the percent conversions used for correlation metadata fields."""
    conversions: dict[str, str] = {}
    for found in _PERCENT_TOKEN_RE.finditer(fmt or ""):
        field = found["field"]
        if field is None:
            continue
        conversion = found["conversion"][-1]
        if conversion == "c":
            raise UnsafeLogFormatError.for_character_conversion(field)
        conversions[field] = _combine_conversions(
            field, conversions.get(field), conversion
        )
    return conversions


def _combine_conversions(
    field: str,
    existing: str | None,
    conversion: str,
) -> str:
    """Return the safe rendering shared by every occurrence of *field*."""
    if existing is None or existing == conversion:
        return conversion
    # Numeric conversions pass the original value through, so each placeholder
    # applies its own conversion. Text and representation conversions replace
    # the value with a single rendering, so different renderings are rejected.
    if {existing, conversion} <= _NUMERIC_CONVERSIONS:
        return existing
    raise UnsafeLogFormatError.for_mixed_conversions(field)


class _EscapedRepr(str):  # ruff: ignore[subclass-builtin] - controls ``%r`` output.
    """Escaped representation that a ``%r`` conversion emits verbatim."""

    def __repr__(self) -> str:
        """Return the escaped representation without quotation marks."""
        return str.__str__(self)


def escape_log_field(value: object, conversion: str) -> object:
    """Escape the rendering that *conversion* selects for a log field."""
    # Text conversions render ``str(value)`` (``%s`` and template style) or
    # ``repr(value)``/``ascii(value)``. Numeric conversions cannot emit control
    # characters, so their values are left untouched and keep working with
    # specifications such as ``%d``.
    if conversion in _REPR_CONVERSIONS:
        # ``repr`` of an exact string always escapes line boundaries, so it is
        # safe and stays byte-identical to the stock formatter. Any other
        # object may override ``__repr__``, so the rendered representation is
        # escaped and returned as a value whose own ``repr`` is that text. That
        # also avoids calling a stateful ``__repr__`` a second time during the
        # format operation.
        if type(value) is str:
            return value
        text = repr(value) if conversion == "r" else ascii(value)
        return _EscapedRepr(text.translate(_TRANSLATION_TABLE))
    if conversion in _NUMERIC_CONVERSIONS:
        return value
    # ``%s`` and template substitutions render ``str(value)``, including any
    # subclass override. Return the checked text so a stateful ``__str__`` is
    # not called a second time with different output.
    return str(value).translate(_TRANSLATION_TABLE)


def copy_with_escaped_fields(
    record: logging.LogRecord,
    conversions: dict[str, str],
) -> logging.LogRecord | None:
    """Return a copy of *record* with escaped correlation fields, if any."""
    # Only fields the format string renders are escaped: an unused field is
    # left alone, so an object whose ``__str__`` raises cannot break a record
    # that the stock formatter would emit.
    present_fields = [
        name
        for name in LOG_FIELD_NAMES
        if name in conversions and hasattr(record, name)
    ]
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
