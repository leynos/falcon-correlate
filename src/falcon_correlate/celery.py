"""Celery signal integration for correlation ID propagation.

This module is import-safe when the optional ``celery`` dependency is not
installed. Importing this module opportunistically registers handlers for
Celery's publish and worker task signals when Celery is available.
"""

from __future__ import annotations

import contextvars
import importlib
import logging
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
_logger = logging.getLogger(__name__)

_ContextToken = contextvars.Token[str | None]
_CeleryContextTokens = dict[str, list[_ContextToken]]
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
    """Return whether the active Celery app uses the RPC result backend.

    Returns
    -------
    bool
        True when Celery is importable and its active result backend URI starts
        with ``rpc://``.

    """
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
    stored_tokens = dict(_celery_context_tokens.get() or {})
    correlation_id_tokens = list(stored_tokens.get(_CORRELATION_ID_CONTEXT_KEY, []))
    correlation_id_tokens.append(token)
    stored_tokens[_CORRELATION_ID_CONTEXT_KEY] = correlation_id_tokens
    _celery_context_tokens.set(stored_tokens)


def clear_correlation_id_in_worker(**_: object) -> None:
    """Restore the pre-task correlation ID context after worker execution."""
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
    """Return the correlation ID carried by a Celery task request, if any.

    Parameters
    ----------
    task : object | None
        The Celery task instance supplied by the worker signal.

    Returns
    -------
    str | None
        The request correlation ID when it is a string; otherwise ``None``.

    """
    request = getattr(task, "request", None)
    correlation_id = getattr(request, "correlation_id", None)
    return correlation_id if isinstance(correlation_id, str) else None


def _safe_connect_signal(
    signal_module: object,
    signal_name: str,
    handler: cabc.Callable[..., object],
    dispatch_uid: str,
) -> None:
    """Connect a Celery signal when the signal object exposes ``connect``.

    Emits ``DEBUG`` log lines for each connection attempt, skipped signal, and
    exception so that misconfigured or missing signals are diagnosable in
    production without raising.

    """
    signal = getattr(signal_module, signal_name, None)
    if signal is None:
        _logger.debug(
            "falcon_correlate: signal %r not found on %r; skipping",
            signal_name,
            signal_module,
        )
        return

    connect = getattr(signal, "connect", None)
    if not callable(connect):
        _logger.debug(
            "falcon_correlate: signal %r has no callable connect(); skipping",
            signal_name,
        )
        return

    try:
        handler_name = getattr(handler, "__name__", repr(handler))
        connect(handler, dispatch_uid=dispatch_uid, weak=False)
        _logger.debug(
            "falcon_correlate: connected %r to %r (dispatch_uid=%r)",
            handler_name,
            signal_name,
            dispatch_uid,
        )
    except Exception:
        _logger.debug(
            "falcon_correlate: exception connecting %r to %r",
            getattr(handler, "__name__", repr(handler)),
            signal_name,
            exc_info=True,
        )


def _maybe_connect_celery_publish_signal() -> None:
    """Register the Celery publish handler once when Celery is installed."""
    try:
        celery_signals = importlib.import_module("celery.signals")
    except ImportError:
        return

    _safe_connect_signal(
        celery_signals,
        "before_task_publish",
        propagate_correlation_id_to_celery,
        _BEFORE_TASK_PUBLISH_DISPATCH_UID,
    )


def _maybe_connect_celery_worker_signals() -> None:
    """Register the Celery worker handlers once when Celery is installed."""
    try:
        celery_signals = importlib.import_module("celery.signals")
    except ImportError:
        return

    _safe_connect_signal(
        celery_signals,
        "task_prerun",
        setup_correlation_id_in_worker,
        _TASK_PRERUN_DISPATCH_UID,
    )
    _safe_connect_signal(
        celery_signals,
        "task_postrun",
        clear_correlation_id_in_worker,
        _TASK_POSTRUN_DISPATCH_UID,
    )


def _maybe_connect_celery_signals() -> None:
    """Register all supported Celery signal handlers when Celery is installed.

    Celery's Django-derived signal implementation protects receiver mutation
    with an internal ``threading.Lock``. Stable dispatch UIDs provide the
    duplicate-registration guard when several callers configure the integration
    concurrently.

    """
    _maybe_connect_celery_publish_signal()
    _maybe_connect_celery_worker_signals()


def configure_celery_correlation[CeleryAppT](app: CeleryAppT) -> CeleryAppT:
    """Configure Celery correlation ID propagation for an application.

    The current integration uses Celery's global signal registry, so the
    ``app`` parameter is returned unchanged for application-factory ergonomics.
    Stable dispatch UIDs keep repeated calls idempotent.

    Parameters
    ----------
    app : CeleryAppT
        Celery application instance being configured. The instance is used as
        the caller's explicit setup marker; signal registration remains global
        and requires Celery's signal objects to be importable.

    Returns
    -------
    CeleryAppT
        The same ``app`` instance, returned for application-factory ergonomics.
        Repeated calls are idempotent because registration uses stable dispatch
        UIDs.

    """
    _maybe_connect_celery_signals()
    return app


_maybe_connect_celery_signals()


__all__ = [
    "clear_correlation_id_in_worker",
    "configure_celery_correlation",
    "propagate_correlation_id_to_celery",
    "setup_correlation_id_in_worker",
]
