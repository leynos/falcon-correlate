"""Unit tests for Celery worker correlation ID signal handlers."""

from __future__ import annotations

import typing as typ
from types import SimpleNamespace

import pytest

celery = pytest.importorskip("celery")

from celery.signals import task_postrun, task_prerun  # noqa: E402

from falcon_correlate import (  # noqa: E402
    clear_correlation_id_in_worker,
    correlation_id_var,
    setup_correlation_id_in_worker,
)
from falcon_correlate.celery import (  # noqa: E402
    _CORRELATION_ID_CONTEXT_KEY,
    _celery_context_tokens,
    _maybe_connect_celery_worker_signals,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc


def _build_task(*, correlation_id: str | None = None) -> object:
    """Build a minimal Celery-like task object for signal handler tests."""
    return SimpleNamespace(
        request=SimpleNamespace(correlation_id=correlation_id),
    )


def test_setup_handler_exposes_task_request_correlation_id(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
) -> None:
    """Worker setup should bind the task request correlation ID into context."""
    task = _build_task(correlation_id="worker-correlation-id")

    def _logic() -> None:
        setup_correlation_id_in_worker(task=task)

        stored_tokens = _celery_context_tokens.get(None)
        assert correlation_id_var.get() == "worker-correlation-id"
        assert stored_tokens is not None
        assert _CORRELATION_ID_CONTEXT_KEY in stored_tokens

    isolated_context(_logic)


def test_setup_handler_is_noop_without_task_request_correlation_id(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
) -> None:
    """Worker setup should ignore tasks that do not carry a correlation ID."""
    task = _build_task(correlation_id=None)

    def _logic() -> None:
        setup_correlation_id_in_worker(task=task)

        assert correlation_id_var.get() is None
        assert _celery_context_tokens.get(None) is None

    isolated_context(_logic)


def test_clear_handler_resets_context_to_previous_value(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
) -> None:
    """Worker cleanup should restore any pre-existing ambient correlation ID."""
    task = _build_task(correlation_id="worker-correlation-id")

    def _logic() -> None:
        correlation_id_var.set("ambient-correlation-id")
        setup_correlation_id_in_worker(task=task)

        clear_correlation_id_in_worker(task=task)

        assert correlation_id_var.get() == "ambient-correlation-id"
        assert _celery_context_tokens.get(None) is None

    isolated_context(_logic)


def test_clear_handler_is_noop_without_stored_token(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
) -> None:
    """Worker cleanup should tolerate missing setup state."""

    def _logic() -> None:
        clear_correlation_id_in_worker(task=_build_task())

        assert correlation_id_var.get() is None
        assert _celery_context_tokens.get(None) is None

    isolated_context(_logic)


def test_worker_signal_connection_is_idempotent() -> None:
    """Connecting worker signals twice should still yield one receiver each."""
    _maybe_connect_celery_worker_signals()
    _maybe_connect_celery_worker_signals()

    prerun_receivers = typ.cast(
        "list[tuple[object, object]]",
        task_prerun.receivers,
    )
    postrun_receivers = typ.cast(
        "list[tuple[object, object]]",
        task_postrun.receivers,
    )

    assert (
        sum(
            1
            for _, receiver_func in prerun_receivers
            if receiver_func is setup_correlation_id_in_worker
        )
        == 1
    )
    assert (
        sum(
            1
            for _, receiver_func in postrun_receivers
            if receiver_func is clear_correlation_id_in_worker
        )
        == 1
    )


def test_worker_signal_handlers_are_exported_from_package_root() -> None:
    """The worker handlers should be re-exported from the package root."""
    import falcon_correlate

    assert "setup_correlation_id_in_worker" in falcon_correlate.__all__
    assert "clear_correlation_id_in_worker" in falcon_correlate.__all__
    assert (
        falcon_correlate.setup_correlation_id_in_worker
        is setup_correlation_id_in_worker
    )
    assert (
        falcon_correlate.clear_correlation_id_in_worker
        is clear_correlation_id_in_worker
    )
