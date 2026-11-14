"""Worker-driven regression tests for safe correlation metadata rendering.

These tests drive the real Celery task signals so the guarantee is observed at
the plaintext logging boundary, not only on hand-built records.
"""

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

from falcon_correlate import (  # ruff: ignore[module-import-not-at-top-of-file] -- dependency probe first.
    RECOMMENDED_LOG_FORMAT,
    ContextualLogFilter,
    ContextualLogFormatter,
    correlation_id_var,
)
from falcon_correlate.celery import (  # ruff: ignore[module-import-not-at-top-of-file] -- dependency probe first.
    _maybe_connect_celery_publish_signal,
    _maybe_connect_celery_worker_signals,
    propagate_correlation_id_to_celery,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    import celery


_HOSTILE_CORRELATION_ID = (
    "abc\r\n2026-01-01 - [CRITICAL] - [forged] - forged - injected"
)
_LOGGER_NAME = "test.celery_worker_signal_logging"


def _build_logger(stream: io.StringIO) -> logging.Logger:
    """Return a logger whose handler uses the filter and safe formatter."""
    test_logger = logging.getLogger(_LOGGER_NAME)
    test_logger.handlers.clear()
    test_logger.setLevel(logging.INFO)
    test_logger.propagate = False

    handler = logging.StreamHandler(stream)
    handler.setFormatter(ContextualLogFormatter(RECOMMENDED_LOG_FORMAT))
    handler.addFilter(ContextualLogFilter())
    test_logger.addHandler(handler)
    return test_logger


def _contains_control_character(value: str) -> bool:
    """Return whether *value* contains a control or line-separator character."""
    return any(
        ord(character) < 0x20
        or 0x7F <= ord(character) <= 0x9F
        or ord(character) in {0x2028, 0x2029}
        for character in value
    )


@pytest.mark.parametrize(
    ("correlation_id", "expected_fragment"),
    [
        pytest.param(
            _HOSTILE_CORRELATION_ID,
            "abc\\r\\n2026-01-01",
            id="hostile-line-break",
        ),
        pytest.param(
            "worker-correlation-id",
            "[worker-correlation-id]",
            id="ordinary-identifier",
        ),
        pytest.param(None, "[-]", id="missing-metadata"),
    ],
)
def test_worker_metadata_renders_as_one_safe_log_line(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    correlation_id: str | None,
    expected_fragment: str,
) -> None:
    """A task request ID cannot add records, and raw values survive."""
    stream = io.StringIO()
    test_logger = _build_logger(stream)
    observed: dict[str, str | None] = {}
    app = Celery("test-safe-worker-logging", broker="memory://")

    @app.task(name="tests.contextual_log_formatter.echo", bind=True)
    def echo(self: celery.Task, payload: str) -> str:
        """Record the visible context ID and emit one task log record."""
        observed["during"] = correlation_id_var.get()
        test_logger.info("handled task")
        return payload

    _maybe_connect_celery_worker_signals()
    echo.push_request(correlation_id=correlation_id)

    def _logic() -> None:
        """Run the worker signal lifecycle inside an isolated context."""
        try:
            task_prerun.send(sender=echo, task=echo, args=("payload",), kwargs={})
            echo.run("payload")
            observed["request"] = echo.request.correlation_id
        finally:
            task_postrun.send(
                sender=echo,
                task=echo,
                args=("payload",),
                kwargs={},
                retval="payload",
                state="SUCCESS",
            )
            observed["after"] = correlation_id_var.get()
            echo.pop_request()

    isolated_context(_logic)

    lines = stream.getvalue().splitlines()
    assert len(lines) == 1, f"expected one log line, got {lines!r}"
    assert expected_fragment in lines[0], (
        f"expected {expected_fragment!r} in the log line, got {lines[0]!r}"
    )
    assert not _contains_control_character(lines[0]), (
        f"expected no raw control characters, got {lines[0]!r}"
    )
    assert observed["during"] == correlation_id, (
        f"expected {correlation_id!r} during the task, got {observed['during']!r}"
    )
    assert observed["request"] == correlation_id, (
        f"expected {correlation_id!r} on the request, got {observed['request']!r}"
    )
    assert observed["after"] is None, (
        f"expected the context to reset, got {observed['after']!r}"
    )


@pytest.mark.parametrize(
    ("context_value", "expected_correlation_id"),
    [
        pytest.param(
            _HOSTILE_CORRELATION_ID,
            _HOSTILE_CORRELATION_ID,
            id="hostile-value-preserved",
        ),
        pytest.param(
            "request-correlation-id",
            "request-correlation-id",
            id="ordinary-identifier",
        ),
        pytest.param(
            None,
            "celery-task-id",
            id="missing-metadata-keeps-task-id",
        ),
    ],
)
def test_publish_propagation_preserves_the_raw_value(
    monkeypatch: pytest.MonkeyPatch,
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    context_value: str | None,
    expected_correlation_id: str,
) -> None:
    """A non-RPC publish copies the raw correlation value unchanged."""
    monkeypatch.setattr(
        "falcon_correlate.celery._current_result_backend_uses_rpc",
        lambda: False,
    )
    _maybe_connect_celery_publish_signal()
    properties: dict[str, str] = {"correlation_id": "celery-task-id"}

    def _logic() -> None:
        """Publish from an isolated context holding the ambient value."""
        correlation_id_var.set(context_value)
        propagate_correlation_id_to_celery(properties=properties)

    isolated_context(_logic)

    assert properties["correlation_id"] == expected_correlation_id, (
        f"expected {expected_correlation_id!r}, got {properties['correlation_id']!r}"
    )
