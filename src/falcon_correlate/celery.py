"""Celery publish integration for correlation ID propagation.

This module is import-safe when the optional ``celery`` dependency is not
installed. If Celery is available, importing this module connects
``propagate_correlation_id_to_celery`` to Celery's
``before_task_publish`` signal.
"""

from __future__ import annotations

import importlib
import typing as typ

from .middleware import correlation_id_var

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    class _SupportsSignalConnect(typ.Protocol):
        def connect(
            self,
            receiver: cabc.Callable[..., object],
            *,
            dispatch_uid: str,
            weak: bool,
        ) -> object: ...


_BEFORE_TASK_PUBLISH_DISPATCH_UID = (
    "falcon_correlate.celery.propagate_correlation_id_to_celery"
)


def propagate_correlation_id_to_celery(
    **kwargs: object,
) -> None:
    """Copy the ambient correlation ID into Celery publish properties.

    Celery populates ``properties['correlation_id']`` with the task ID by
    default. When a Falcon request correlation ID exists in context, this
    handler intentionally overwrites that publish-time value so downstream
    workers can trace the task back to the originating request.
    """
    properties = typ.cast(
        "cabc.MutableMapping[str, typ.Any] | None",
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


def _load_before_task_publish_signal() -> _SupportsSignalConnect | None:
    """Return Celery's publish signal when the optional dependency exists."""
    try:
        celery_signals = importlib.import_module("celery.signals")
    except ImportError:
        return None

    before_task_publish = getattr(celery_signals, "before_task_publish", None)
    if before_task_publish is None:
        return None

    return typ.cast("_SupportsSignalConnect", before_task_publish)


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


def _connect_before_task_publish_signal() -> None:
    """Register the Celery publish handler once when Celery is installed."""
    before_task_publish = _load_before_task_publish_signal()
    if before_task_publish is None:
        return

    before_task_publish.connect(
        propagate_correlation_id_to_celery,
        dispatch_uid=_BEFORE_TASK_PUBLISH_DISPATCH_UID,
        weak=False,
    )


_connect_before_task_publish_signal()

__all__ = ["propagate_correlation_id_to_celery"]
