"""Celery signal integration for correlation ID propagation.

This module is import-safe when the optional ``celery`` dependency is not
installed. Importing this module defines integration names only: it neither
imports Celery nor connects its process-global signals. Call
:func:`configure_celery_correlation` explicitly in every publisher and worker
process that needs correlation ID propagation; it registers the publish and
worker task handlers. Stable dispatch UIDs keep activation idempotent.
"""

from __future__ import annotations

import contextvars
import importlib
import logging
import threading
import types
import typing as typ
import weakref

from .celery_diagnostics import (
    _report_configuration_outcome,
    _safe_connect_signal,
)
from .middleware_utils import correlation_id_var

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from .celery_diagnostics import _PublisherContextState, _SignalState

    class _BackendLike(typ.Protocol):
        """Structural type for the Celery backend used by this module."""

        def as_uri(self) -> str:
            """Return the backend URI."""
            ...

    class _CeleryAppLike(typ.Protocol):
        """Structural app type; instances must support weak cache keys."""

        def __hash__(self) -> int:
            """Return the hash required by the weak verdict cache."""
            ...

        @property
        def backend(self) -> _BackendLike:
            """The application's result backend."""
            ...

        send_task: typ.Any


_BEFORE_TASK_PUBLISH_DISPATCH_UID = (
    "falcon_correlate.celery.propagate_correlation_id_to_celery"
)
_TASK_PRERUN_DISPATCH_UID = "falcon_correlate.celery.setup_correlation_id_in_worker"
_TASK_POSTRUN_DISPATCH_UID = "falcon_correlate.celery.clear_correlation_id_in_worker"
_CORRELATION_ID_CONTEXT_KEY = "correlation_id"
_logger = logging.getLogger(__name__)


_ContextToken = contextvars.Token[str | None]
type _CeleryContextTokens = dict[str, list[_ContextToken]]
_celery_context_tokens: contextvars.ContextVar[_CeleryContextTokens | None] = (
    contextvars.ContextVar("celery_context_tokens", default=None)
)
_celery_publishing_app: contextvars.ContextVar[_CeleryAppLike | None] = (
    contextvars.ContextVar("celery_publishing_app", default=None)
)
_configured_app_backend_rpc_verdicts: weakref.WeakKeyDictionary[
    _CeleryAppLike, bool
] = weakref.WeakKeyDictionary()
_configured_apps_with_send_task_context: weakref.WeakSet[_CeleryAppLike] = (
    weakref.WeakSet()
)
_configured_app_backend_rpc_verdicts_lock = threading.RLock()


def propagate_correlation_id_to_celery(
    *,
    sender: object | None = None,
    **kwargs: object,
) -> None:
    """Copy the ambient correlation ID into Celery publish properties.

    Celery populates ``properties['correlation_id']`` with the task ID by
    default. When a Falcon request correlation ID exists in context, this
    handler intentionally overwrites that publish-time value so downstream
    workers can trace the task back to the originating request.

    Parameters
    ----------
    sender : object | None
        Task name emitted by Celery's publish signal. It provides context for
        backend-inspection diagnostics but does not identify the publisher,
        because another app can publish a registered task by name.
    **kwargs : dict
        Celery signal keyword arguments. Must contain a ``properties`` key
        mapping to a mutable mapping (typically :class:`dict`) that holds
        AMQP message properties, including ``correlation_id``.

    Notes
    -----
    A configured app's ``send_task`` method establishes publisher identity for
    the duration of its synchronous publish call. When no configured publisher
    context is active, this handler falls back to Celery's active application.
    For an ``rpc://`` result backend, or when backend inspection is inconclusive,
    it preserves the task ID in ``correlation_id`` to maintain Celery's result
    retrieval contract.

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

    publishing_app = _celery_publishing_app.get()
    if publishing_app is None:
        backend_uses_rpc = _current_result_backend_uses_rpc()
    else:
        backend_uses_rpc = _cache_app_backend_rpc_verdict(
            publishing_app, task_name=sender
        )

    if backend_uses_rpc is not False:
        return

    properties["correlation_id"] = correlation_id


def _app_backend_uses_rpc(
    app: _CeleryAppLike, *, task_name: object | None = None
) -> bool | None:
    """Return whether an application's result backend URI uses RPC."""
    try:
        backend = getattr(app, "backend", None)
        if backend is None:
            return False

        as_uri = getattr(backend, "as_uri", None)
        if not callable(as_uri):
            return False

        return str(as_uri()).startswith("rpc://")
    except Exception:
        # A failed inspection is unknown, not evidence that the backend is non-RPC.
        message = "Unable to inspect Celery result backend URI"
        if isinstance(task_name, str):
            message += f" for publishing task {task_name!r}"
        _logger.debug("%s; preserving task ID.", message, exc_info=True)
        return None


def _cache_app_backend_rpc_verdict(
    app: _CeleryAppLike, *, task_name: object | None = None
) -> bool | None:
    """Cache a definite backend verdict; leave inspection failures retryable."""
    with _configured_app_backend_rpc_verdicts_lock:
        cached_verdict = _configured_app_backend_rpc_verdicts.get(app)
    if cached_verdict is not None:
        return cached_verdict

    backend_uses_rpc = _app_backend_uses_rpc(app, task_name=task_name)
    if backend_uses_rpc is None:
        return None

    with _configured_app_backend_rpc_verdicts_lock:
        return _configured_app_backend_rpc_verdicts.setdefault(app, backend_uses_rpc)


def _configure_app_send_task_context(app: _CeleryAppLike) -> _PublisherContextState:
    """Wrap ``send_task`` so its publish signal carries the actual app locally."""
    with _configured_app_backend_rpc_verdicts_lock:
        if app in _configured_apps_with_send_task_context:
            return "configured"

        bound_send_task = getattr(app, "send_task", None)
        original_send_task = getattr(bound_send_task, "__func__", None)
        if not callable(original_send_task):
            return "send_task_unavailable"

        def send_task_with_publishing_app(
            configured_app: _CeleryAppLike,
            *args: object,
            **kwargs: object,
        ) -> object:
            """Set publisher identity while Celery emits its publish signal."""
            token = _celery_publishing_app.set(configured_app)
            try:
                return original_send_task(configured_app, *args, **kwargs)
            finally:
                _celery_publishing_app.reset(token)

        try:
            app.send_task = types.MethodType(send_task_with_publishing_app, app)
        except (AttributeError, TypeError):
            return "assignment_rejected"

        _configured_apps_with_send_task_context.add(app)
        return "configured"


def _current_result_backend_uses_rpc() -> bool | None:
    """Return whether the active Celery app uses the RPC result backend."""
    try:
        celery_module = importlib.import_module("celery")
    except ImportError:
        return False

    current_app = getattr(celery_module, "current_app", None)
    if current_app is None:
        return False

    return _app_backend_uses_rpc(typ.cast("_CeleryAppLike", current_app))


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
    """Return a Celery task request correlation ID when it is a string."""
    request = getattr(task, "request", None)
    correlation_id = getattr(request, "correlation_id", None)
    return correlation_id if isinstance(correlation_id, str) else None


def _maybe_connect_celery_publish_signal() -> _SignalState:
    """Register the Celery publish handler once when Celery is installed."""
    try:
        celery_signals = importlib.import_module("celery.signals")
    except ImportError:
        return "celery_signals_unavailable"

    return _safe_connect_signal(
        celery_signals,
        "before_task_publish",
        propagate_correlation_id_to_celery,
        _BEFORE_TASK_PUBLISH_DISPATCH_UID,
    )


def _maybe_connect_celery_worker_signals() -> tuple[_SignalState, _SignalState]:
    """Register the Celery worker handlers once when Celery is installed."""
    try:
        celery_signals = importlib.import_module("celery.signals")
    except ImportError:
        return ("celery_signals_unavailable", "celery_signals_unavailable")

    prerun_state = _safe_connect_signal(
        celery_signals,
        "task_prerun",
        setup_correlation_id_in_worker,
        _TASK_PRERUN_DISPATCH_UID,
    )
    postrun_state = _safe_connect_signal(
        celery_signals,
        "task_postrun",
        clear_correlation_id_in_worker,
        _TASK_POSTRUN_DISPATCH_UID,
    )
    return prerun_state, postrun_state


def _maybe_connect_celery_signals() -> tuple[_SignalState, _SignalState, _SignalState]:
    """Register all supported Celery signal handlers when Celery is installed.

    Celery's Django-derived signal implementation protects receiver mutation
    with an internal ``threading.Lock``. Stable dispatch UIDs provide the
    duplicate-registration guard when several callers configure the integration
    concurrently.

    Returns
    -------
    tuple[_SignalState, _SignalState, _SignalState]
        Connection outcomes for publish, task-prerun, and task-postrun signals.

    """
    publish_state = _maybe_connect_celery_publish_signal()
    return publish_state, *_maybe_connect_celery_worker_signals()


def configure_celery_correlation[CeleryAppT: _CeleryAppLike](
    app: CeleryAppT,
) -> CeleryAppT:
    """Configure Celery correlation ID propagation for an application.

    Call this helper explicitly in each publisher and worker process that needs
    correlation ID propagation. It connects the ``before_task_publish``,
    ``task_prerun``, and ``task_postrun`` receivers through Celery's
    process-global registry. Stable dispatch UIDs keep repeated activation
    idempotent.

    The integration wraps this application's ``send_task`` method to identify
    the publishing application while Celery emits a publish signal. Signal
    sender values are task names and cannot reliably identify the publisher.
    Backend inspection is deferred until an eligible publish has an ambient
    correlation ID and message properties, so activation does not access
    Celery's lazy backend before application configuration is complete. If no
    verdict is cached, the first eligible publish attempts inspection; only a
    definite verdict from successful inspection is cached for this app. If
    inspection fails, the verdict remains uncached and publishes preserve
    Celery's task ID until inspection succeeds.

    Each distinct configuration outcome emits one structured ``INFO`` record
    when complete or ``WARNING`` record when incomplete for this app's lifetime.
    Activation records always report an ``unknown`` backend verdict because
    inspection is not part of configuration. An eligible publish caches a
    definite verdict internally when inspection succeeds; the record is not
    updated afterwards. Importing the integration does not emit these
    diagnostics.

    Parameters
    ----------
    app : CeleryAppT
        Celery application instance whose ``send_task`` method establishes
        publisher identity. The app must be hashable and weak-referenceable for
        the weak-key state. Signal registration remains global and requires
        Celery's signal objects to be importable.

    Returns
    -------
    CeleryAppT
        The same ``app`` instance, returned for application-factory ergonomics.
        Repeated calls are idempotent because publisher wrapping is guarded per
        app and signal registration uses stable dispatch UIDs.

    """
    publisher_context_state = _configure_app_send_task_context(app)
    signal_states = _maybe_connect_celery_signals()
    _report_configuration_outcome(
        app,
        signal_states,
        publisher_context_state,
        backend_uses_rpc=None,
    )
    return app


__all__ = [
    "clear_correlation_id_in_worker",
    "configure_celery_correlation",
    "propagate_correlation_id_to_celery",
    "setup_correlation_id_in_worker",
]
