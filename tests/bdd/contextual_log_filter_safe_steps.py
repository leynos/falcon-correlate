"""Safe-formatter step definitions for contextual_log_filter.feature.

These steps drive a ``dictConfig`` logger through ``ContextualLogFormatter`` so
the plaintext escaping contract stays separate from the filter-only steps in
``test_contextual_log_filter_steps``.
"""

from __future__ import annotations

import io
import logging
import logging.config
import typing as typ

from pytest_bdd import given, then

if typ.TYPE_CHECKING:
    import pytest

    from tests.bdd.test_contextual_log_filter_steps import Context

from falcon_correlate import RECOMMENDED_LOG_FORMAT, correlation_id_var

_HOSTILE_CORRELATION_ID = (
    "abc\r\n2026-01-01 - [CRITICAL] - [forged] - forged - injected"
)


@given(
    "a logger configured via dictConfig with the safe formatter",
    target_fixture="context",
)
def given_logger_via_dictconfig_with_safe_formatter(
    request: pytest.FixtureRequest,
) -> Context:
    """Create a logger via dictConfig using ``ContextualLogFormatter``.

    Parameters
    ----------
    request : pytest.FixtureRequest
        Pytest fixture used to remove configured handlers during teardown.

    Returns
    -------
    Context
        The value produced for the test scenario.

    """
    logger_name = "bdd_safe_dictconfig_test"
    config = {
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
            "bdd_safe_stream": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "safe",
                "filters": ["contextual"],
            },
        },
        "loggers": {
            logger_name: {
                "handlers": ["bdd_safe_stream"],
                "level": "INFO",
                "propagate": False,
            },
        },
    }
    logging.config.dictConfig(config)
    test_logger = logging.getLogger(logger_name)

    stream = io.StringIO()
    for handler in test_logger.handlers:
        if isinstance(handler, logging.StreamHandler):
            handler.stream = stream

    def _cleanup() -> None:
        """Detach all handlers from the test logger."""
        for handler in list(test_logger.handlers):
            test_logger.removeHandler(handler)

    request.addfinalizer(_cleanup)

    return {
        "logger": test_logger,
        "stream": stream,
    }


@given(
    "the correlation ID is set to a value with a line break",
    target_fixture="context",
)
def given_correlation_id_with_line_break(context: Context) -> Context:
    """Bind a CRLF-bearing correlation ID and retain its reset token.

    Parameters
    ----------
    context : Context
        Scenario context mapping to update with the context-variable token.

    Returns
    -------
    Context
        The value produced for the test scenario.

    """
    context["correlation_id_token"] = correlation_id_var.set(_HOSTILE_CORRELATION_ID)
    return context


@then("the formatted output should be a single escaped line")
def then_output_is_single_escaped_line(context: Context) -> None:
    """Verify hostile correlation metadata stays on one escaped line."""
    lines = context["stream"].getvalue().splitlines()
    assert len(lines) == 1, f"expected one log line, got {lines!r}"
    assert "abc\\r\\n2026-01-01" in lines[0], (
        f"expected escaped CRLF in the log line, got {lines[0]!r}"
    )
    assert not any(
        ord(character) < 0x20 or 0x7F <= ord(character) <= 0x9F
        for character in lines[0]
    ), f"expected no raw control characters, got {lines[0]!r}"
