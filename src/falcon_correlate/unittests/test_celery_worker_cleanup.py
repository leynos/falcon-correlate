"""Direct unit tests for the Celery worker correlation cleanup handler.

These tests call the cleanup helper directly rather than through configured
Celery signals. Dispatch through ``task_postrun`` adds no store states beyond
those the helper can be handed here, so direct calls give stronger and
cheaper evidence for the token-stack invariants.
"""

from __future__ import annotations

import typing as typ

import pytest

from falcon_correlate import (
    clear_correlation_id_in_worker,
    correlation_id_var,
    setup_correlation_id_in_worker,
)
from falcon_correlate._celery_worker_signals import (
    _CORRELATION_ID_CONTEXT_KEY,
    _celery_context_tokens,
)
from falcon_correlate.unittests.celery_worker_helpers import build_task

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from falcon_correlate._celery_worker_signals import _CeleryContextTokens


@pytest.mark.parametrize(
    "stored_state",
    [
        pytest.param({}, id="empty-store"),
        pytest.param(
            {_CORRELATION_ID_CONTEXT_KEY: []},
            id="empty-correlation-stack",
        ),
        pytest.param({"unrelated": []}, id="unrelated-key-only"),
    ],
)
def test_clear_handler_is_noop_for_stores_without_reset_tokens(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    stored_state: _CeleryContextTokens,
) -> None:
    """Cleanup should ignore stores that hold no correlation reset tokens.

    A non-empty store without the correlation stack exercises the defensive
    ``get`` default: cleanup must not raise and must leave the store untouched.
    """
    ambient_correlation_id = "ambient-correlation-id"

    def _logic() -> None:
        """Exercise the isolated test scenario."""
        correlation_id_var.set(ambient_correlation_id)
        _celery_context_tokens.set(stored_state)

        clear_correlation_id_in_worker(task=build_task())

        assert correlation_id_var.get() == ambient_correlation_id, (
            "cleanup without a reset token should preserve the ambient ID"
        )
        assert _celery_context_tokens.get(None) == stored_state, (
            "cleanup without a reset token should leave the store unchanged"
        )

    isolated_context(_logic)


def test_clear_handler_is_noop_after_exhausting_the_token_stack(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
) -> None:
    """A second cleanup after the last token is popped should do nothing."""

    def _logic() -> None:
        """Exercise the isolated test scenario."""
        task = build_task(correlation_id="worker-correlation-id")
        correlation_id_var.set("ambient-correlation-id")
        setup_correlation_id_in_worker(task=task)
        clear_correlation_id_in_worker(task=task)
        assert _celery_context_tokens.get(None) is None, (
            "the final cleanup should remove the exhausted token store"
        )

        clear_correlation_id_in_worker(task=task)

        assert correlation_id_var.get() == "ambient-correlation-id", (
            "cleanup without a token should preserve the restored ambient ID"
        )
        assert _celery_context_tokens.get(None) is None, (
            "cleanup without a token should keep the store exhausted"
        )

    isolated_context(_logic)


def test_clear_handler_preserves_unrelated_store_entries_while_unwinding(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
) -> None:
    """Cleanup should remove only the exhausted correlation stack entry."""
    outer_task = build_task(correlation_id="outer-worker-correlation-id")
    inner_task = build_task(correlation_id="inner-worker-correlation-id")
    unrelated_entry = ["retained"]

    def _logic() -> None:
        """Exercise the isolated test scenario."""
        correlation_id_var.set("ambient-correlation-id")
        _celery_context_tokens.set(
            typ.cast("_CeleryContextTokens", {"unrelated": unrelated_entry}),
        )
        setup_correlation_id_in_worker(task=outer_task)
        setup_correlation_id_in_worker(task=inner_task)

        clear_correlation_id_in_worker(task=inner_task)

        stored_tokens = _celery_context_tokens.get(None)
        assert stored_tokens is not None, "expected stored_tokens not to be None"
        assert set(stored_tokens) == {"unrelated", _CORRELATION_ID_CONTEXT_KEY}, (
            "inner cleanup should retain the outer token and unrelated entry"
        )
        assert stored_tokens["unrelated"] is unrelated_entry, (
            "inner cleanup should preserve the unrelated entry object"
        )
        assert len(stored_tokens[_CORRELATION_ID_CONTEXT_KEY]) == 1, (
            "inner cleanup should leave exactly the outer token"
        )
        assert correlation_id_var.get() == "outer-worker-correlation-id", (
            "inner cleanup should restore the outer correlation ID"
        )

        clear_correlation_id_in_worker(task=outer_task)

        assert _celery_context_tokens.get(None) == {"unrelated": unrelated_entry}, (
            "outer cleanup should remove only the correlation stack entry"
        )
        assert correlation_id_var.get() == "ambient-correlation-id", (
            "outer cleanup should restore the ambient correlation ID"
        )

    isolated_context(_logic)


def test_clear_handler_resets_context_to_previous_value(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
) -> None:
    """Worker cleanup should restore any pre-existing ambient correlation ID."""
    task = build_task(correlation_id="worker-correlation-id")

    def _logic() -> None:
        """Exercise the isolated test scenario."""
        correlation_id_var.set("ambient-correlation-id")
        setup_correlation_id_in_worker(task=task)

        clear_correlation_id_in_worker(task=task)

        assert correlation_id_var.get() == "ambient-correlation-id", (
            "cleanup should restore the ambient correlation ID"
        )
        assert _celery_context_tokens.get(None) is None, (
            "cleanup should remove the exhausted token store"
        )

    isolated_context(_logic)


def test_nested_worker_cleanup_restores_outer_then_ambient_context(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
) -> None:
    """Nested worker runs should unwind correlation IDs in LIFO order."""
    outer_task = build_task(correlation_id="outer-worker-correlation-id")
    inner_task = build_task(correlation_id="inner-worker-correlation-id")

    def _logic() -> None:
        """Exercise the isolated test scenario."""
        correlation_id_var.set("ambient-correlation-id")
        setup_correlation_id_in_worker(task=outer_task)
        setup_correlation_id_in_worker(task=inner_task)

        assert correlation_id_var.get() == "inner-worker-correlation-id", (
            "inner setup should bind the inner correlation ID"
        )

        clear_correlation_id_in_worker(task=inner_task)

        stored_tokens = _celery_context_tokens.get(None)
        assert correlation_id_var.get() == "outer-worker-correlation-id", (
            "inner cleanup should restore the outer correlation ID"
        )
        assert stored_tokens is not None, "expected stored_tokens not to be None"
        assert len(stored_tokens[_CORRELATION_ID_CONTEXT_KEY]) == 1, (
            "inner cleanup should leave exactly the outer token"
        )

        clear_correlation_id_in_worker(task=outer_task)

        assert correlation_id_var.get() == "ambient-correlation-id", (
            "outer cleanup should restore the ambient correlation ID"
        )
        assert _celery_context_tokens.get(None) is None, (
            "outer cleanup should remove the exhausted token store"
        )

    isolated_context(_logic)
