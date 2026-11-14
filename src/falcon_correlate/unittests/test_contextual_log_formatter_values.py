"""Value-type handling for ``ContextualLogFormatter``.

The formatter must escape text that could forge a line without breaking
format specifications for values that carry no such risk.
"""

from __future__ import annotations

import logging

import pytest

from falcon_correlate import ContextualLogFormatter

_HOSTILE_CORRELATION_ID = "abc\r\n2026-01-01 - [CRITICAL] - [forged] - injected"
_FIELD_FORMAT = "%(correlation_id)s|%(user_id)s|%(message)s"


class _HostileText:
    """Object whose text form is a forged log line."""

    def __str__(self) -> str:
        """Return hostile metadata text."""
        return _HOSTILE_CORRELATION_ID


def _contains_control_character(value: str) -> bool:
    """Return whether *value* contains a control or line-separator character."""
    return any(
        ord(character) < 0x20
        or 0x7F <= ord(character) <= 0x9F
        or ord(character) in {0x2028, 0x2029}
        for character in value
    )


def _make_record() -> logging.LogRecord:
    """Create a log record for formatter tests."""
    return logging.LogRecord(
        "test.contextual_log_formatter.values",
        logging.INFO,
        __file__,
        1,
        "handled request",
        (),
        None,
    )


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("abc-123", id="ordinary"),
        pytest.param(None, id="explicit-none"),
        pytest.param("", id="empty-string"),
        pytest.param("café-ü", id="non-ascii"),
        pytest.param(12345, id="integer"),
        pytest.param(0, id="zero"),
        pytest.param(False, id="false"),
    ],
)
def test_safe_output_matches_plain_formatter_for_explicit_values(
    value: object,
) -> None:
    """Explicit record values keep the plain formatter's string rendering."""
    record = _make_record()
    record.correlation_id = value
    record.user_id = value

    actual = ContextualLogFormatter(_FIELD_FORMAT).format(record)
    expected = logging.Formatter(_FIELD_FORMAT).format(record)

    assert actual == expected, f"expected {expected!r}, got {actual!r}"


@pytest.mark.parametrize("field", ["correlation_id", "user_id"])
def test_numeric_metadata_keeps_numeric_format_specifications(field: str) -> None:
    """Non-text metadata passes through so numeric conversions still work."""
    record = _make_record()
    setattr(record, field, 42)

    actual = ContextualLogFormatter(f"%({field})d").format(record)
    expected = logging.Formatter(f"%({field})d").format(record)

    assert actual == expected, f"expected {expected!r}, got {actual!r}"
    assert vars(record)[field] == 42, f"expected 42, got {vars(record)[field]!r}"


@pytest.mark.parametrize("field", ["correlation_id", "user_id"])
def test_object_text_is_escaped_at_the_output_boundary(field: str) -> None:
    """A non-text value with hostile text cannot forge an extra log line."""
    record = _make_record()
    hostile = _HostileText()
    setattr(record, field, hostile)

    output = ContextualLogFormatter(f"%({field})s").format(record)

    lines = output.splitlines()
    assert len(lines) == 1, f"expected one log line, got {lines!r}"
    assert not _contains_control_character(lines[0]), (
        f"expected no raw control characters, got {lines[0]!r}"
    )
    expected = _HOSTILE_CORRELATION_ID.replace("\r", "\\r").replace("\n", "\\n")
    assert output == expected, f"expected {expected!r}, got {output!r}"
    assert vars(record)[field] is hostile, (
        f"expected the raw object to stay on the record, got {vars(record)[field]!r}"
    )
