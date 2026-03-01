"""Step definitions for structlog_integration.feature."""

from __future__ import annotations

import typing as typ

import pytest

structlog = pytest.importorskip("structlog")

if typ.TYPE_CHECKING:
    import contextvars

from pytest_bdd import given, parsers, scenarios, then, when  # noqa: E402

from falcon_correlate import correlation_id_var, user_id_var  # noqa: E402
from falcon_correlate.unittests.test_structlog_integration import (  # noqa: E402
    inject_correlation_context,
)

scenarios("structlog_integration.feature")


class Context(typ.TypedDict, total=False):
    """Type definition for test context."""

    captured_events: list[dict[str, object]]
    correlation_id_token: contextvars.Token[str | None]
    user_id_token: contextvars.Token[str | None]


@pytest.fixture(autouse=True)
def _reset_context_variables() -> typ.Generator[None, None, None]:
    """Reset context variables before and after each scenario."""
    correlation_id_var.set(None)
    user_id_var.set(None)
    yield
    correlation_id_var.set(None)
    user_id_var.set(None)


@pytest.fixture(autouse=True)
def _reset_structlog() -> typ.Generator[None, None, None]:
    """Reset structlog configuration before and after each scenario."""
    structlog.contextvars.clear_contextvars()
    structlog.reset_defaults()
    yield
    structlog.contextvars.clear_contextvars()
    structlog.reset_defaults()


@given(
    "structlog is configured with the correlation context processor",
    target_fixture="context",
)
def given_structlog_configured() -> Context:
    """Configure structlog with the correlation context processor."""
    captured: list[dict[str, object]] = []

    def _capture(
        logger: object,
        method_name: str,
        event_dict: dict[str, object],
    ) -> dict[str, object]:
        captured.append(dict(event_dict))
        raise structlog.DropEvent

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            inject_correlation_context,
            _capture,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(0),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )

    return {"captured_events": captured}


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
    correlation_id_var.set(None)
    user_id_var.set(None)
    structlog.contextvars.clear_contextvars()


@when(
    parsers.parse('a structlog message "{message}" is emitted'),
    target_fixture="context",
)
def when_structlog_message_emitted(context: Context, message: str) -> Context:
    """Emit a structlog message."""
    log = structlog.get_logger()
    log.info(message)
    return context


@then(
    parsers.parse('the structlog event should contain "{key}" with value "{expected}"')
)
def then_structlog_event_contains(context: Context, key: str, expected: str) -> None:
    """Verify the captured structlog event contains the expected key/value."""
    events = context["captured_events"]
    assert len(events) == 1, f"expected 1 captured event, got {len(events)}"
    actual = events[0].get(key)
    assert actual == expected, f"expected {key}={expected!r}, got {actual!r}"
