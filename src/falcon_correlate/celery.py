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
    sender: object | None = None,
    headers: cabc.MutableMapping[str, typ.Any] | None = None,
    body: object | None = None,
    properties: cabc.MutableMapping[str, typ.Any] | None = None,
    **kwargs: object,
) -> None:
    """Copy the ambient correlation ID into Celery publish properties.

    Celery populates ``properties['correlation_id']`` with the task ID by
    default. When a Falcon request correlation ID exists in context, this
    handler intentionally overwrites that publish-time value so downstream
    workers can trace the task back to the originating request.
    """
    correlation_id = correlation_id_var.get()
    if not correlation_id or properties is None:
        return

    properties["correlation_id"] = correlation_id


def _load_before_task_publish_signal() -> _SupportsSignalConnect | None:
    """Return Celery's publish signal when the optional dependency exists."""
    try:
        celery_signals = importlib.import_module("celery.signals")
    except ImportError:
        return None

    return typ.cast("_SupportsSignalConnect", celery_signals.before_task_publish)


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
