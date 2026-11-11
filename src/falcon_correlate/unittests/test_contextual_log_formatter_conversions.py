"""Format-conversion handling for ``ContextualLogFormatter``.

The formatter must escape the rendering that the format string actually
selects, and reject conversions or styles whose output it cannot guarantee.
"""

from __future__ import annotations

import collections
import logging

import pytest

from falcon_correlate import ContextualLogFormatter

_HOSTILE_TEXT = "abc\r\n2026-01-01 - [CRITICAL] - [forged] - injected"


def _make_record(**fields: object) -> logging.LogRecord:
    """Create a log record carrying explicit correlation metadata."""
    record = logging.LogRecord(
        "test.contextual_log_formatter.conversions",
        logging.INFO,
        __file__,
        1,
        "handled request",
        (),
        None,
    )
    for name, value in fields.items():
        setattr(record, name, value)
    return record


def _contains_control_character(value: str) -> bool:
    """Return whether *value* contains a control or line-separator character."""
    return any(
        ord(character) < 0x20
        or 0x7F <= ord(character) <= 0x9F
        or ord(character) in {0x2028, 0x2029}
        for character in value
    )


def _assert_single_safe_line(output: str) -> None:
    """Assert *output* holds one line with no raw control characters."""
    lines = output.splitlines()
    assert len(lines) == 1, f"expected one log line, got {lines!r}"
    assert not _contains_control_character(lines[0]), (
        f"expected no raw control characters, got {lines[0]!r}"
    )


class _HostileRepr:
    """Object whose string form is safe but whose representation is hostile."""

    def __str__(self) -> str:
        """Return a safe text form."""
        return "safe-text"

    def __repr__(self) -> str:
        """Return metadata that would forge an extra log line."""
        return _HOSTILE_TEXT


class _HostileStr(collections.UserString):
    """String-like value whose ``str`` rendering is hostile."""

    def __str__(self) -> str:
        """Return metadata that would forge an extra log line."""
        return _HOSTILE_TEXT


@pytest.mark.parametrize("field", ["correlation_id", "user_id"])
def test_character_conversion_is_rejected(field: str) -> None:
    """``%c`` can render an integer as a raw line feed, so it is rejected."""
    with pytest.raises(ValueError, match=r"%c conversion"):
        ContextualLogFormatter(f"%({field})c|%(message)s")


def test_brace_style_is_rejected_including_character_specs() -> None:
    """Brace format specifications can render arbitrary text, so they fail."""
    with pytest.raises(ValueError, match="brace-style"):
        ContextualLogFormatter("{user_id:c}|{message}", style="{")


@pytest.mark.parametrize("field", ["correlation_id", "user_id"])
@pytest.mark.parametrize("conversion", ["r", "a"])
def test_repr_conversions_escape_hostile_representations(
    field: str,
    conversion: str,
) -> None:
    """``%r`` and ``%a`` escape a custom representation that forges a line."""
    hostile = _HostileRepr()
    record = _make_record(**{field: hostile})

    output = ContextualLogFormatter(f"%({field}){conversion}").format(record)

    _assert_single_safe_line(output)
    assert "abc" in output, f"expected the metadata text, got {output!r}"
    assert vars(record)[field] is hostile, (
        f"expected the raw object to stay on the record, got {vars(record)[field]!r}"
    )


@pytest.mark.parametrize("conversion", ["s", "r", "a"])
def test_text_conversions_match_plain_formatter_for_safe_values(
    conversion: str,
) -> None:
    """Safe values render byte-identically to the stock formatter."""
    record = _make_record(correlation_id="abc-123")
    fmt = f"%(correlation_id){conversion}"

    actual = ContextualLogFormatter(fmt).format(record)
    expected = logging.Formatter(fmt).format(record)

    assert actual == expected, f"expected {expected!r}, got {actual!r}"


def test_string_subclass_override_is_escaped() -> None:
    """``%s`` escapes the rendering supplied by a ``str`` subclass."""
    record = _make_record(user_id=_HostileStr("safe-content"))

    output = ContextualLogFormatter("%(user_id)s").format(record)

    _assert_single_safe_line(output)
    expected = _HOSTILE_TEXT.replace("\r", "\\r").replace("\n", "\\n")
    assert output == expected, f"expected {expected!r}, got {output!r}"


def test_template_style_escapes_metadata() -> None:
    """Template-style substitutions are escaped like ``%s`` conversions."""
    record = _make_record(correlation_id=_HOSTILE_TEXT)

    output = ContextualLogFormatter("$correlation_id|$message", style="$").format(
        record
    )

    _assert_single_safe_line(output)
    assert "abc\\r\\n" in output, f"expected escaped CRLF, got {output!r}"


@pytest.mark.parametrize("conversion", ["d", "x"])
def test_numeric_conversions_keep_non_text_values(conversion: str) -> None:
    """Numeric conversions still render integers like the stock formatter."""
    record = _make_record(user_id=42)
    fmt = f"%(user_id){conversion}"

    actual = ContextualLogFormatter(fmt).format(record)
    expected = logging.Formatter(fmt).format(record)

    assert actual == expected, f"expected {expected!r}, got {actual!r}"
