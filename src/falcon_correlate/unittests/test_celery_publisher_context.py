"""Tests for configured Celery publisher identity and verdict caching."""

from __future__ import annotations

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
    configure_celery_correlation,
    propagate_correlation_id_to_celery,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc


def test_publish_uses_each_configured_app_backend(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
) -> None:
    """Actual Celery publishes should use their configured app's verdict."""
    rpc_app = Celery(
        "configured-rpc-publish-app",
        backend="rpc://",
        broker="memory://",
    )
    non_rpc_app = Celery(
        "configured-non-rpc-publish-app",
        backend="cache+memory://",
        broker="memory://",
    )

    @rpc_app.task(name="configured-rpc-publish-task", shared=False)
    def configured_rpc_publish_task() -> None:
        """Provide a task name owned by the RPC application."""

    @non_rpc_app.task(name="configured-non-rpc-publish-task", shared=False)
    def configured_non_rpc_publish_task() -> None:
        """Provide a task name owned by the non-RPC application."""

    rpc_app.finalize()
    non_rpc_app.finalize()
    configure_celery_correlation(rpc_app)
    configure_celery_correlation(non_rpc_app)
    published_task_ids: list[str] = []

    with mock.patch("kombu.Producer.publish", autospec=True) as publish:

        def _logic() -> None:
            """Publish through both real Celery app task paths."""
            correlation_id_var.set("request-correlation-id")
            published_task_ids.extend([
                configured_rpc_publish_task.apply_async().id,
                configured_non_rpc_publish_task.apply_async().id,
            ])

        isolated_context(_logic)

    assert publish.call_count == 2, "each task should reach the broker publish call"
    assert (
        publish.call_args_list[0].kwargs["correlation_id"] == published_task_ids[0]
    ), "RPC result backends should preserve Celery task-ID correlation"
    assert publish.call_args_list[1].kwargs["correlation_id"] == (
        "request-correlation-id"
    ), "non-RPC result backends should receive request correlation"


def test_publisher_identity_does_not_depend_on_task_registry_owner(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
) -> None:
    """An app publishing another registry's task uses its own backend."""
    rpc_publisher = Celery(
        "configured-rpc-task-publisher",
        backend="rpc://",
        broker="memory://",
    )
    non_rpc_task_owner = Celery(
        "configured-non-rpc-task-owner",
        backend="cache+memory://",
        broker="memory://",
    )

    @non_rpc_task_owner.task(name="task-owned-by-non-rpc-app", shared=False)
    def task_owned_by_non_rpc_app() -> None:
        """Provide a task name owned only by the non-RPC app."""

    configure_celery_correlation(rpc_publisher)
    configure_celery_correlation(non_rpc_task_owner)

    with mock.patch("kombu.Producer.publish", autospec=True) as publish:

        def _logic() -> None:
            """Publish the owner app's task name through the RPC app."""
            correlation_id_var.set("request-correlation-id")
            rpc_publisher.send_task(
                task_owned_by_non_rpc_app.name,
                task_id="rpc-publisher-task-id",
            )

        isolated_context(_logic)

    assert publish.call_count == 1, "the task should be published once"
    assert publish.call_args.kwargs["correlation_id"] == "rpc-publisher-task-id", (
        "the publishing RPC app must preserve its task ID regardless of registry "
        "ownership"
    )


def test_configured_app_uses_cached_backend_verdict_without_global_lookup(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configured task publishing should use its app cache, not current_app."""
    celery_app = Celery(
        "configured-cache-publish-app",
        backend="cache+memory://",
        broker="memory://",
    )

    @celery_app.task(name="configured-cache-publish-task", shared=False)
    def configured_cache_publish_task() -> None:
        """Provide a task published by the configured app."""

    backend = celery_app.backend
    original_as_uri = mock.Mock(wraps=backend.as_uri)
    monkeypatch.setattr(backend, "as_uri", original_as_uri)
    configure_celery_correlation(celery_app)
    original_as_uri.assert_called_once()
    changed_as_uri = mock.Mock(return_value="rpc://")
    monkeypatch.setattr(backend, "as_uri", changed_as_uri)
    current_result_backend_uses_rpc = mock.Mock(return_value=False)
    monkeypatch.setattr(
        "falcon_correlate.celery._current_result_backend_uses_rpc",
        current_result_backend_uses_rpc,
    )

    with mock.patch("kombu.Producer.publish", autospec=True) as publish:

        def _logic() -> None:
            """Exercise publishing through the configured Celery app."""
            correlation_id_var.set("request-correlation-id")
            configured_cache_publish_task.apply_async()

        isolated_context(_logic)

    current_result_backend_uses_rpc.assert_not_called()
    changed_as_uri.assert_not_called()
    assert publish.call_args.kwargs["correlation_id"] == "request-correlation-id", (
        "configured publishing should use the cached backend verdict"
    )


def test_handler_falls_back_when_no_configured_app_owns_task(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unowned task names should retain the active-app compatibility fallback."""
    properties = {"correlation_id": "celery-task-id"}
    result_backend_lookup_count = 0

    def _current_result_backend_uses_rpc() -> bool:
        """Record use of the active-app compatibility fallback."""
        nonlocal result_backend_lookup_count
        result_backend_lookup_count += 1
        return True

    monkeypatch.setattr(
        "falcon_correlate.celery._current_result_backend_uses_rpc",
        _current_result_backend_uses_rpc,
    )

    def _logic() -> None:
        """Exercise the fallback path from an isolated context."""
        correlation_id_var.set("request-correlation-id")
        propagate_correlation_id_to_celery(
            sender="unconfigured-publish-task",
            properties=properties,
        )

    isolated_context(_logic)

    assert result_backend_lookup_count == 1, (
        "unowned tasks should consult the active-app fallback once"
    )
    assert properties["correlation_id"] == "celery-task-id", (
        "RPC fallback should preserve Celery task-ID correlation"
    )
