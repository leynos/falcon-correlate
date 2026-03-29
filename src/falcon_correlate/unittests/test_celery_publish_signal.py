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


@pytest.mark.parametrize(
    ("context_value", "expected_correlation_id"),
    [
        pytest.param(
            "request-correlation-id",
            "request-correlation-id",
            id="overwrites_when_context_is_set",
        ),
        pytest.param(
            None,
            "celery-task-id",
            id="leaves_unchanged_when_context_is_empty",
        ),
    ],
)
def test_handler_updates_publish_correlation_id(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    context_value: str | None,
    expected_correlation_id: str,
) -> None:
    """Publish properties should reflect the ambient correlation ID policy."""
    properties: dict[str, str] = {
        "correlation_id": "celery-task-id",
        "reply_to": "reply-queue",
    }

    def _logic() -> None:
        correlation_id_var.set(context_value)
        propagate_correlation_id_to_celery(properties=properties)

    isolated_context(_logic)

    assert properties == {
        "correlation_id": expected_correlation_id,
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
