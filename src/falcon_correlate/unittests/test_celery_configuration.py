"""Unit tests for the public Celery configuration helper."""

from __future__ import annotations

import typing as typ

import pytest

celery = pytest.importorskip("celery")

from celery import Celery  # noqa: E402
from celery.signals import before_task_publish, task_postrun, task_prerun  # noqa: E402

from falcon_correlate.celery import (  # noqa: E402
    _BEFORE_TASK_PUBLISH_DISPATCH_UID,
    _TASK_POSTRUN_DISPATCH_UID,
    _TASK_PRERUN_DISPATCH_UID,
    clear_correlation_id_in_worker,
    configure_celery_correlation,
    propagate_correlation_id_to_celery,
    setup_correlation_id_in_worker,
)


class _SignalWithReceivers(typ.Protocol):
    """Structural type for Celery signal objects inspected by tests."""

    receivers: object


def _disconnect_integration_receivers() -> None:
    """Remove existing integration receivers by stable dispatch UID."""
    before_task_publish.disconnect(dispatch_uid=_BEFORE_TASK_PUBLISH_DISPATCH_UID)
    task_prerun.disconnect(dispatch_uid=_TASK_PRERUN_DISPATCH_UID)
    task_postrun.disconnect(dispatch_uid=_TASK_POSTRUN_DISPATCH_UID)


def _receiver_count(signal: _SignalWithReceivers, receiver: object) -> int:
    """Count live receivers matching a concrete function object."""
    receivers = typ.cast("list[tuple[object, object]]", signal.receivers)
    return sum(1 for _, receiver_func in receivers if receiver_func is receiver)


@pytest.fixture
def celery_app() -> Celery:
    """Build a minimal Celery app for configuration tests."""
    return Celery("unit-celery-configuration", broker="memory://")


def test_configure_celery_correlation_connects_all_supported_signals(
    celery_app: Celery,
) -> None:
    """The helper should reconnect publish and worker signal receivers."""
    _disconnect_integration_receivers()

    configure_celery_correlation(celery_app)

    assert (
        _receiver_count(
            before_task_publish,
            propagate_correlation_id_to_celery,
        )
        == 1
    )
    assert _receiver_count(task_prerun, setup_correlation_id_in_worker) == 1
    assert _receiver_count(task_postrun, clear_correlation_id_in_worker) == 1


def test_configure_celery_correlation_is_idempotent(celery_app: Celery) -> None:
    """Repeated configuration should not duplicate signal receivers."""
    _disconnect_integration_receivers()

    configure_celery_correlation(celery_app)
    configure_celery_correlation(celery_app)

    assert (
        _receiver_count(
            before_task_publish,
            propagate_correlation_id_to_celery,
        )
        == 1
    )
    assert _receiver_count(task_prerun, setup_correlation_id_in_worker) == 1
    assert _receiver_count(task_postrun, clear_correlation_id_in_worker) == 1


def test_configure_celery_correlation_returns_app_instance(
    celery_app: Celery,
) -> None:
    """Application factories should be able to return the configured app."""
    assert configure_celery_correlation(celery_app) is celery_app


def test_configure_celery_correlation_is_exported_from_package_root() -> None:
    """The public helper should be discoverable from falcon_correlate."""
    import falcon_correlate

    assert "configure_celery_correlation" in falcon_correlate.__all__
    assert falcon_correlate.configure_celery_correlation is configure_celery_correlation
