"""Unit tests for Celery correlation ID publish propagation."""

from __future__ import annotations

import typing as typ

import pytest

celery = pytest.importorskip("celery")

from celery.signals import before_task_publish  # noqa: E402

from falcon_correlate import correlation_id_var  # noqa: E402
from falcon_correlate.celery import (  # noqa: E402
    _maybe_connect_celery_publish_signal,
    propagate_correlation_id_to_celery,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc


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
        pytest.param(
            "",
            "celery-task-id",
            id="leaves_unchanged_when_context_is_empty_string",
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


def test_handler_preserves_task_id_correlation_for_rpc_result_backend(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RPC result backends must keep Celery's task-id correlation contract."""
    properties: dict[str, str] = {
        "correlation_id": "celery-task-id",
        "reply_to": "reply-queue",
    }

    monkeypatch.setattr(
        "falcon_correlate.celery._current_result_backend_uses_rpc",
        lambda: True,
    )

    def _logic() -> None:
        correlation_id_var.set("request-correlation-id")
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
    """Calling the connection helper should register the signal handler."""
    _maybe_connect_celery_publish_signal()

    receivers = typ.cast(
        "list[tuple[object, object]]",
        before_task_publish.receivers,
    )
    assert any(
        receiver_func is propagate_correlation_id_to_celery
        for _, receiver_func in receivers
    ), "propagate_correlation_id_to_celery not found in before_task_publish receivers"


def test_signal_connection_is_idempotent_across_reload(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
) -> None:
    """Test idempotency of the connection helper."""
    probe_calls: list[str] = []
    probe_dispatch_uid = "test_probe_publish_receiver"

    def probe_receiver(**kwargs: object) -> None:
        properties = typ.cast("dict[str, str] | None", kwargs.get("properties"))
        if properties is None:
            return

        probe_calls.append(properties["correlation_id"])

    def _send_signal() -> tuple[dict[str, str], list[tuple[object, object]]]:
        properties = {
            "correlation_id": "celery-task-id",
            "reply_to": "reply-queue",
        }
        signal_responses: list[tuple[object, object]] = []

        def _logic() -> None:
            correlation_id_var.set("request-correlation-id")
            nonlocal signal_responses
            signal_responses = before_task_publish.send(
                sender="test-sender",
                headers={},
                body=(),
                properties=properties,
            )

        isolated_context(_logic)
        return properties, signal_responses

    def _count_integration_receivers(
        signal_responses: list[tuple[object, object]],
    ) -> int:
        return sum(
            1
            for receiver, _ in signal_responses
            if getattr(receiver, "__module__", None) == "falcon_correlate.celery"
            and getattr(receiver, "__name__", None)
            == "propagate_correlation_id_to_celery"
        )

    try:
        _maybe_connect_celery_publish_signal()
        before_task_publish.connect(
            probe_receiver,
            dispatch_uid=probe_dispatch_uid,
            weak=False,
        )
        initial_properties, initial_responses = _send_signal()
        assert initial_properties["correlation_id"] == "request-correlation-id"
        assert len(probe_calls) == 1
        assert _count_integration_receivers(initial_responses) == 1

        _maybe_connect_celery_publish_signal()

        probe_calls.clear()
        reloaded_properties, reloaded_responses = _send_signal()
        assert reloaded_properties["correlation_id"] == "request-correlation-id"
        assert len(probe_calls) == 1
        assert _count_integration_receivers(reloaded_responses) == 1
    finally:
        before_task_publish.disconnect(dispatch_uid=probe_dispatch_uid)


def test_publish_signal_handler_is_exported_from_package_root() -> None:
    """The Celery publish handler should be re-exported from the package root."""
    import falcon_correlate

    assert "propagate_correlation_id_to_celery" in falcon_correlate.__all__
    assert (
        falcon_correlate.propagate_correlation_id_to_celery
        is propagate_correlation_id_to_celery
    )
