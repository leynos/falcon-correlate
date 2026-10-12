"""Tests for app resolution during Celery publish handling."""

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
    propagate_correlation_id_to_celery,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc


class _FailingBackend:
    """Backend test double whose URI inspection fails."""

    def as_uri(self) -> str:
        """Raise to model a malformed or unavailable backend configuration."""
        raise RuntimeError


class _MalformedCeleryApp:
    """Celery-shaped app with a backend that cannot report its URI."""

    def __init__(self) -> None:
        """Initialize members inspected by the app protocol."""
        self.backend = _FailingBackend()
        self.finalized = True
        self.tasks: dict[str, object] = {}


def test_backend_uri_failure_does_not_escape_the_app_check(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A broken backend URI must not raise through the optional integration."""
    with caplog.at_level(logging.DEBUG, logger="falcon_correlate.celery"):
        backend_uses_rpc = _app_backend_uses_rpc(_MalformedCeleryApp())

    assert backend_uses_rpc is False, (
        "a failed backend lookup should use the non-RPC fallback"
    )
    assert any(
        "Unable to inspect Celery result backend URI" in record.message
        for record in caplog.records
    ), "a failed backend lookup should emit a diagnostic"


def test_unfinalized_configured_app_is_not_finalized_during_resolution(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolution skips unfinished registries while finding another app."""
    unfinished_app = Celery(
        "unfinished-resolution-app",
        backend="cache+memory://",
        broker="memory://",
        autofinalize=False,
    )
    publishing_app = Celery(
        "finalized-resolution-app",
        backend="cache+memory://",
        broker="memory://",
    )

    @publishing_app.task(name="finalized-resolution-task", shared=False)
    def finalized_resolution_task() -> None:
        """Provide a task name owned by the finalized application."""

    publishing_app.finalize()
    configure_celery_correlation(unfinished_app)
    configure_celery_correlation(publishing_app)
    fallback = mock.Mock(return_value=False)
    monkeypatch.setattr(
        "falcon_correlate.celery._current_result_backend_uses_rpc",
        fallback,
    )
    properties = {"correlation_id": "celery-task-id"}

    def _logic() -> None:
        """Exercise resolution with one unfinished configured app."""
        correlation_id_var.set("request-correlation-id")
        propagate_correlation_id_to_celery(
            sender=finalized_resolution_task.name,
            properties=properties,
        )

    isolated_context(_logic)

    fallback.assert_not_called()
    assert unfinished_app.finalized is False, (
        "publish resolution must not finalize an application owned by its caller"
    )
    assert properties["correlation_id"] == "request-correlation-id", (
        "the unique finalized task owner should supply the backend verdict"
    )


def test_shared_task_name_preserves_task_id_when_app_is_ambiguous(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A shared name cannot select between apps with different backends."""
    rpc_app = Celery(
        "shared-resolution-rpc-app",
        backend="rpc://",
        broker="memory://",
    )
    non_rpc_app = Celery(
        "shared-resolution-non-rpc-app",
        backend="cache+memory://",
        broker="memory://",
    )

    @rpc_app.task(name="shared-resolution-task")
    def shared_resolution_task() -> None:
        """Provide a task registered with Celery's shared-task mechanism."""

    rpc_app.finalize()
    non_rpc_app.finalize()
    assert shared_resolution_task.name in rpc_app.tasks, (
        "the shared task should be present in its defining application"
    )
    assert shared_resolution_task.name in non_rpc_app.tasks, (
        "Celery should register the shared task in the other application"
    )
    configure_celery_correlation(rpc_app)
    configure_celery_correlation(non_rpc_app)
    fallback = mock.Mock(return_value=False)
    monkeypatch.setattr(
        "falcon_correlate.celery._current_result_backend_uses_rpc",
        fallback,
    )
    properties = {"correlation_id": "celery-task-id"}

    def _logic() -> None:
        """Exercise publish handling for the shared task name."""
        correlation_id_var.set("request-correlation-id")
        propagate_correlation_id_to_celery(
            sender=shared_resolution_task.name,
            properties=properties,
        )

    isolated_context(_logic)

    fallback.assert_not_called()
    assert properties["correlation_id"] == "celery-task-id", (
        "ambiguous ownership must preserve Celery's task-id correlation"
    )
