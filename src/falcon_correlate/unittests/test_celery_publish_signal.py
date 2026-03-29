"""Unit tests for Celery correlation ID publish propagation."""

from __future__ import annotations

import importlib
import typing as typ

import pytest

celery = pytest.importorskip("celery")

from celery.signals import before_task_publish  # noqa: E402

from falcon_correlate import correlation_id_var  # noqa: E402
from falcon_correlate.celery import (  # noqa: E402
    _BEFORE_TASK_PUBLISH_DISPATCH_UID,
    propagate_correlation_id_to_celery,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    _SignalReceiverEntry = tuple[tuple[object, object], object]


def _count_connected_receivers(dispatch_uid: str) -> int:
    """Return how many signal receivers are connected for *dispatch_uid*."""
    receivers = typ.cast(
        "list[_SignalReceiverEntry]",
        before_task_publish.receivers or [],
    )
    return sum(
        1 for (lookup_key, _receiver) in receivers if lookup_key[0] == dispatch_uid
    )


def test_handler_overwrites_publish_correlation_id_when_context_is_set(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
) -> None:
    """Ambient request correlation ID should replace Celery's publish value."""
    properties = {
        "correlation_id": "celery-task-id",
        "reply_to": "reply-queue",
    }

    def _logic() -> None:
        correlation_id_var.set("request-correlation-id")
        propagate_correlation_id_to_celery(properties=properties)

    isolated_context(_logic)

    assert properties == {
        "correlation_id": "request-correlation-id",
        "reply_to": "reply-queue",
    }


def test_handler_leaves_properties_unchanged_when_context_is_empty(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
) -> None:
    """No ambient correlation ID should leave Celery publish properties alone."""
    properties = {
        "correlation_id": "celery-task-id",
        "reply_to": "reply-queue",
    }

    def _logic() -> None:
        correlation_id_var.set(None)
        propagate_correlation_id_to_celery(properties=properties)

    isolated_context(_logic)

    assert properties == {
        "correlation_id": "celery-task-id",
        "reply_to": "reply-queue",
    }


def test_handler_tolerates_missing_properties_mapping(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
) -> None:
    """A missing Celery properties mapping should be treated as a no-op."""

    def _logic() -> None:
        correlation_id_var.set("request-correlation-id")
        propagate_correlation_id_to_celery(properties=None)

    isolated_context(_logic)


def test_signal_handler_is_connected_to_before_task_publish() -> None:
    """Importing the module should register the publish signal handler once."""
    assert _count_connected_receivers(_BEFORE_TASK_PUBLISH_DISPATCH_UID) == 1


def test_signal_connection_is_idempotent_across_reload() -> None:
    """Reloading the module should not duplicate the signal registration."""
    assert _count_connected_receivers(_BEFORE_TASK_PUBLISH_DISPATCH_UID) == 1

    import falcon_correlate.celery as celery_integration

    importlib.reload(celery_integration)

    assert _count_connected_receivers(_BEFORE_TASK_PUBLISH_DISPATCH_UID) == 1


def test_publish_signal_handler_is_exported_from_package_root() -> None:
    """The Celery publish handler should be re-exported from the package root."""
    import falcon_correlate

    assert "propagate_correlation_id_to_celery" in falcon_correlate.__all__
    assert (
        falcon_correlate.propagate_correlation_id_to_celery
        is propagate_correlation_id_to_celery
    )
