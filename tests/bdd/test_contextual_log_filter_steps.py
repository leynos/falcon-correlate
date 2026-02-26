"""Step definitions for contextual_log_filter.feature."""

from __future__ import annotations

import io
import logging
import logging.config
import typing as typ

import pytest

if typ.TYPE_CHECKING:
    import contextvars
from pytest_bdd import given, parsers, scenarios, then, when

from falcon_correlate import (
    RECOMMENDED_LOG_FORMAT,
    ContextualLogFilter,
    correlation_id_var,
    user_id_var,
)

scenarios("contextual_log_filter.feature")


class Context(typ.TypedDict, total=False):
    """Type definition for test context."""

    log_filter: ContextualLogFilter
    record: logging.LogRecord
    result: bool
    logger: logging.Logger
    stream: io.StringIO
    correlation_id_token: contextvars.Token[str | None]
    user_id_token: contextvars.Token[str | None]


def _make_log_record(msg: str = "test message") -> logging.LogRecord:
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


@pytest.fixture(autouse=True)
def _reset_context_variables() -> typ.Generator[None, None, None]:
    """Reset context variables after each scenario to prevent leakage."""
    yield
    # Reset to defaults — both variables default to None.
    correlation_id_var.set(None)
    user_id_var.set(None)


@given("a contextual log filter", target_fixture="context")
def given_contextual_log_filter() -> Context:
    """Create a contextual log filter instance."""
    return {"log_filter": ContextualLogFilter()}


@given(
    "a logger configured with the contextual log filter",
    target_fixture="context",
)
def given_logger_with_filter(request: pytest.FixtureRequest) -> Context:
    """Create a logger with the contextual log filter attached."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(
        logging.Formatter("[%(correlation_id)s][%(user_id)s] %(message)s")
    )
    log_filter = ContextualLogFilter()
    handler.addFilter(log_filter)

    test_logger = logging.getLogger("bdd_contextual_log_filter_test")
    test_logger.addHandler(handler)
    test_logger.setLevel(logging.INFO)

    # Remove the handler at teardown to prevent accumulation across scenarios.
    request.addfinalizer(lambda: test_logger.removeHandler(handler))

    return {
        "log_filter": log_filter,
        "logger": test_logger,
        "stream": stream,
    }


@given(
    parsers.parse('the correlation ID is set to "{value}"'),
    target_fixture="context",
)
def given_correlation_id_set(context: Context, value: str) -> Context:
    """Set the correlation ID context variable."""
    context["correlation_id_token"] = correlation_id_var.set(value)
    return context


@given(
    parsers.parse('the user ID is set to "{value}"'),
    target_fixture="context",
)
def given_user_id_set(context: Context, value: str) -> Context:
    """Set the user ID context variable."""
    context["user_id_token"] = user_id_var.set(value)
    return context


@given("no context variables are set")
def given_no_context_variables_set() -> None:
    """Ensure no context variables are set (default state)."""
    # Context variables default to None; nothing to do.


@when("the filter processes a log record", target_fixture="context")
def when_filter_processes_record(context: Context) -> Context:
    """Pass a log record through the filter."""
    record = _make_log_record()
    context["result"] = context["log_filter"].filter(record)
    context["record"] = record
    return context


@when(
    parsers.parse('a log message "{message}" is emitted'),
    target_fixture="context",
)
def when_log_message_emitted(context: Context, message: str) -> Context:
    """Emit a log message through the configured logger."""
    context["logger"].info(message)
    return context


@then(parsers.parse('the log record should have correlation_id "{expected}"'))
def then_record_has_correlation_id(context: Context, expected: str) -> None:
    """Verify the log record has the expected correlation_id."""
    actual = context["record"].correlation_id  # type: ignore[attr-defined]
    assert actual == expected, f"expected correlation_id {expected!r}, got {actual!r}"


@then(parsers.parse('the log record should have user_id "{expected}"'))
def then_record_has_user_id(context: Context, expected: str) -> None:
    """Verify the log record has the expected user_id."""
    actual = context["record"].user_id  # type: ignore[attr-defined]
    assert actual == expected, f"expected user_id {expected!r}, got {actual!r}"


@then(parsers.parse('the formatted output should contain "{expected}"'))
def then_output_contains(context: Context, expected: str) -> None:
    """Verify the formatted log output contains the expected string."""
    output = context["stream"].getvalue()
    assert expected in output, (
        f"formatted output did not contain {expected!r}: {output!r}"
    )


@given(
    "a logger configured with the recommended log format",
    target_fixture="context",
)
def given_logger_with_recommended_format(
    request: pytest.FixtureRequest,
) -> Context:
    """Create a logger using RECOMMENDED_LOG_FORMAT."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(
        logging.Formatter(RECOMMENDED_LOG_FORMAT),
    )
    handler.addFilter(ContextualLogFilter())

    test_logger = logging.getLogger(
        "bdd_recommended_log_format_test",
    )
    test_logger.addHandler(handler)
    test_logger.setLevel(logging.INFO)

    request.addfinalizer(
        lambda: test_logger.removeHandler(handler),
    )

    return {
        "logger": test_logger,
        "stream": stream,
    }


@given(
    "a logger configured via dictConfig with the recommended format",
    target_fixture="context",
)
def given_logger_via_dictconfig_with_recommended_format(
    request: pytest.FixtureRequest,
) -> Context:
    """Create a logger via dictConfig using RECOMMENDED_LOG_FORMAT."""
    logger_name = "bdd_recommended_dictconfig_test"
    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "contextual": {
                "()": "falcon_correlate.ContextualLogFilter",
            },
        },
        "formatters": {
            "recommended": {
                "format": RECOMMENDED_LOG_FORMAT,
            },
        },
        "handlers": {
            "bdd_stream": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "recommended",
                "filters": ["contextual"],
            },
        },
        "loggers": {
            logger_name: {
                "handlers": ["bdd_stream"],
                "level": "INFO",
            },
        },
    }
    logging.config.dictConfig(config)
    test_logger = logging.getLogger(logger_name)

    stream = io.StringIO()
    for h in test_logger.handlers:
        if isinstance(h, logging.StreamHandler):
            h.stream = stream

    def _cleanup() -> None:
        for h in list(test_logger.handlers):
            test_logger.removeHandler(h)

    request.addfinalizer(_cleanup)

    return {
        "logger": test_logger,
        "stream": stream,
    }
