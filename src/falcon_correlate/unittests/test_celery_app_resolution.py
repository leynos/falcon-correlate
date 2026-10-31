"""Tests for configured Celery publishers and active-app resolution."""

from __future__ import annotations

import importlib
import sys
import types
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
    celery as falcon_celery,
)
from falcon_correlate.celery import (  # ruff: ignore[module-import-not-at-top-of-file] -- dependency probe first.
    _current_result_backend_uses_rpc,
    configure_celery_correlation,
    propagate_correlation_id_to_celery,
)
from falcon_correlate.middleware_utils import (  # ruff: ignore[module-import-not-at-top-of-file] -- dependency probe first.
    correlation_id_var,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc


def test_current_result_backend_uses_rpc_for_rpc_current_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fallback detects an RPC backend on Celery's active app."""
    celery_module = importlib.import_module("celery")
    rpc_app = Celery(
        "fallback-rpc-current-app",
        backend="rpc://",
        broker="memory://",
        set_as_current=False,
    )
    monkeypatch.setattr(celery_module, "current_app", rpc_app)

    assert _current_result_backend_uses_rpc() is True, (
        "an rpc:// active app should be detected as RPC"
    )


def test_current_result_backend_uses_rpc_for_non_rpc_current_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fallback detects a non-RPC backend on Celery's active app."""
    celery_module = importlib.import_module("celery")
    non_rpc_app = Celery(
        "fallback-non-rpc-current-app",
        backend="cache+memory://",
        broker="memory://",
        set_as_current=False,
    )
    monkeypatch.setattr(celery_module, "current_app", non_rpc_app)

    assert _current_result_backend_uses_rpc() is False, (
        "a non-RPC active app should be detected as non-RPC"
    )


def test_current_result_backend_uses_rpc_without_current_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Celery module without an active app is treated as non-RPC."""
    monkeypatch.setitem(sys.modules, "celery", types.ModuleType("celery"))

    assert _current_result_backend_uses_rpc() is False, (
        "a Celery module without current_app should be treated as non-RPC"
    )


def test_current_result_backend_uses_rpc_with_none_current_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unset active app is treated as non-RPC."""
    celery_module = importlib.import_module("celery")
    monkeypatch.setattr(celery_module, "current_app", None)

    assert _current_result_backend_uses_rpc() is False, (
        "an unset current_app should be treated as non-RPC"
    )


def test_current_result_backend_uses_rpc_when_celery_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unavailable Celery import preserves task-ID correlation."""
    monkeypatch.setitem(sys.modules, "celery", None)

    assert _current_result_backend_uses_rpc() is False, (
        "an unavailable Celery import should preserve task-ID correlation"
    )


def test_current_result_backend_failure_is_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed active-app inspection remains inconclusive."""
    celery_module = importlib.import_module("celery")
    failing_app = Celery(
        "fallback-failing-current-app",
        backend="cache+memory://",
        broker="memory://",
        set_as_current=False,
    )
    monkeypatch.setattr(
        failing_app.backend,
        "as_uri",
        mock.Mock(side_effect=RuntimeError("inspection failed")),
    )
    monkeypatch.setattr(celery_module, "current_app", failing_app)

    assert _current_result_backend_uses_rpc() is None, (
        "an active-app inspection failure should stay inconclusive"
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
        set_as_current=False,
    )
    backend_uri = mock.Mock(
        side_effect=[
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
            """Publish while unknown, after RPC is confirmed, then reuse it."""
            correlation_id_var.set("request-correlation-id")
            celery_app.send_task("unregistered-task", task_id="first-task-id")
            celery_app.send_task("unregistered-task", task_id="second-task-id")
            celery_app.send_task("unregistered-task", task_id="third-task-id")

        isolated_context(_logic)

    assert publish.call_count == 3, "all task publishes should reach Kombu"
    assert [call.kwargs["correlation_id"] for call in publish.call_args_list] == [
        "first-task-id",
        "second-task-id",
        "third-task-id",
    ], "unknown and RPC verdicts must both preserve Celery task IDs"
    assert backend_uri.call_count == 2, (
        "publish inspection should retry once and cache its definite verdict"
    )
    current_backend_lookup.assert_not_called()


def test_fallback_verdict_is_not_cached(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The active-app fallback must not write into the configured-app cache."""
    celery_module = importlib.import_module("celery")
    non_rpc_app = Celery(
        "fallback-cache-isolation-app",
        backend="cache+memory://",
        broker="memory://",
        set_as_current=False,
    )
    monkeypatch.setattr(celery_module, "current_app", non_rpc_app)
    properties: dict[str, object] = {"correlation_id": "celery-task-id"}

    def _logic() -> None:
        """Exercise the fallback path with an ambient correlation ID."""
        correlation_id_var.set("request-correlation-id")
        propagate_correlation_id_to_celery(
            sender="fallback-cache-isolation-task",
            properties=properties,
        )

    isolated_context(_logic)

    assert properties["correlation_id"] == "request-correlation-id", (
        "the fallback should still replace the task ID for a non-RPC app"
    )
    assert non_rpc_app not in falcon_celery._configured_app_backend_rpc_verdicts, (
        "the active-app fallback must not populate the configured-app cache"
    )
