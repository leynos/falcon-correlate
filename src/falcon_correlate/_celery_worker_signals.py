"""Internal Celery worker receivers and their context-local token stack.

This module does not import Celery or connect process-global signals. The
public callbacks are re-exported by :mod:`falcon_correlate.celery`, which
registers them through :func:`configure_celery_correlation`.
"""

from __future__ import annotations

import contextvars

from .middleware_utils import correlation_id_var

_CORRELATION_ID_CONTEXT_KEY = "correlation_id"
_ContextToken = contextvars.Token[str | None]
# ``None`` is a placeholder for a setup that found no usable correlation ID.
type _ContextStackEntry = _ContextToken | None
type _CeleryContextTokens = dict[str, list[_ContextStackEntry]]
_celery_context_tokens: contextvars.ContextVar[_CeleryContextTokens | None] = (
    contextvars.ContextVar("celery_context_tokens", default=None)
)


def setup_correlation_id_in_worker(*, task: object | None = None, **_: object) -> None:
    """Expose a task request correlation ID during worker execution.

    Parameters
    ----------
    task : object | None, keyword-only
        Celery task whose ``request.correlation_id`` is read.
    **_ : object
        Additional Celery signal keyword arguments, which are ignored.

    Returns
    -------
    None
        This signal receiver updates the current correlation context in place.

    See Also
    --------
    configure_celery_correlation : Recommended signal activation API.
    clear_correlation_id_in_worker : Restore the preceding context value.

    Notes
    -----
    A non-empty string in ``task.request.correlation_id`` is set on
    :data:`correlation_id_var`, and the returned reset token is pushed onto a
    context-local stack. A missing, empty, or non-string ID pushes a ``None``
    placeholder instead and leaves the correlation context unchanged. Every
    call pushes exactly one stack entry, so setup is not idempotent: repeated
    calls each push an entry.

    Pair each setup with one cleanup in the same context and in LIFO order,
    including when the task has no usable ID. The placeholder keeps a nested
    task's cleanup paired with its own setup, so an enclosing task's
    correlation ID remains visible until the enclosing cleanup runs. Do not
    connect this receiver manually when :func:`configure_celery_correlation`
    already manages ``task_prerun``.

    """  # ruff: ignore[docstring-extraneous-returns] -- public callback documents None.
    correlation_id = _get_task_request_correlation_id(task)
    token = correlation_id_var.set(correlation_id) if correlation_id else None

    stored_tokens = dict(_celery_context_tokens.get() or {})
    correlation_id_tokens = list(stored_tokens.get(_CORRELATION_ID_CONTEXT_KEY, []))
    correlation_id_tokens.append(token)
    stored_tokens[_CORRELATION_ID_CONTEXT_KEY] = correlation_id_tokens
    _celery_context_tokens.set(stored_tokens)


def clear_correlation_id_in_worker(**_: object) -> None:
    """Restore the preceding correlation context after worker execution.

    Parameters
    ----------
    **_ : object
        Celery signal keyword arguments, including ``task``, which are ignored.

    Returns
    -------
    None
        This signal receiver updates the current correlation context in place.

    See Also
    --------
    configure_celery_correlation : Recommended signal activation API.
    setup_correlation_id_in_worker : Bind the task request correlation ID.

    Notes
    -----
    Cleanup pops exactly one entry from the current context-local stack. A
    real reset token restores the value saved when its setup called
    :meth:`~contextvars.ContextVar.set`; a ``None`` placeholder from a setup
    without a usable ID leaves the correlation context unchanged. Entries are
    popped in LIFO order, so cleaning up a nested task without an ID preserves
    the enclosing task's correlation ID until the enclosing cleanup runs.
    Cleanup does nothing when the store or stack is empty.

    Pair each setup with one cleanup in the same context and in LIFO order. Do
    not connect this receiver manually when
    :func:`configure_celery_correlation` already manages ``task_postrun``.

    """  # ruff: ignore[docstring-extraneous-returns] -- public callback documents None.
    stored_tokens = _celery_context_tokens.get(None)
    if not stored_tokens:
        return

    correlation_id_tokens = list(stored_tokens.get(_CORRELATION_ID_CONTEXT_KEY, []))
    if not correlation_id_tokens:
        return

    token = correlation_id_tokens.pop()
    if token is not None:
        correlation_id_var.reset(token)
    if correlation_id_tokens:
        stored_tokens[_CORRELATION_ID_CONTEXT_KEY] = correlation_id_tokens
    else:
        stored_tokens.pop(_CORRELATION_ID_CONTEXT_KEY, None)

    _celery_context_tokens.set(stored_tokens or None)


def _get_task_request_correlation_id(task: object | None) -> str | None:
    """Return a Celery task request correlation ID when it is a string."""
    request = getattr(task, "request", None)
    correlation_id = getattr(request, "correlation_id", None)
    return correlation_id if isinstance(correlation_id, str) else None
