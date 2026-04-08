"""Celery signal integration for correlation ID propagation.

This module is import-safe when the optional ``celery`` dependency is not
installed. Importing this module opportunistically registers handlers for
Celery's publish and worker task signals when Celery is available.
"""

from __future__ import annotations

import contextvars
import importlib
import typing as typ

from .middleware import correlation_id_var

if typ.TYPE_CHECKING:
    import collections.abc as cabc


_BEFORE_TASK_PUBLISH_DISPATCH_UID = (
    "falcon_correlate.celery.propagate_correlation_id_to_celery"
)
_TASK_PRERUN_DISPATCH_UID = "falcon_correlate.celery.setup_correlation_id_in_worker"
_TASK_POSTRUN_DISPATCH_UID = "falcon_correlate.celery.clear_correlation_id_in_worker"
_CORRELATION_ID_CONTEXT_KEY = "correlation_id"

_ContextToken = contextvars.Token[str | None]
_CeleryContextTokens = dict[str, _ContextToken]
_celery_context_tokens: contextvars.ContextVar[_CeleryContextTokens | None] = (
    contextvars.ContextVar("celery_context_tokens", default=None)
)


def propagate_correlation_id_to_celery(
    **kwargs: object,
) -> None:
    """Copy the ambient correlation ID into Celery publish properties.

    Celery populates ``properties['correlation_id']`` with the task ID by
    default. When a Falcon request correlation ID exists in context, this
    handler intentionally overwrites that publish-time value so downstream
    workers can trace the task back to the originating request.

    Parameters
    ----------
    **kwargs : dict
        Celery signal keyword arguments. Must contain a ``properties`` key
        mapping to a mutable mapping (typically :class:`dict`) that holds
        AMQP message properties, including ``correlation_id``.

    Returns
    -------
    None
        This function mutates the ``properties`` mapping in place when the
        ambient correlation ID is set and the result backend does not use
        RPC, overwriting Celery's default ``correlation_id`` value.

    Notes
    -----
    When the active Celery application uses the ``rpc://`` result backend,
    this handler preserves the task ID in ``correlation_id`` to maintain
    Celery's result retrieval contract.

    """
    properties = typ.cast(
        "cabc.MutableMapping[str, object] | None",
        kwargs.get("properties"),
    )
    correlation_id = correlation_id_var.get()
    if not correlation_id:
        return

    if properties is None:
        return

    if _current_result_backend_uses_rpc():
        return

    properties["correlation_id"] = correlation_id


def _current_result_backend_uses_rpc() -> bool:
    """Return ``True`` when the active Celery app uses the RPC result backend."""
    try:
        celery_module = importlib.import_module("celery")
    except ImportError:
        return False

    current_app = getattr(celery_module, "current_app", None)
    if current_app is None:
        return False

    backend = getattr(current_app, "backend", None)
    if backend is None:
        return False

    as_uri = getattr(backend, "as_uri", None)
    if not callable(as_uri):
        return False

    return str(as_uri()).startswith("rpc://")


def setup_correlation_id_in_worker(*, task: object | None = None, **_: object) -> None:
    """Expose the task request correlation ID during worker execution."""
    correlation_id = _get_task_request_correlation_id(task)
    if not correlation_id:
        return

    token = correlation_id_var.set(correlation_id)
    stored_tokens = dict(_celery_context_tokens.get({}) or {})
    stored_tokens[_CORRELATION_ID_CONTEXT_KEY] = token
    _celery_context_tokens.set(stored_tokens)


def clear_correlation_id_in_worker(**_: object) -> None:
    """Restore the pre-task correlation ID context after worker execution."""
    stored_tokens = _celery_context_tokens.get(None)
    if not stored_tokens:
        return

    correlation_id_token = stored_tokens.get(_CORRELATION_ID_CONTEXT_KEY)
    if correlation_id_token is not None:
        correlation_id_var.reset(correlation_id_token)

    _celery_context_tokens.set(None)


def _get_task_request_correlation_id(task: object | None) -> str | None:
    """Return the correlation ID carried by a Celery task request, if any."""
    request = getattr(task, "request", None)
    correlation_id = getattr(request, "correlation_id", None)
    return correlation_id if isinstance(correlation_id, str) else None


def _maybe_connect_celery_publish_signal() -> None:
    """Register the Celery publish handler once when Celery is installed."""
    try:
        celery_signals = importlib.import_module("celery.signals")
    except ImportError:
        return

    before_task_publish = getattr(celery_signals, "before_task_publish", None)
    if before_task_publish is None:
        return

    connect = getattr(before_task_publish, "connect", None)
    if not callable(connect):
        return

    connect(
        propagate_correlation_id_to_celery,
        dispatch_uid=_BEFORE_TASK_PUBLISH_DISPATCH_UID,
        weak=False,
    )


def _maybe_connect_celery_worker_signals() -> None:
    """Register the Celery worker handlers once when Celery is installed."""
    try:
        celery_signals = importlib.import_module("celery.signals")
    except ImportError:
        return

    task_prerun = getattr(celery_signals, "task_prerun", None)
    task_postrun = getattr(celery_signals, "task_postrun", None)
    if task_prerun is None or task_postrun is None:
        return

    prerun_connect = getattr(task_prerun, "connect", None)
    postrun_connect = getattr(task_postrun, "connect", None)
    if not callable(prerun_connect) or not callable(postrun_connect):
        return

    prerun_connect(
        setup_correlation_id_in_worker,
        dispatch_uid=_TASK_PRERUN_DISPATCH_UID,
        weak=False,
    )
    postrun_connect(
        clear_correlation_id_in_worker,
        dispatch_uid=_TASK_POSTRUN_DISPATCH_UID,
        weak=False,
    )


_maybe_connect_celery_publish_signal()
_maybe_connect_celery_worker_signals()


__all__ = [
    "_maybe_connect_celery_publish_signal",
    "_maybe_connect_celery_worker_signals",
    "clear_correlation_id_in_worker",
    "propagate_correlation_id_to_celery",
    "setup_correlation_id_in_worker",
]
