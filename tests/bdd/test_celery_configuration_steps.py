"""BDD steps for the public Celery configuration helper."""

from __future__ import annotations

import typing as typ
from unittest import mock

import pytest

celery = pytest.importorskip("celery")

from celery import Celery  # noqa: E402
from celery.signals import before_task_publish, task_postrun, task_prerun  # noqa: E402
from pytest_bdd import given, parsers, scenarios, then, when  # noqa: E402

from falcon_correlate import correlation_id_var  # noqa: E402
from falcon_correlate.celery import (  # noqa: E402
    _BEFORE_TASK_PUBLISH_DISPATCH_UID,
    _TASK_POSTRUN_DISPATCH_UID,
    _TASK_PRERUN_DISPATCH_UID,
    _celery_context_tokens,
    configure_celery_correlation,
)

scenarios("celery_configuration.feature")


class Context(typ.TypedDict, total=False):
    """Type definition for per-scenario configuration state."""

    app: Celery
    task: celery.Task
    observed: dict[str, str | None]
    published_correlation_id: str
    task_correlation_id_seen: str | None
    correlation_id_after_task: str | None


@pytest.fixture(autouse=True)
def _reset_context_variables() -> typ.Generator[None, None, None]:
    """Reset context variables around each scenario using token-based reset."""
    celery_tokens_token = _celery_context_tokens.set(None)
    correlation_token = correlation_id_var.set(None)
    try:
        yield
    finally:
        _celery_context_tokens.reset(celery_tokens_token)
        correlation_id_var.reset(correlation_token)


@given("Celery correlation handlers have been disconnected")
def given_celery_handlers_disconnected() -> None:
    """Disconnect integration receivers so the scenario proves configuration."""
    before_task_publish.disconnect(dispatch_uid=_BEFORE_TASK_PUBLISH_DISPATCH_UID)
    task_prerun.disconnect(dispatch_uid=_TASK_PRERUN_DISPATCH_UID)
    task_postrun.disconnect(dispatch_uid=_TASK_POSTRUN_DISPATCH_UID)


@given("a Celery app configured through the public helper", target_fixture="context")
def given_configured_celery_app() -> Context:
    """Create and configure a Celery app through the public helper."""
    app = Celery("bdd-celery-configuration", broker="memory://")
    app.conf.task_always_eager = False
    configured_app = configure_celery_correlation(app)
    assert configured_app is app
    return {"app": app}


@given(parsers.parse('the correlation ID is set to "{value}"'))
def given_correlation_id_set(value: str) -> None:
    """Set the ambient correlation ID."""
    correlation_id_var.set(value)


@given(
    parsers.parse(
        'a configured Celery worker task request with correlation ID "{value}"'
    )
)
def given_configured_task_request(context: Context, value: str) -> None:
    """Create a real Celery task with a request correlation ID."""
    app = context["app"]
    observed: dict[str, str | None] = {}

    @app.task(name="bdd.configured.worker.echo", bind=True)
    def echo(self: celery.Task, payload: str) -> str:
        observed["task_correlation_id_seen"] = correlation_id_var.get()
        return payload

    echo.push_request(correlation_id=value)
    context["task"] = echo
    context["observed"] = observed


@when("I publish a configured Celery task", target_fixture="context")
def when_publish_configured_task(context: Context) -> Context:
    """Publish a task through Celery's normal apply_async path."""
    app = context["app"]

    @app.task(name="bdd.configured.echo")
    def echo(value: str) -> str:
        return value

    with mock.patch("kombu.Producer.publish", autospec=True) as publish:
        echo.apply_async(args=("payload",))

    assert publish.call_count == 1, "expected a single broker publish call"
    return {
        **context,
        "published_correlation_id": publish.call_args.kwargs["correlation_id"],
    }


@when("the configured Celery worker lifecycle runs the task", target_fixture="context")
def when_configured_worker_runs_task(context: Context) -> Context:
    """Drive the actual Celery task signals around the task body."""
    task = context["task"]

    try:
        task_prerun.send(sender=task, task=task, args=("payload",), kwargs={})
        task.run("payload")
    finally:
        task_postrun.send(
            sender=task,
            task=task,
            args=("payload",),
            kwargs={},
            retval="payload",
            state="SUCCESS",
        )
        task.pop_request()

    return {
        **context,
        "task_correlation_id_seen": context["observed"].get("task_correlation_id_seen"),
        "correlation_id_after_task": correlation_id_var.get(),
    }


@then(
    parsers.parse(
        'the configured outgoing task message should use correlation ID "{value}"'
    )
)
def then_configured_published_correlation_id_matches(
    context: Context,
    value: str,
) -> None:
    """Assert the broker publish call used the expected correlation ID."""
    assert context["published_correlation_id"] == value


@then(parsers.parse('the configured task body should observe correlation ID "{value}"'))
def then_configured_task_body_observes_correlation_id(
    context: Context,
    value: str,
) -> None:
    """Assert the task body received the worker correlation ID context."""
    assert context["task_correlation_id_seen"] == value


@then("the configured ambient correlation ID should be cleared after the task finishes")
def then_configured_ambient_correlation_id_is_cleared(context: Context) -> None:
    """Assert worker cleanup restored a clean ambient context."""
    assert context["correlation_id_after_task"] is None
