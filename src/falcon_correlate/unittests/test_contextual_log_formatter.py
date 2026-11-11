"""Unit tests for ``ContextualLogFormatter`` safe plaintext rendering.

The formatter is the output boundary that stops correlation metadata from
fabricating log records, while leaving the raw values available for
propagation.
"""

from __future__ import annotations

import io
import logging
import logging.config
import sys
import typing as typ

import pytest

from falcon_correlate import (
    RECOMMENDED_LOG_FORMAT,
    ContextualLogFilter,
    ContextualLogFormatter,
    correlation_id_var,
    user_id_var,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import types


_HOSTILE_CORRELATION_ID = "abc\r\n2026-01-01 - [CRITICAL] - [forged] - injected"
_FIELD_FORMAT = "%(correlation_id)s|%(user_id)s|%(message)s"
_ESCAPE_CASES = [
    pytest.param("\n", "\\n", id="lf"),
    pytest.param("\r", "\\r", id="cr"),
    pytest.param("\r\n", "\\r\\n", id="crlf"),
    pytest.param("\t", "\\t", id="tab"),
    pytest.param("\x00", "\\x00", id="nul"),
    pytest.param("\x1b[31m", "\\x1b[31m", id="ansi-escape"),
    pytest.param("\x7f", "\\x7f", id="del"),
    pytest.param("\x85", "\\x85", id="c1-nel"),
    pytest.param("\u2028", "\\u2028", id="line-separator"),
    pytest.param("\u2029", "\\u2029", id="paragraph-separator"),
    pytest.param("\\", "\\\\", id="backslash"),
]


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


def _make_record(
    *,
    msg: str = "handled request",
    exc_info: tuple[type[BaseException], BaseException, types.TracebackType]
    | None = None,
) -> logging.LogRecord:
    """Create a log record for formatter tests."""
    return logging.LogRecord(
        "test.contextual_log_formatter",
        logging.INFO,
        __file__,
        1,
        msg,
        (),
        exc_info,
    )


def _enriched_record(
    correlation_id: str | None,
    user_id: str | None,
) -> logging.LogRecord:
    """Filter a fresh record using context values, then restore the context."""
    record = _make_record()
    cid_token = correlation_id_var.set(correlation_id)
    uid_token = user_id_var.set(user_id)
    try:
        ContextualLogFilter().filter(record)
    finally:
        user_id_var.reset(uid_token)
        correlation_id_var.reset(cid_token)
    return record


@pytest.fixture
def safe_logger() -> cabc.Generator[tuple[logging.Logger, io.StringIO], None, None]:
    """Yield a logger whose handler uses the safe formatter and the filter."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(ContextualLogFormatter(RECOMMENDED_LOG_FORMAT))
    handler.addFilter(ContextualLogFilter())

    test_logger = logging.getLogger("test.contextual_log_formatter.emit")
    original_propagate = test_logger.propagate
    test_logger.addHandler(handler)
    test_logger.setLevel(logging.INFO)
    test_logger.propagate = False

    yield test_logger, stream

    test_logger.removeHandler(handler)
    handler.close()
    test_logger.propagate = original_propagate


@pytest.mark.parametrize("field", ["correlation_id", "user_id"])
@pytest.mark.parametrize(("payload", "escaped"), _ESCAPE_CASES)
def test_formatter_escapes_control_characters(
    field: str,
    payload: str,
    escaped: str,
) -> None:
    """Each control character renders as its documented escape form."""
    record = _make_record()
    setattr(record, field, f"prefix{payload}suffix")

    output = ContextualLogFormatter(f"%({field})s").format(record)

    assert output == f"prefix{escaped}suffix", (
        f"expected prefix{escaped}suffix, got {output!r}"
    )
    assert not _contains_control_character(output), (
        f"expected no raw control characters, got {output!r}"
    )
    assert len(output.splitlines()) == 1, (
        f"expected one log line, got {output.splitlines()!r}"
    )


@pytest.mark.parametrize(
    ("correlation_id", "user_id"),
    [
        pytest.param("abc-123", "user-456", id="ordinary"),
        pytest.param(None, None, id="missing-context-placeholder"),
        pytest.param("", "", id="empty-context"),
        pytest.param("café-ü", "üser-42", id="non-ascii"),
    ],
)
def test_safe_output_matches_plain_formatter_for_context_values(
    correlation_id: str | None,
    user_id: str | None,
) -> None:
    """Safe rendering is byte-identical for values that need no escaping."""
    record = _enriched_record(correlation_id, user_id)

    actual = ContextualLogFormatter(_FIELD_FORMAT).format(record)
    expected = logging.Formatter(_FIELD_FORMAT).format(record)

    assert actual == expected, f"expected {expected!r}, got {actual!r}"


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


def test_extra_metadata_is_escaped_when_emitted_through_a_logger(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    safe_logger: tuple[logging.Logger, io.StringIO],
) -> None:
    """Caller-supplied ``extra=`` metadata is escaped at the output boundary."""
    test_logger, stream = safe_logger

    def _logic() -> None:
        """Emit one record carrying hostile explicit metadata."""
        test_logger.info(
            "handled request",
            extra={
                "correlation_id": _HOSTILE_CORRELATION_ID,
                "user_id": "uid\nforged",
            },
        )

    isolated_context(_logic)

    output = stream.getvalue()
    _assert_single_safe_line(output)
    assert "abc\\r\\n" in output, f"expected escaped CRLF, got {output!r}"
    assert "uid\\nforged" in output, f"expected escaped LF, got {output!r}"


def test_formatting_preserves_original_record_and_context_variables() -> None:
    """Escaping happens on a copy, and repeated renders are stable."""
    hostile = _HOSTILE_CORRELATION_ID
    record = _make_record()
    record.correlation_id = hostile
    record.user_id = "user-1"
    formatter = ContextualLogFormatter(_FIELD_FORMAT)

    cid_token = correlation_id_var.set(hostile)
    try:
        first = formatter.format(record)
        second = formatter.format(record)
        context_value = correlation_id_var.get()
    finally:
        correlation_id_var.reset(cid_token)

    assert vars(record)["correlation_id"] is hostile, (
        f"expected {hostile!r}, got {vars(record)['correlation_id']!r}"
    )
    assert vars(record)["user_id"] == "user-1", (
        f"expected 'user-1', got {vars(record)['user_id']!r}"
    )
    assert context_value is hostile, (
        f"expected context value {hostile!r}, got {context_value!r}"
    )
    assert correlation_id_var.get() is None, (
        f"expected the context variable to reset, got {correlation_id_var.get()!r}"
    )
    assert first == second, f"expected stable renders, got {first!r} and {second!r}"
    assert not _contains_control_character(first), (
        f"expected no raw control characters, got {first!r}"
    )


def test_plain_and_safe_handlers_receive_one_unsafe_record(
    safe_logger: tuple[logging.Logger, io.StringIO],
) -> None:
    """A plain handler still sees the raw value held by the same record."""
    test_logger, safe_stream = safe_logger
    raw_stream = io.StringIO()
    raw_handler = logging.StreamHandler(raw_stream)
    raw_handler.setFormatter(logging.Formatter("%(correlation_id)s"))
    test_logger.addHandler(raw_handler)

    try:
        test_logger.info(
            "handled request",
            extra={"correlation_id": _HOSTILE_CORRELATION_ID},
        )
    finally:
        test_logger.removeHandler(raw_handler)
        raw_handler.close()

    raw_output = raw_stream.getvalue()
    safe_output = safe_stream.getvalue()
    assert raw_output == f"{_HOSTILE_CORRELATION_ID}\n", (
        f"expected the plain handler to see the raw value, got {raw_output!r}"
    )
    _assert_single_safe_line(safe_output)
    assert "abc\\r\\n" in safe_output, f"expected escaped CRLF, got {safe_output!r}"


def _raise_value_error() -> None:
    """Raise a ``ValueError`` for traceback rendering."""
    raise ValueError("boom")


def test_traceback_is_rendered_without_mutating_the_original_record() -> None:
    """Exception text is added to the copy, not cached on the raw record."""
    try:
        _raise_value_error()
    except ValueError:
        exc_info = sys.exc_info()

    record = _make_record(exc_info=typ.cast("tuple", exc_info))
    record.correlation_id = _HOSTILE_CORRELATION_ID

    output = ContextualLogFormatter("%(correlation_id)s %(message)s").format(record)

    first_line, *traceback_lines = output.splitlines()
    assert first_line.endswith("handled request"), (
        f"expected the escaped prefix on the first line, got {first_line!r}"
    )
    assert "abc\\r\\n" in first_line, f"expected escaped CRLF, got {first_line!r}"
    assert traceback_lines[0] == "Traceback (most recent call last):", (
        f"expected a rendered traceback, got {traceback_lines[0]!r}"
    )
    assert traceback_lines[-1] == "ValueError: boom", (
        f"expected the exception summary, got {traceback_lines[-1]!r}"
    )
    assert record.exc_text is None, (
        f"expected exc_text to stay unset, got {record.exc_text!r}"
    )
    assert vars(record)["correlation_id"] == _HOSTILE_CORRELATION_ID, (
        f"expected the raw correlation ID, got {vars(record)['correlation_id']!r}"
    )


def test_dict_config_uses_the_safe_formatter_class() -> None:
    """``dictConfig`` resolves the formatter through its dotted class path."""
    logger_name = "test.contextual_log_formatter.dictconfig"
    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "contextual": {
                "()": "falcon_correlate.ContextualLogFilter",
            },
        },
        "formatters": {
            "safe": {
                "class": "falcon_correlate.ContextualLogFormatter",
                "format": RECOMMENDED_LOG_FORMAT,
            },
        },
        "handlers": {
            "capture": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "safe",
                "filters": ["contextual"],
            },
        },
        "loggers": {
            logger_name: {
                "handlers": ["capture"],
                "level": "INFO",
                "propagate": False,
            },
        },
    })
    test_logger = logging.getLogger(logger_name)
    stream = io.StringIO()
    for handler in test_logger.handlers:
        if isinstance(handler, logging.StreamHandler):
            handler.stream = stream

    try:
        token = correlation_id_var.set(_HOSTILE_CORRELATION_ID)
        try:
            test_logger.info("handled request")
        finally:
            correlation_id_var.reset(token)
        output = stream.getvalue()
    finally:
        for handler in list(test_logger.handlers):
            test_logger.removeHandler(handler)

    _assert_single_safe_line(output)
    assert "abc\\r\\n" in output, f"expected escaped CRLF, got {output!r}"
    assert test_logger.handlers == [], (
        f"expected no handlers left attached, got {test_logger.handlers!r}"
    )
