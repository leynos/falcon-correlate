"""Format-conversion handling for ``ContextualLogFormatter``.

The formatter must escape the rendering that the format string actually
selects, and reject conversions or styles whose output it cannot guarantee.
"""

from __future__ import annotations

import collections
import logging
import typing as typ

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


class _StatefulStr:
    """Object whose first ``str`` call is safe and whose second is hostile."""

    def __init__(self) -> None:
        """Start with no recorded ``str`` calls."""
        self.calls = 0

    def __str__(self) -> str:
        """Return safe text once, then forge an extra log line."""
        self.calls += 1
        return "safe" if self.calls == 1 else _HOSTILE_TEXT


class _StatefulRepr:
    """Object whose first ``repr`` call is safe and whose second is hostile."""

    def __init__(self) -> None:
        """Start with no recorded ``repr`` calls."""
        self.calls = 0

    def __repr__(self) -> str:
        """Return a safe representation once, then forge a log line."""
        self.calls += 1
        return "safe" if self.calls == 1 else _HOSTILE_TEXT


class _Unrenderable:
    """Object whose text form raises, like a broken metadata value."""

    def __str__(self) -> str:
        """Fail rather than produce text."""
        raise RuntimeError


@pytest.mark.parametrize("field", ["correlation_id", "user_id"])
def test_character_conversion_is_rejected(field: str) -> None:
    """``%c`` can render an integer as a raw line feed, so it is rejected."""
    with pytest.raises(ValueError, match=r"%c conversion"):
        ContextualLogFormatter(f"%({field})c|%(message)s")


@pytest.mark.parametrize("modifier", ["h", "l", "L"])
def test_character_conversion_with_length_modifier_is_rejected(
    modifier: str,
) -> None:
    """The ignored length modifiers do not hide a ``%c`` conversion."""
    with pytest.raises(ValueError, match=r"%c conversion"):
        ContextualLogFormatter(f"%(user_id){modifier}c|%(message)s")


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


def test_escaped_percent_placeholder_is_not_scanned() -> None:
    """A literal ``%%`` placeholder cannot select the later conversion."""
    record = _make_record(correlation_id=_HOSTILE_TEXT)

    output = ContextualLogFormatter("%%(correlation_id)r|%(correlation_id)s").format(
        record
    )

    _assert_single_safe_line(output)
    assert output.startswith("%(correlation_id)r|"), (
        f"expected the literal placeholder, got {output!r}"
    )


def test_escaped_character_placeholder_is_not_rejected() -> None:
    """A literal ``%%c`` placeholder is text, not a ``%c`` conversion."""
    formatter = ContextualLogFormatter("%%(user_id)c|%(message)s")

    output = formatter.format(_make_record(user_id=10))

    assert output == "%(user_id)c|handled request", (
        f"expected the literal placeholder, got {output!r}"
    )


def test_repeated_field_conversions_escape_every_occurrence() -> None:
    """Every occurrence of a repeated field sees escaped text."""
    record = _make_record(correlation_id=_HOSTILE_TEXT)

    output = ContextualLogFormatter("%(correlation_id)s|%(correlation_id)s").format(
        record
    )

    _assert_single_safe_line(output)
    assert output.count("abc\\r\\n") == 2, (
        f"expected escaped CRLF twice, got {output!r}"
    )


def test_mixed_text_and_numeric_conversions_are_rejected() -> None:
    """One field cannot be both escaped text and a numeric rendering."""
    with pytest.raises(ValueError, match="mix conversions"):
        ContextualLogFormatter("%(user_id)s|%(user_id)d")


def test_mixed_text_conversions_are_rejected() -> None:
    """``%s`` and ``%r`` render one field differently, so they cannot mix."""
    with pytest.raises(ValueError, match="mix conversions"):
        ContextualLogFormatter("%(user_id)s|%(user_id)r")


def test_numeric_conversion_mix_matches_plain_formatter() -> None:
    """Numeric conversions pass the value through and each applies itself."""
    record = _make_record(user_id=42)
    fmt = "%(user_id)d|%(user_id)x"

    actual = ContextualLogFormatter(fmt).format(record)
    expected = logging.Formatter(fmt).format(record)

    assert actual == expected, f"expected {expected!r}, got {actual!r}"


@pytest.mark.parametrize(
    ("fmt", "style"),
    [
        pytest.param("%(message)s", "%", id="percent"),
        pytest.param("$message", "$", id="template"),
    ],
)
def test_unused_field_is_not_rendered(
    fmt: str,
    style: typ.Literal["%", "$"],
) -> None:
    """A field the format does not use cannot break the record."""
    record = _make_record(user_id=_Unrenderable())

    output = ContextualLogFormatter(fmt, style=style).format(record)

    assert output == "handled request", f"expected the message, got {output!r}"


def test_stateful_string_rendering_is_checked_once() -> None:
    """The text that was checked is what ``%s`` emits."""
    value = _StatefulStr()
    record = _make_record(user_id=value)

    output = ContextualLogFormatter("%(user_id)s").format(record)

    _assert_single_safe_line(output)
    assert output == "safe", f"expected the checked text, got {output!r}"
    assert vars(record)["user_id"] is value, (
        f"expected the raw object to stay on the record, got {vars(record)!r}"
    )


def test_stateful_repr_rendering_is_checked_once() -> None:
    """The representation that was checked is what ``%r`` emits."""
    value = _StatefulRepr()
    record = _make_record(user_id=value)

    output = ContextualLogFormatter("%(user_id)r").format(record)

    _assert_single_safe_line(output)
    assert output == "safe", f"expected the checked text, got {output!r}"
    assert vars(record)["user_id"] is value, (
        f"expected the raw object to stay on the record, got {vars(record)!r}"
    )


def test_template_style_ignores_percent_like_text() -> None:
    """Template style escapes substitutions without scanning percent tokens."""
    record = _make_record(correlation_id=_HOSTILE_TEXT)

    output = ContextualLogFormatter(
        "%(correlation_id)r|$correlation_id", style="$"
    ).format(record)

    _assert_single_safe_line(output)
    assert "abc\\r\\n" in output, f"expected escaped CRLF, got {output!r}"


def test_template_field_boundary_follows_template_rules() -> None:
    """A non-ASCII letter after a field is literal, not part of its name."""
    record = _make_record(correlation_id=_HOSTILE_TEXT)

    output = ContextualLogFormatter("$correlation_id\u212a|$message", style="$").format(
        record
    )

    _assert_single_safe_line(output)
    assert output.endswith("\u212a|handled request"), (
        f"expected the literal Kelvin sign, got {output!r}"
    )


def test_escaped_template_dollar_is_not_a_field() -> None:
    """``$$`` is a literal dollar, so the following text is not a field."""
    record = _make_record(correlation_id=_HOSTILE_TEXT)

    output = ContextualLogFormatter("$$correlation_id|$message", style="$").format(
        record
    )

    assert output == "$correlation_id|handled request", (
        f"expected a literal dollar, got {output!r}"
    )


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
