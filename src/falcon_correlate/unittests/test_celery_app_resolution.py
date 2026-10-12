"""Tests for configured Celery publishers and backend verdicts."""

from __future__ import annotations

import logging
import typing as typ
from unittest import mock

import pytest

try:
    from celery import Celery
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
    correlation_id_var,
)
from falcon_correlate.celery import (  # ruff: ignore[module-import-not-at-top-of-file] -- dependency probe first.
    _app_backend_uses_rpc,
    configure_celery_correlation,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc


class _FailingBackend:
    """Backend test double whose URI inspection fails."""

    def as_uri(self) -> str:
        """Raise to model a temporarily unavailable backend inspection."""
        raise RuntimeError


class _MalformedCeleryApp:
    """Celery-shaped app with a backend that cannot report its URI."""

    def __init__(self) -> None:
        """Initialize the backend member inspected by the helper."""
        self.backend = _FailingBackend()

    def send_task(self, *args: object, **kwargs: object) -> object:
        """Satisfy the configured-app shape without publishing a task."""
        return None


class _AppWithoutBackend:
    """Malformed app double without an optional backend attribute."""

    def send_task(self, *args: object, **kwargs: object) -> object:
        """Satisfy the configured-app shape without publishing a task."""
        return None


def test_backend_uri_failure_is_unknown_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A backend error must not be mistaken for a non-RPC verdict."""
    with caplog.at_level(logging.DEBUG, logger="falcon_correlate.celery"):
        backend_uses_rpc = _app_backend_uses_rpc(_MalformedCeleryApp())

    assert backend_uses_rpc is None, (
        "an inspection exception must remain distinct from a non-RPC verdict"
    )
    assert any(
        "Unable to inspect Celery result backend URI" in record.message
        for record in caplog.records
    ), "a failed backend lookup should emit a diagnostic"


def test_missing_backend_attribute_is_a_non_rpc_verdict() -> None:
    """Missing optional backend members retain the defensive false result."""
    app_without_backend = typ.cast("typ.Any", _AppWithoutBackend())
    assert _app_backend_uses_rpc(app_without_backend) is False, (
        "an app without backend configuration should be treated as non-RPC"
    )


def test_publish_retries_failed_backend_inspection_without_losing_task_id(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transient URI failure is not cached as a non-RPC result."""
    celery_app = Celery(
        "retry-backend-verdict-app",
        backend="cache+memory://",
        broker="memory://",
    )
    backend_uri = mock.Mock(
        side_effect=[
            RuntimeError("configure inspection failed"),
            RuntimeError("publish inspection failed"),
            "rpc://",
        ]
    )
    monkeypatch.setattr(celery_app.backend, "as_uri", backend_uri)
    configure_celery_correlation(celery_app)
    current_backend_lookup = mock.Mock(return_value=False)
    monkeypatch.setattr(
        "falcon_correlate.celery._current_result_backend_uses_rpc",
        current_backend_lookup,
    )

    with mock.patch("kombu.Producer.publish", autospec=True) as publish:

        def _logic() -> None:
            """Publish once while unknown and once after RPC is confirmed."""
            correlation_id_var.set("request-correlation-id")
            celery_app.send_task("unregistered-task", task_id="first-task-id")
            celery_app.send_task("unregistered-task", task_id="second-task-id")

        isolated_context(_logic)

    assert publish.call_count == 2, "both task publishes should reach Kombu"
    assert [call.kwargs["correlation_id"] for call in publish.call_args_list] == [
        "first-task-id",
        "second-task-id",
    ], "unknown and RPC verdicts must both preserve Celery task IDs"
    assert backend_uri.call_count == 3, (
        "failed inspections should retry and the definite verdict should be cached"
    )
    current_backend_lookup.assert_not_called()
