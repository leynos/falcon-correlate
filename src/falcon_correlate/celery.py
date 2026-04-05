"""Celery publish integration for correlation ID propagation.

This module is import-safe when the optional ``celery`` dependency is not
installed. Use ``_maybe_connect_celery_publish_signal`` during application
start-up to register ``propagate_correlation_id_to_celery`` with Celery's
``before_task_publish`` signal.
"""

from __future__ import annotations

import importlib
import typing as typ

from .middleware import correlation_id_var

if typ.TYPE_CHECKING:
    import collections.abc as cabc


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


__all__ = [
    "_maybe_connect_celery_publish_signal",
    "propagate_correlation_id_to_celery",
]
