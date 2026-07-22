"""Unit tests for the public Celery configuration helper."""

from __future__ import annotations

import concurrent.futures
import threading
import typing as typ
from types import SimpleNamespace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

celery = pytest.importorskip("celery")

from celery import Celery  # noqa: E402
from celery.signals import before_task_publish, task_postrun, task_prerun  # noqa: E402

from falcon_correlate.celery import (  # noqa: E402
    _BEFORE_TASK_PUBLISH_DISPATCH_UID,
    _TASK_POSTRUN_DISPATCH_UID,
    _TASK_PRERUN_DISPATCH_UID,
    clear_correlation_id_in_worker,
    configure_celery_correlation,
    correlation_id_var,
    propagate_correlation_id_to_celery,
    setup_correlation_id_in_worker,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc


class _SignalWithReceivers(typ.Protocol):
    """Structural type for Celery signal objects inspected by tests."""

    receivers: object


def _disconnect_integration_receivers() -> None:
    """Remove existing integration receivers by stable dispatch UID."""
    before_task_publish.disconnect(dispatch_uid=_BEFORE_TASK_PUBLISH_DISPATCH_UID)
    task_prerun.disconnect(dispatch_uid=_TASK_PRERUN_DISPATCH_UID)
    task_postrun.disconnect(dispatch_uid=_TASK_POSTRUN_DISPATCH_UID)


def _receiver_count(signal: _SignalWithReceivers, receiver: object) -> int:
    """Count live receivers matching a concrete function object.

    Returns
    -------
    int
        The value produced for the test scenario.

    """
    receivers = typ.cast("list[tuple[object, object]]", signal.receivers)
    return sum(1 for _, receiver_func in receivers if receiver_func is receiver)


def _assert_all_signals_connected_once() -> None:
    """Assert each integration signal has exactly one live receiver."""
    for signal, receiver in (
        (
            before_task_publish,
            propagate_correlation_id_to_celery,
        ),
        (task_prerun, setup_correlation_id_in_worker),
        (task_postrun, clear_correlation_id_in_worker),
    ):
        assert _receiver_count(signal, receiver) == 1


class _TaskLike:
    """Minimal hashable task object for Celery signal dispatch tests."""

    def __init__(self, *, correlation_id: str) -> None:
        """Initialize the test double."""
        self.request = SimpleNamespace(correlation_id=correlation_id)


@pytest.fixture
def celery_app() -> Celery:
    """Build a minimal Celery app for configuration tests.

    Returns
    -------
    Celery
        The value produced for the test scenario.

    """
    return Celery("unit-celery-configuration", broker="memory://")


def test_configure_celery_correlation_connects_all_supported_signals(
    celery_app: Celery,
) -> None:
    """The helper should reconnect publish and worker signal receivers."""
    _disconnect_integration_receivers()

    configure_celery_correlation(celery_app)

    _assert_all_signals_connected_once()


def test_configure_celery_correlation_is_safe_under_concurrent_calls(
    celery_app: Celery,
) -> None:
    """Concurrent configuration calls should still connect each signal once."""
    _disconnect_integration_receivers()
    barrier = threading.Barrier(4)

    def _configure_from_thread() -> None:
        """Configure Celery correlation from a worker thread."""
        barrier.wait()
        configure_celery_correlation(celery_app)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(_configure_from_thread) for _ in range(4)]
        for future in futures:
            future.result(timeout=5)

    _assert_all_signals_connected_once()


def test_configure_celery_correlation_is_idempotent(celery_app: Celery) -> None:
    """Repeated configuration should not duplicate signal receivers."""
    _disconnect_integration_receivers()

    configure_celery_correlation(celery_app)
    configure_celery_correlation(celery_app)

    _assert_all_signals_connected_once()


@given(call_count=st.integers(min_value=1, max_value=10))
@settings(max_examples=50)
def test_configure_celery_correlation_idempotent_for_n_calls(
    call_count: int,
) -> None:
    """Calling configure_celery_correlation n times must not duplicate receivers.

    The dispatch UID guard guarantees idempotence regardless of call count.
    """
    app = Celery("prop-celery-idempotence", broker="memory://")
    _disconnect_integration_receivers()

    for _ in range(call_count):
        configure_celery_correlation(app)

    _assert_all_signals_connected_once()
    _disconnect_integration_receivers()


@given(
    correlation_ids=st.lists(
        st.text(
            min_size=1,
            max_size=64,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        ),
        min_size=1,
        max_size=8,
    )
)
@settings(max_examples=50)
def test_context_token_stack_unwinds_lifo(correlation_ids: list[str]) -> None:
    """setup/clear functions must unwind the ContextVar stack in LIFO order.

    For any sequence of correlation IDs pushed via setup_correlation_id_in_worker,
    successive calls to clear_correlation_id_in_worker must restore each prior
    value in reverse order, ending with None.
    """
    tasks = [_TaskLike(correlation_id=cid) for cid in correlation_ids]

    for task in tasks:
        setup_correlation_id_in_worker(task=task)

    for expected in reversed(correlation_ids):
        assert correlation_id_var.get() == expected
        clear_correlation_id_in_worker()

    assert correlation_id_var.get() is None


def test_configure_celery_correlation_isolates_nested_task_context(
    celery_app: Celery,
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
) -> None:
    """Configured worker signals should unwind nested task contexts in order."""
    _disconnect_integration_receivers()
    configure_celery_correlation(celery_app)
    outer_task = _TaskLike(correlation_id="outer-worker-correlation-id")
    inner_task = _TaskLike(correlation_id="inner-worker-correlation-id")

    def _logic() -> None:
        """Exercise the isolated test scenario."""
        assert correlation_id_var.get() is None

        task_prerun.send(sender=outer_task, task=outer_task, args=(), kwargs={})
        assert correlation_id_var.get() == "outer-worker-correlation-id"

        task_prerun.send(sender=inner_task, task=inner_task, args=(), kwargs={})
        assert correlation_id_var.get() == "inner-worker-correlation-id"

        task_postrun.send(
            sender=inner_task,
            task=inner_task,
            args=(),
            kwargs={},
            retval=None,
            state="SUCCESS",
        )
        assert correlation_id_var.get() == "outer-worker-correlation-id"

        task_postrun.send(
            sender=outer_task,
            task=outer_task,
            args=(),
            kwargs={},
            retval=None,
            state="SUCCESS",
        )
        assert correlation_id_var.get() is None

    isolated_context(_logic)


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


def test_safe_connect_signal_logs_when_signal_missing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """_safe_connect_signal should emit a DEBUG message for a missing signal."""
    import logging

    from falcon_correlate.celery import _safe_connect_signal

    def fake_handler(**_: object) -> None:
        """Stand in for a Celery signal receiver."""
        return

    module_without_signal = object()

    with caplog.at_level(logging.DEBUG, logger="falcon_correlate.celery"):
        _safe_connect_signal(
            module_without_signal,
            "nonexistent_signal",
            fake_handler,
            "test.uid",
        )

    assert any("nonexistent_signal" in record.message for record in caplog.records)


def test_safe_connect_signal_logs_on_successful_connect(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """_safe_connect_signal should emit a DEBUG message on successful connect."""
    import logging

    from falcon_correlate.celery import _safe_connect_signal

    fake_uid = "falcon_correlate.test.debug_log_uid"

    def fake_handler(**_: object) -> None:
        """Stand in for a Celery signal receiver."""
        return

    fake_module = SimpleNamespace(before_task_publish=before_task_publish)

    try:
        with caplog.at_level(logging.DEBUG, logger="falcon_correlate.celery"):
            _safe_connect_signal(
                fake_module,
                "before_task_publish",
                fake_handler,
                fake_uid,
            )
        assert any(fake_uid in record.message for record in caplog.records)
    finally:
        before_task_publish.disconnect(dispatch_uid=fake_uid)


def test_safe_connect_signal_suppresses_invalid_receiver(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Invalid receiver signatures should remain an optional integration failure."""
    import logging

    from falcon_correlate.celery import _safe_connect_signal

    def reject_receiver(*_: object, **__: object) -> None:
        """Reject the receiver as Celery does for an invalid signature."""
        msg = "Signal receiver must accept keyword arguments"
        raise ValueError(msg)

    fake_module = SimpleNamespace(
        before_task_publish=SimpleNamespace(connect=reject_receiver)
    )

    with caplog.at_level(logging.DEBUG, logger="falcon_correlate.celery"):
        _safe_connect_signal(fake_module, "before_task_publish", lambda: None, "uid")

    assert any("invalid receiver" in record.message for record in caplog.records)


def test_safe_connect_signal_propagates_unexpected_failure() -> None:
    """Unexpected registration failures should remain visible to callers."""
    from falcon_correlate.celery import _safe_connect_signal

    def fail_connection(*_: object, **__: object) -> None:
        """Raise an unexpected registration failure."""
        msg = "unexpected registration failure"
        raise RuntimeError(msg)

    fake_module = SimpleNamespace(
        before_task_publish=SimpleNamespace(connect=fail_connection)
    )

    with pytest.raises(RuntimeError, match="unexpected registration failure"):
        _safe_connect_signal(fake_module, "before_task_publish", lambda: None, "uid")
