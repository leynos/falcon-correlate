"""BDD steps for Celery worker correlation ID signal handlers."""

from __future__ import annotations

import io
import logging
import typing as typ

import pytest

try:
    from celery import Celery
    from celery.signals import task_postrun, task_prerun
except ModuleNotFoundError as error:  # pragma: no cover - blocked child only
    if error.name != "celery":
        raise
    _HAS_CELERY = False
else:
    _HAS_CELERY = True

pytestmark = pytest.mark.skipif(
    not _HAS_CELERY,
    reason="celery is not installed",
)

from pytest_bdd import (  # ruff: ignore[module-import-not-at-top-of-file] -- dependency probe first.
    given,
    parsers,
    scenarios,
    then,
    when,
)

from falcon_correlate import (  # ruff: ignore[module-import-not-at-top-of-file] -- dependency probe first.
    RECOMMENDED_LOG_FORMAT,
    ContextualLogFilter,
    ContextualLogFormatter,
    correlation_id_var,
)
from falcon_correlate._celery_worker_signals import (  # ruff: ignore[module-import-not-at-top-of-file] -- dependency probe first.
    _celery_context_tokens,
)
from falcon_correlate.celery import (  # ruff: ignore[module-import-not-at-top-of-file] -- dependency probe first.
    _maybe_connect_celery_worker_signals,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    import celery

scenarios("celery_worker_signal.feature")


_LOGGER_NAME = "bdd_celery_worker_signal"
_HOSTILE_CORRELATION_ID = (
    "abc\r\n2026-01-01 - [CRITICAL] - [forged] - forged - injected"
)


class Context(typ.TypedDict, total=False):
    """Type definition for per-scenario worker capture state."""

    task: celery.Task
    observed: dict[str, str | None]
    correlation_id: str | None
    stream: io.StringIO
    task_correlation_id_seen: str | None
    request_correlation_id_seen: str | None
    correlation_id_after_task: str | None


def _build_logger(stream: io.StringIO) -> logging.Logger:
    """Return the worker logger wired with the filter and safe formatter."""
    worker_logger = logging.getLogger(_LOGGER_NAME)
    worker_logger.handlers.clear()
    worker_logger.setLevel(logging.INFO)
    worker_logger.propagate = False

    handler = logging.StreamHandler(stream)
    handler.setFormatter(ContextualLogFormatter(RECOMMENDED_LOG_FORMAT))
    handler.addFilter(ContextualLogFilter())
    worker_logger.addHandler(handler)
    return worker_logger


def _build_worker_context(value: str | None) -> Context:
    """Create a real Celery task whose body logs through the safe formatter."""
    app = Celery("bdd-celery-worker", broker="memory://")
    observed: dict[str, str | None] = {}
    stream = io.StringIO()
    worker_logger = _build_logger(stream)

    @app.task(name="bdd.worker.echo", bind=True)
    def echo(self: celery.Task, payload: str) -> str:
        """Record the visible IDs, log one record, and echo the payload."""
        observed["task_correlation_id_seen"] = correlation_id_var.get()
        observed["request_correlation_id_seen"] = self.request.correlation_id
        worker_logger.info("handled task")
        return payload

    echo.push_request(correlation_id=value)
    return {
        "task": echo,
        "observed": observed,
        "correlation_id": value,
        "stream": stream,
    }


@pytest.fixture(autouse=True, scope="session")
def _connect_celery_worker_signals() -> None:
    """Connect the Celery worker signal handlers once for all scenarios."""
    _maybe_connect_celery_worker_signals()


@pytest.fixture(autouse=True)
def _isolate_celery_context_tokens(
    _reset_context_variables: None,
) -> cabc.Generator[None, None, None]:
    """Discard the Celery token store around each scenario.

    The shared fixture must run first so the scenario starts from a clean
    public context, and it must tear down last so the scenario's
    ``task_postrun`` cleanup still restores the values it seeded.
    """
    celery_tokens_token = _celery_context_tokens.set(None)
    try:
        yield
    finally:
        _celery_context_tokens.reset(celery_tokens_token)


@given(
    parsers.parse('a Celery worker task request with correlation ID "{value}"'),
    target_fixture="context",
)
def given_task_request_with_correlation_id(value: str) -> Context:
    """Create a real Celery task with a request correlation ID.

    Returns
    -------
    Context
        The value produced for the test scenario.

    """
    return _build_worker_context(value)


@given(
    "a Celery worker task request with a line-break correlation ID",
    target_fixture="context",
)
def given_task_request_with_line_break_correlation_id() -> Context:
    """Create a Celery task whose request ID tries to forge a log record.

    Returns
    -------
    Context
        The value produced for the test scenario.

    """
    return _build_worker_context(_HOSTILE_CORRELATION_ID)


@given(parsers.parse('the ambient correlation ID is set to "{value}"'))
def given_ambient_correlation_id(value: str) -> None:
    """Set a pre-existing ambient correlation ID before worker execution."""
    correlation_id_var.set(value)


@when("the Celery worker lifecycle runs the task", target_fixture="context")
def when_worker_runs_task(context: Context) -> Context:
    """Drive the actual Celery task signals around the task body.

    Returns
    -------
    Context
        The value produced for the test scenario.

    """
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
        "request_correlation_id_seen": context["observed"].get(
            "request_correlation_id_seen"
        ),
        "correlation_id_after_task": correlation_id_var.get(),
    }


@then(parsers.parse('the task body should observe correlation ID "{value}"'))
def then_task_body_observes_correlation_id(context: Context, value: str) -> None:
    """Assert the task body received the worker correlation ID context."""
    assert context["task_correlation_id_seen"] == value, (
        "Task body did not observe the expected correlation ID"
    )


@then("the ambient correlation ID should be cleared after the task finishes")
def then_ambient_correlation_id_is_cleared(context: Context) -> None:
    """Assert worker cleanup restored a clean ambient context."""
    assert context["correlation_id_after_task"] is None, (
        "Ambient correlation ID leaked after task completion"
    )


@then(
    parsers.parse(
        'the ambient correlation ID should be restored to "{value}" after the '
        "task finishes"
    )
)
def then_ambient_correlation_id_is_restored(value: str) -> None:
    """Assert worker cleanup restores a pre-existing ambient correlation ID."""
    assert correlation_id_var.get() == value, (
        "Ambient correlation ID was not restored after task completion"
    )


@then("the worker should emit exactly one escaped log record")
def then_worker_emits_one_escaped_log_record(context: Context) -> None:
    """Assert hostile worker metadata cannot add a second log record."""
    lines = context["stream"].getvalue().splitlines()
    assert len(lines) == 1, f"expected one log line, got {lines!r}"
    assert "abc\\r\\n2026-01-01" in lines[0], (
        f"expected escaped CRLF in the worker log, got {lines[0]!r}"
    )
    assert not any(
        ord(character) < 0x20 or 0x7F <= ord(character) <= 0x9F
        for character in lines[0]
    ), f"expected no raw control characters, got {lines[0]!r}"


@then("the worker should retain the raw correlation ID for propagation")
def then_worker_retains_raw_correlation_id(context: Context) -> None:
    """Assert the raw value survives on the context and the task request."""
    expected = _HOSTILE_CORRELATION_ID
    assert context["task_correlation_id_seen"] == expected, (
        "Task body did not observe the raw correlation ID"
    )
    assert context["request_correlation_id_seen"] == expected, (
        "Task request did not retain the raw correlation ID"
    )
