"""BDD steps for Celery worker correlation ID signal handlers."""

from __future__ import annotations

import typing as typ

import pytest

celery = pytest.importorskip("celery")

from celery import Celery  # noqa: E402
from celery.signals import task_postrun, task_prerun  # noqa: E402
from pytest_bdd import given, parsers, scenarios, then, when  # noqa: E402

from falcon_correlate import correlation_id_var  # noqa: E402
from falcon_correlate.celery import _maybe_connect_celery_worker_signals  # noqa: E402

scenarios("celery_worker_signal.feature")


class Context(typ.TypedDict, total=False):
    """Type definition for per-scenario worker capture state."""

    task: celery.Task
    observed: dict[str, str | None]
    task_correlation_id_seen: str | None
    correlation_id_after_task: str | None


@pytest.fixture(autouse=True, scope="session")
def _connect_celery_worker_signals() -> None:
    """Connect the Celery worker signal handlers once for all scenarios."""
    _maybe_connect_celery_worker_signals()


@pytest.fixture(autouse=True)
def _reset_context_variables() -> typ.Generator[None, None, None]:
    """Reset context variables after each scenario."""
    yield
    correlation_id_var.set(None)


@given(
    parsers.parse('a Celery worker task request with correlation ID "{value}"'),
    target_fixture="context",
)
def given_task_request_with_correlation_id(value: str) -> Context:
    """Create a real Celery task with a request correlation ID."""
    app = Celery("bdd-celery-worker", broker="memory://")
    observed: dict[str, str | None] = {}

    @app.task(name="bdd.worker.echo", bind=True)
    def echo(self: celery.Task, payload: str) -> str:
        observed["task_correlation_id_seen"] = correlation_id_var.get()
        return payload

    echo.push_request(correlation_id=value)
    return {
        "task": echo,
        "observed": observed,
        "task_correlation_id_seen": observed.get("task_correlation_id_seen"),
    }


@when("the Celery worker lifecycle runs the task", target_fixture="context")
def when_worker_runs_task(context: Context) -> Context:
    """Drive the actual Celery task signals around the task body."""
    task = context["task"]

    try:
        task_prerun.send(sender=task, task=task, args=("payload",), kwargs={})
        task.run("payload")
        task_postrun.send(
            sender=task,
            task=task,
            args=("payload",),
            kwargs={},
            retval="payload",
            state="SUCCESS",
        )
    finally:
        task.pop_request()

    return {
        **context,
        "task_correlation_id_seen": context["observed"].get("task_correlation_id_seen"),
        "correlation_id_after_task": correlation_id_var.get(),
    }


@then(parsers.parse('the task body should observe correlation ID "{value}"'))
def then_task_body_observes_correlation_id(context: Context, value: str) -> None:
    """Assert the task body received the worker correlation ID context."""
    assert context["task_correlation_id_seen"] == value


@then("the ambient correlation ID should be cleared after the task finishes")
def then_ambient_correlation_id_is_cleared(context: Context) -> None:
    """Assert worker cleanup restored a clean ambient context."""
    assert context["correlation_id_after_task"] is None
