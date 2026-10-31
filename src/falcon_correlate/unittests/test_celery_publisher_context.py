"""Tests for configured Celery publisher identity and verdict caching."""

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
        set_as_current=False,
    )
    non_rpc_app = Celery(
        "configured-non-rpc-publish-app",
        backend="cache+memory://",
        broker="memory://",
        set_as_current=False,
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
        set_as_current=False,
    )
    non_rpc_task_owner = Celery(
        "configured-non-rpc-task-owner",
        backend="cache+memory://",
        broker="memory://",
        set_as_current=False,
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


def test_configured_app_caches_backend_verdict_on_first_publish(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Publishing caches the app verdict without consulting ``current_app``."""
    celery_app = Celery(
        "configured-cache-publish-app",
        backend="cache+memory://",
        broker="memory://",
        set_as_current=False,
    )

    @celery_app.task(name="configured-cache-publish-task", shared=False)
    def configured_cache_publish_task() -> None:
        """Provide a task published by the configured app."""

    backend = celery_app.backend
    original_as_uri = mock.Mock(wraps=backend.as_uri)
    monkeypatch.setattr(backend, "as_uri", original_as_uri)
    configure_celery_correlation(celery_app)
    original_as_uri.assert_not_called()
    changed_as_uri = mock.Mock(return_value="rpc://")
    current_result_backend_uses_rpc = mock.Mock(return_value=False)
    monkeypatch.setattr(
        "falcon_correlate.celery._current_result_backend_uses_rpc",
        current_result_backend_uses_rpc,
    )

    with mock.patch("kombu.Producer.publish", autospec=True) as publish:

        def _logic() -> None:
            """Exercise cache creation and reuse through the configured app."""
            correlation_id_var.set("request-correlation-id")
            configured_cache_publish_task.apply_async()
            monkeypatch.setattr(backend, "as_uri", changed_as_uri)
            configured_cache_publish_task.apply_async()

        isolated_context(_logic)

    current_result_backend_uses_rpc.assert_not_called()
    original_as_uri.assert_called_once()
    changed_as_uri.assert_not_called()
    assert publish.call_count == 2, "both configured-app tasks should publish"
    assert [call.kwargs["correlation_id"] for call in publish.call_args_list] == [
        "request-correlation-id",
        "request-correlation-id",
    ], "repeated publishing should keep using the first cached verdict"


def test_publish_preserves_task_id_and_logs_sender_when_inspection_fails(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed publish-path inspection preserves the task ID and its sender."""
    celery_app = Celery(
        "failing-inspection-publish-app",
        backend="cache+memory://",
        broker="memory://",
        set_as_current=False,
    )

    @celery_app.task(name="failing-inspection-publish-task", shared=False)
    def failing_inspection_publish_task() -> None:
        """Provide the task whose publish inspection fails."""

    celery_app.finalize()
    monkeypatch.setattr(
        celery_app.backend,
        "as_uri",
        mock.Mock(side_effect=RuntimeError("publish inspection failed")),
    )
    configure_celery_correlation(celery_app)
    published_task_ids: list[str] = []

    with (
        caplog.at_level(logging.DEBUG, logger="falcon_correlate.celery"),
        mock.patch("kombu.Producer.publish", autospec=True) as publish,
    ):

        def _logic() -> None:
            """Publish the task with an ambient request correlation ID."""
            correlation_id_var.set("request-correlation-id")
            published_task_ids.append(failing_inspection_publish_task.apply_async().id)

        isolated_context(_logic)

    assert publish.call_count == 1, "the task should be published once"
    assert publish.call_args.kwargs["correlation_id"] == published_task_ids[0], (
        "an inconclusive backend inspection must preserve the task ID"
    )
    diagnostics = [
        record.getMessage()
        for record in caplog.records
        if record.name == "falcon_correlate.celery" and record.levelno == logging.DEBUG
    ]
    assert diagnostics == [
        (
            "Unable to inspect Celery result backend URI for publishing task "
            "'failing-inspection-publish-task'; preserving task ID."
        )
    ], "the publish diagnostic should identify the signal sender"


def test_publish_replaces_correlation_id_when_backend_lacks_as_uri(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A backend without a URI accessor counts as a non-RPC verdict."""
    celery_app = Celery(
        "missing-as-uri-publish-app",
        backend="cache+memory://",
        broker="memory://",
        set_as_current=False,
    )

    @celery_app.task(name="missing-as-uri-publish-task", shared=False)
    def missing_as_uri_publish_task() -> None:
        """Provide the task published against a backend without ``as_uri``."""

    celery_app.finalize()
    backend_type = type(celery_app.backend)
    uri_owners = [
        backend_class
        for backend_class in backend_type.__mro__
        if "as_uri" in vars(backend_class)
    ]
    assert uri_owners, "the test requires a backend class that defines as_uri"
    for backend_class in uri_owners:
        monkeypatch.delattr(backend_class, "as_uri")
    configure_celery_correlation(celery_app)

    with mock.patch("kombu.Producer.publish", autospec=True) as publish:

        def _logic() -> None:
            """Publish the task with an ambient request correlation ID."""
            correlation_id_var.set("request-correlation-id")
            missing_as_uri_publish_task.apply_async()

        isolated_context(_logic)

    assert publish.call_count == 1, "the task should be published once"
    assert publish.call_args.kwargs["correlation_id"] == "request-correlation-id", (
        "a backend without as_uri should accept the request correlation ID"
    )


def test_cached_rpc_verdict_is_reused_after_backend_changes(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cached RPC verdict must survive later backend changes."""
    celery_app = Celery(
        "cached-rpc-verdict-app",
        backend="rpc://",
        broker="memory://",
        set_as_current=False,
    )

    @celery_app.task(name="cached-rpc-verdict-task", shared=False)
    def cached_rpc_verdict_task() -> None:
        """Provide the task whose RPC verdict is cached on first publish."""

    celery_app.finalize()
    backend = celery_app.backend
    original_as_uri = mock.Mock(wraps=backend.as_uri)
    monkeypatch.setattr(backend, "as_uri", original_as_uri)
    changed_as_uri = mock.Mock(return_value="cache+memory://")
    configure_celery_correlation(celery_app)
    published_task_ids: list[str] = []

    with mock.patch("kombu.Producer.publish", autospec=True) as publish:

        def _logic() -> None:
            """Publish once for the verdict, then twice after a backend change."""
            correlation_id_var.set("request-correlation-id")
            published_task_ids.append(cached_rpc_verdict_task.apply_async().id)
            monkeypatch.setattr(backend, "as_uri", changed_as_uri)
            published_task_ids.append(cached_rpc_verdict_task.apply_async().id)
            published_task_ids.append(cached_rpc_verdict_task.apply_async().id)

        isolated_context(_logic)

    original_as_uri.assert_called_once()
    changed_as_uri.assert_not_called()
    assert publish.call_count == 3, "all task publishes should reach Kombu"
    assert [call.kwargs["correlation_id"] for call in publish.call_args_list] == (
        published_task_ids
    ), "the cached RPC verdict should keep preserving every task ID"


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
