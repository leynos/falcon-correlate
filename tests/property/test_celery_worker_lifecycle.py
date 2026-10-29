"""Property tests for the Celery worker correlation context lifecycle."""

from __future__ import annotations

import contextvars
from types import SimpleNamespace

from hypothesis import example, given, settings
from hypothesis import strategies as st

from falcon_correlate import (
    clear_correlation_id_in_worker,
    correlation_id_var,
    setup_correlation_id_in_worker,
)
from falcon_correlate._celery_worker_signals import (
    _CORRELATION_ID_CONTEXT_KEY,
    _celery_context_tokens,
)

type _LifecycleOperation = tuple[str, object]

_AMBIENT_ID = "ambient-correlation-id"


@st.composite
def _lifecycle_operations(draw: st.DrawFn) -> list[_LifecycleOperation]:
    """Generate bounded worker setup and cleanup operations."""
    setup_values = st.one_of(
        st.text(min_size=1, max_size=12),
        st.just(""),
        st.none(),
        st.integers(),
    )
    operations = st.one_of(
        st.tuples(st.just("setup"), setup_values),
        st.tuples(st.just("setup-without-request"), st.none()),
        st.tuples(st.just("cleanup"), st.none()),
    )
    return draw(st.lists(operations, min_size=1, max_size=20))


@given(operations=_lifecycle_operations())
@example(
    operations=[
        ("setup", "outer-task-id"),
        ("setup-without-request", None),
        ("cleanup", None),
        ("cleanup", None),
    ],
)
@settings(max_examples=100)
def test_worker_setup_and_cleanup_follow_the_token_stack_model(
    operations: list[_LifecycleOperation],
) -> None:
    """Each operation agrees with the independently modelled token stack."""
    context = contextvars.Context()

    def exercise_sequence() -> None:
        correlation_id_var.set(_AMBIENT_ID)
        expected_value: str | None = _AMBIENT_ID
        previous_values: list[str | None] = []

        for operation_index, (operation, value) in enumerate(operations):
            match operation:
                case "setup":
                    if isinstance(value, str) and value:
                        previous_values.append(expected_value)
                        expected_value = value
                    setup_correlation_id_in_worker(
                        task=SimpleNamespace(
                            request=SimpleNamespace(correlation_id=value),
                        ),
                    )
                case "setup-without-request":
                    setup_correlation_id_in_worker(task=SimpleNamespace())
                case "cleanup":
                    clear_correlation_id_in_worker(task=SimpleNamespace())
                    if previous_values:
                        expected_value = previous_values.pop()

            assert correlation_id_var.get() == expected_value, (
                f"operation {operation_index} ({operation}, {value!r}) "
                f"should leave correlation ID {expected_value!r}, got "
                f"{correlation_id_var.get()!r}"
            )
            stored_tokens = _celery_context_tokens.get(None) or {}
            actual_depth = len(
                stored_tokens.get(_CORRELATION_ID_CONTEXT_KEY, []),
            )
            assert actual_depth == len(previous_values), (
                f"operation {operation_index} ({operation}, {value!r}) "
                f"should leave {len(previous_values)} reset tokens, got "
                f"{actual_depth}"
            )

    context.run(exercise_sequence)
