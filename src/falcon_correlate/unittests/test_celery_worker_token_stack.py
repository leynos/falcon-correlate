"""Regression tests for paired Celery worker token-stack entries.

A worker setup must push exactly one stack entry for every invocation, whether
or not the task carries a usable correlation ID. Cleanup pops exactly one
entry, so a nested task without an ID preserves the enclosing task's ID until
the enclosing cleanup runs.
"""

from __future__ import annotations

import typing as typ
from types import SimpleNamespace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

try:
    from celery import Celery
    from celery.signals import task_postrun, task_prerun
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
    clear_correlation_id_in_worker,
    configure_celery_correlation,
    correlation_id_var,
    setup_correlation_id_in_worker,
)
from falcon_correlate._celery_worker_signals import (  # ruff: ignore[module-import-not-at-top-of-file] -- dependency probe first.
    _CORRELATION_ID_CONTEXT_KEY,
    _celery_context_tokens,
)
from falcon_correlate.celery import (  # ruff: ignore[module-import-not-at-top-of-file] -- dependency probe first.
    _TASK_POSTRUN_DISPATCH_UID,
    _TASK_PRERUN_DISPATCH_UID,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc


_MISSING = object()

_UNUSABLE_CORRELATION_IDS = [
    pytest.param(_MISSING, id="missing-attribute"),
    pytest.param(None, id="none"),
    pytest.param("", id="empty-string"),
    pytest.param(42, id="int"),
    pytest.param(b"correlation-id", id="bytes"),
]

_AMBIENT_CORRELATION_ID = "ambient-correlation-id"
_OUTER_CORRELATION_ID = "outer-worker-correlation-id"

_ACCEPTED_CORRELATION_ID = st.text(
    min_size=1,
    max_size=64,
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
)
_UNUSABLE_CORRELATION_ID = st.one_of(
    st.none(),
    st.just(""),
    st.integers(),
    st.binary(max_size=8),
)


def _build_task(*, correlation_id: object = _MISSING) -> object:
    """Build a minimal Celery-like task object for helper-level tests.

    Omitting ``correlation_id`` leaves the request without that attribute,
    modelling a task whose message carried no correlation ID.

    Returns
    -------
    object
        A namespace with a ``request`` attribute carrying the requested value.

    """
    request = SimpleNamespace()
    if correlation_id is not _MISSING:
        request.correlation_id = correlation_id
    return SimpleNamespace(request=request)


class _TaskLike:
    """Minimal hashable task object for Celery signal dispatch tests."""

    def __init__(self, *, correlation_id: object = _MISSING) -> None:
        """Initialize the test double."""
        self.request = SimpleNamespace()
        if correlation_id is not _MISSING:
            self.request.correlation_id = correlation_id


def _disconnect_worker_receivers() -> None:
    """Reset this integration's worker receivers in Celery's process state."""
    task_prerun.disconnect(dispatch_uid=_TASK_PRERUN_DISPATCH_UID)
    task_postrun.disconnect(dispatch_uid=_TASK_POSTRUN_DISPATCH_UID)


@pytest.fixture
def celery_app() -> Celery:
    """Build a minimal Celery app for worker-signal tests.

    Returns
    -------
    Celery
        The in-memory Celery app named ``unit-celery-worker-token-stack``.

    """
    return Celery("unit-celery-worker-token-stack", broker="memory://")


@pytest.mark.parametrize("unusable_correlation_id", _UNUSABLE_CORRELATION_IDS)
def test_nested_task_without_usable_id_preserves_outer_context(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    unusable_correlation_id: object,
) -> None:
    """Nested tasks without usable IDs should preserve the outer context."""
    outer_task = _build_task(correlation_id=_OUTER_CORRELATION_ID)
    inner_task = _build_task(correlation_id=unusable_correlation_id)

    def _logic() -> None:
        """Exercise nested setup and cleanup around an unusable inner ID."""
        correlation_id_var.set(_AMBIENT_CORRELATION_ID)
        setup_correlation_id_in_worker(task=outer_task)

        assert correlation_id_var.get() == _OUTER_CORRELATION_ID, (
            "expected outer setup to set the outer task ID"
        )

        setup_correlation_id_in_worker(task=inner_task)

        assert correlation_id_var.get() == _OUTER_CORRELATION_ID, (
            "expected inner setup without a usable ID to preserve the outer ID"
        )
        stored_tokens = _celery_context_tokens.get(None)
        assert stored_tokens is not None, "expected both setups to record stack entries"
        assert len(stored_tokens[_CORRELATION_ID_CONTEXT_KEY]) == 2, (
            "expected the outer token and inner placeholder to be recorded"
        )

        clear_correlation_id_in_worker(task=inner_task)

        assert correlation_id_var.get() == _OUTER_CORRELATION_ID, (
            "expected inner cleanup to preserve the outer ID"
        )
        stored_tokens = _celery_context_tokens.get(None)
        assert stored_tokens is not None, (
            "expected outer setup to retain its reset token"
        )
        assert len(stored_tokens[_CORRELATION_ID_CONTEXT_KEY]) == 1, (
            "expected inner cleanup to consume only the inner placeholder"
        )

        clear_correlation_id_in_worker(task=outer_task)

        assert correlation_id_var.get() == _AMBIENT_CORRELATION_ID, (
            "expected outer cleanup to restore the ambient ID"
        )
        assert _celery_context_tokens.get(None) is None, (
            "expected all stack entries to be consumed"
        )

    isolated_context(_logic)


@pytest.mark.parametrize("unusable_correlation_id", _UNUSABLE_CORRELATION_IDS)
def test_configured_signals_preserve_outer_context_for_nested_task_without_id(
    celery_app: Celery,
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    unusable_correlation_id: object,
) -> None:
    """Configured signals should preserve the outer ID for an unusable nested ID."""
    _disconnect_worker_receivers()
    configure_celery_correlation(celery_app)
    outer_task = _TaskLike(correlation_id=_OUTER_CORRELATION_ID)
    inner_task = _TaskLike(correlation_id=unusable_correlation_id)

    def _logic() -> None:
        """Dispatch worker signals and assert the nested context sequence."""
        correlation_id_var.set(_AMBIENT_CORRELATION_ID)
        try:
            task_prerun.send(sender=outer_task, task=outer_task, args=(), kwargs={})
            assert correlation_id_var.get() == _OUTER_CORRELATION_ID, (
                "expected outer prerun to set the outer task ID"
            )

            task_prerun.send(sender=inner_task, task=inner_task, args=(), kwargs={})
            assert correlation_id_var.get() == _OUTER_CORRELATION_ID, (
                "expected inner prerun without a usable ID to preserve the outer ID"
            )

            task_postrun.send(
                sender=inner_task,
                task=inner_task,
                args=(),
                kwargs={},
                retval=None,
                state="SUCCESS",
            )
            assert correlation_id_var.get() == _OUTER_CORRELATION_ID, (
                "expected inner postrun to preserve the outer ID"
            )

            task_postrun.send(
                sender=outer_task,
                task=outer_task,
                args=(),
                kwargs={},
                retval=None,
                state="SUCCESS",
            )
            assert correlation_id_var.get() == _AMBIENT_CORRELATION_ID, (
                "expected outer postrun to restore the ambient ID"
            )
            assert _celery_context_tokens.get(None) is None, (
                "expected all stack entries to be consumed"
            )
        finally:
            _disconnect_worker_receivers()

    isolated_context(_logic)


@given(
    correlation_ids=st.lists(
        st.one_of(_ACCEPTED_CORRELATION_ID, _UNUSABLE_CORRELATION_ID),
        min_size=1,
        max_size=8,
    )
)
@settings(max_examples=50)
def test_context_token_stack_unwinds_lifo(correlation_ids: list[object]) -> None:
    """setup/clear functions must unwind one stack entry per setup in LIFO order.

    Non-empty strings update the correlation context; unusable values record a
    placeholder. After all cleanups the ambient value is restored and the token
    store is empty.
    """
    tasks = [_TaskLike(correlation_id=cid) for cid in correlation_ids]

    correlation_id_var.set(_AMBIENT_CORRELATION_ID)
    try:
        current_correlation_id = _AMBIENT_CORRELATION_ID
        for task, correlation_id in zip(tasks, correlation_ids, strict=True):
            setup_correlation_id_in_worker(task=task)
            if isinstance(correlation_id, str) and correlation_id:
                current_correlation_id = correlation_id
            assert correlation_id_var.get() == current_correlation_id, (
                "expected setup to apply the most recent usable correlation ID"
            )

        for index in range(len(tasks) - 1, -1, -1):
            clear_correlation_id_in_worker()
            remaining_ids = [
                correlation_id
                for correlation_id in correlation_ids[:index]
                if isinstance(correlation_id, str) and correlation_id
            ]
            expected = remaining_ids[-1] if remaining_ids else _AMBIENT_CORRELATION_ID
            assert correlation_id_var.get() == expected, (
                "expected cleanup to restore the most recent remaining usable ID"
            )

        assert correlation_id_var.get() == _AMBIENT_CORRELATION_ID, (
            "expected all cleanups to restore the ambient correlation ID"
        )
        assert _celery_context_tokens.get(None) is None, (
            "expected all stack entries to be consumed"
        )
    finally:
        correlation_id_var.set(None)
