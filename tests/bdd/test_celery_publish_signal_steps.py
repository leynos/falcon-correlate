"""BDD steps for Celery publish correlation ID propagation."""

from __future__ import annotations

import typing as typ
from unittest import mock

import pytest

celery = pytest.importorskip("celery")

from celery import Celery  # noqa: E402
from pytest_bdd import given, parsers, scenarios, then, when  # noqa: E402

import falcon_correlate.celery as _celery_integration  # noqa: F401, E402
from falcon_correlate import correlation_id_var  # noqa: E402

scenarios("celery_publish_signal.feature")


class Context(typ.TypedDict, total=False):
    """Type definition for per-scenario publish capture state."""

    published_correlation_id: str
    task_id: str


@pytest.fixture(autouse=True)
def _reset_context_variables() -> typ.Generator[None, None, None]:
    """Reset context variables after each scenario."""
    yield
    correlation_id_var.set(None)


@given(
    parsers.parse('the correlation ID is set to "{value}"'),
    target_fixture="context",
)
def given_correlation_id_set(value: str) -> Context:
    """Set the ambient correlation ID."""
    correlation_id_var.set(value)
    return {}


@given("no correlation ID is set", target_fixture="context")
def given_no_correlation_id() -> Context:
    """Clear any ambient correlation ID."""
    correlation_id_var.set(None)
    return {}


def _publish_task(**apply_async_kwargs: str) -> Context:
    """Publish a task and capture the final broker correlation ID."""
    app = Celery("bdd-celery-propagation", broker="memory://")
    app.conf.task_always_eager = False

    @app.task(name="bdd.echo")
    def echo(value: str) -> str:
        return value

    with mock.patch("kombu.Producer.publish", autospec=True) as publish:
        result = echo.apply_async(args=("payload",), **apply_async_kwargs)

    assert publish.call_count == 1, "expected a single broker publish call"
    published_correlation_id = publish.call_args.kwargs["correlation_id"]
    return {
        "published_correlation_id": published_correlation_id,
        "task_id": result.id,
    }


@when("I publish a Celery task", target_fixture="context")
def when_publish_task() -> Context:
    """Publish a task through Celery's normal apply_async path."""
    return _publish_task()


@when(
    parsers.parse('I publish a Celery task with explicit correlation ID "{value}"'),
    target_fixture="context",
)
def when_publish_task_with_explicit_correlation_id(value: str) -> Context:
    """Publish a task while the caller provides a Celery correlation ID."""
    return _publish_task(correlation_id=value)


@then(parsers.parse('the outgoing task message should use correlation ID "{value}"'))
def then_published_correlation_id_matches(context: Context, value: str) -> None:
    """Assert the broker publish call used the expected correlation ID."""
    assert context["published_correlation_id"] == value


@then("the outgoing task message should keep the generated task ID as correlation ID")
def then_published_correlation_id_matches_generated_task_id(context: Context) -> None:
    """Assert Celery's generated task ID remains the broker correlation ID."""
    assert context["published_correlation_id"] == context["task_id"]
