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
type _ModelEntry = tuple[bool, str | None]

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


class _TokenStackModel:
    """Independent model of the paired context-token stack.

    An entry pairs an ``is_placeholder`` flag with the prior value. A real
    token stores the value to restore; a placeholder stores ``None`` and is
    discarded without changing the modelled correlation ID.
    """

    def __init__(self, ambient_id: str) -> None:
        """Start the model with an ambient correlation ID."""
        self.value: str | None = ambient_id
        self.entries: list[_ModelEntry] = []

    def record_setup(self, correlation_id: object) -> None:
        """Record one setup entry for an accepted or unusable ID."""
        if isinstance(correlation_id, str) and correlation_id:
            self.entries.append((False, self.value))
            self.value = correlation_id
        else:
            self.entries.append((True, None))

    def record_cleanup(self) -> None:
        """Record one cleanup, restoring the prior value only for a real token."""
        if not self.entries:
            return
        is_placeholder, previous = self.entries.pop()
        if not is_placeholder:
            self.value = previous


def _assert_matches_model(
    model: _TokenStackModel,
    operation_index: int,
    operation: str,
    value: object,
) -> None:
    """Assert the live context and token depth agree with the model."""
    operation_label = f"operation {operation_index} ({operation}, {value!r})"
    actual_value = correlation_id_var.get()
    failure_message = (
        f"{operation_label} should leave correlation ID {model.value!r}, "
        f"got {actual_value!r}"
    )
    assert actual_value == model.value, failure_message
    stored_tokens = _celery_context_tokens.get(None)
    if model.entries:
        failure_message = (
            f"{operation_label} should retain {len(model.entries)} stack entries, "
            "got no store"
        )
        assert stored_tokens is not None, failure_message
        failure_message = (
            f"{operation_label} should retain only the correlation stack, got "
            f"{sorted(stored_tokens)}"
        )
        assert set(stored_tokens) == {_CORRELATION_ID_CONTEXT_KEY}, failure_message
        actual_depth = len(stored_tokens[_CORRELATION_ID_CONTEXT_KEY])
        failure_message = (
            f"{operation_label} should leave {len(model.entries)} stack entries, "
            f"got {actual_depth}"
        )
        assert actual_depth == len(model.entries), failure_message
    else:
        failure_message = (
            f"{operation_label} should clear the exhausted token store, got "
            f"{stored_tokens!r}"
        )
        assert stored_tokens is None, failure_message


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
        """Replay the generated operations, then unwind any leftover entries."""
        correlation_id_var.set(_AMBIENT_ID)
        model = _TokenStackModel(_AMBIENT_ID)

        for operation_index, (operation, value) in enumerate(operations):
            match operation:
                case "setup":
                    model.record_setup(value)
                    setup_correlation_id_in_worker(
                        task=SimpleNamespace(
                            request=SimpleNamespace(correlation_id=value),
                        ),
                    )
                case "setup-without-request":
                    model.record_setup(None)
                    setup_correlation_id_in_worker(task=SimpleNamespace())
                case "cleanup":
                    model.record_cleanup()
                    clear_correlation_id_in_worker(task=SimpleNamespace())

            _assert_matches_model(model, operation_index, operation, value)

        unwind_index = len(operations)
        while model.entries:
            model.record_cleanup()
            clear_correlation_id_in_worker(task=SimpleNamespace())
            _assert_matches_model(model, unwind_index, "unwind", None)
            unwind_index += 1

        failure_message = (
            "unwinding every entry should restore the ambient correlation ID"
        )
        assert correlation_id_var.get() == _AMBIENT_ID, failure_message
        failure_message = "unwinding every entry should exhaust the token store"
        assert _celery_context_tokens.get(None) is None, failure_message

    context.run(exercise_sequence)
