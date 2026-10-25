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
type _CeleryContextTokens = dict[str, list[_ContextToken]]
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
    :data:`correlation_id_var`, and one reset token is pushed onto a context-
    local stack for each successful call. Setup is not idempotent: repeated
    successful calls each push a token. A missing, empty, or non-string ID
    pushes no token. A later cleanup still pops the most recent saved token, if
    one exists, so an unmatched cleanup after a nested missing-ID setup can
    consume an outer setup's token.

    Pair each successful setup with one cleanup in the same context and in
    LIFO order. Do not connect this receiver manually when
    :func:`configure_celery_correlation` already manages ``task_prerun``.

    """  # ruff: ignore[docstring-extraneous-returns] -- public callback documents None.
    correlation_id = _get_task_request_correlation_id(task)
    if not correlation_id:
        return

    token = correlation_id_var.set(correlation_id)
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
    Cleanup pops one reset token from the current context-local stack and
    resets :data:`correlation_id_var` to the value saved by that token. Tokens
    are popped in LIFO order, restoring the preceding value. If no token exists,
    cleanup does nothing. Because setup with a missing, empty, or non-string ID
    pushes no token, cleanup can consume the most recent earlier successful
    setup's token in that context.

    Pair each successful setup with one cleanup in the same context and in
    LIFO order. Do not connect this receiver manually when
    :func:`configure_celery_correlation` already manages ``task_postrun``.

    """  # ruff: ignore[docstring-extraneous-returns] -- public callback documents None.
    stored_tokens = _celery_context_tokens.get(None)
    if not stored_tokens:
        return

    correlation_id_tokens = list(stored_tokens.get(_CORRELATION_ID_CONTEXT_KEY, []))
    if not correlation_id_tokens:
        return

    correlation_id_var.reset(correlation_id_tokens.pop())
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
