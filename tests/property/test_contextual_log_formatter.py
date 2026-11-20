"""Property tests for safe plaintext rendering of correlation metadata."""

from __future__ import annotations

import logging
import re

from hypothesis import given
from hypothesis import strategies as st

from falcon_correlate import ContextualLogFormatter

_UNSAFE_SOURCE = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029\\]")
_CONTROL_CHARACTER = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]")
_SHORT_ESCAPES = {"\\": "\\\\", "\r": "\\r", "\n": "\\n", "\t": "\\t"}
_SAFE_TEXT = st.text(
    alphabet=st.characters(blacklist_categories=("Cc", "Cs", "Zl", "Zp"))
)


def _reference_escape(value: str) -> str:
    """Return the documented escape form for *value* using simple rules."""
    escaped: list[str] = []
    for character in value:
        if character in _SHORT_ESCAPES:
            escaped.append(_SHORT_ESCAPES[character])
            continue
        code = ord(character)
        if code < 0x20 or 0x7F <= code <= 0x9F:
            escaped.append(f"\\x{code:02x}")
        elif code in {0x2028, 0x2029}:
            escaped.append(f"\\u{code:04x}")
        else:
            escaped.append(character)
    return "".join(escaped)


@given(correlation_id=st.text(), user_id=st.text(), message=_SAFE_TEXT)
def test_escaped_fields_stay_on_one_line(
    correlation_id: str,
    user_id: str,
    message: str,
) -> None:
    """Any correlation text renders as one line of printable characters."""
    record = logging.LogRecord(
        "test.property",
        logging.INFO,
        __file__,
        1,
        message,
        (),
        None,
    )
    record.correlation_id = correlation_id
    record.user_id = user_id

    output = ContextualLogFormatter(
        "%(correlation_id)s|%(user_id)s|%(message)s"
    ).format(record)

    expected = (
        f"{_reference_escape(correlation_id)}|{_reference_escape(user_id)}|{message}"
    )
    assert output == expected, f"expected {expected!r}, got {output!r}"
    assert len(output.splitlines()) == 1, (
        f"expected one log line, got {output.splitlines()!r}"
    )
    assert not _CONTROL_CHARACTER.search(output), (
        f"expected no raw control characters, got {output!r}"
    )

    field_output = ContextualLogFormatter("%(correlation_id)s").format(record)
    if not _UNSAFE_SOURCE.search(correlation_id):
        assert field_output == correlation_id, (
            f"expected unchanged safe text {correlation_id!r}, got {field_output!r}"
        )
