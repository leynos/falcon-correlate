"""Shared helpers for Celery worker signal tests."""

from __future__ import annotations

from types import SimpleNamespace

_MISSING = object()


def build_task(*, correlation_id: object = _MISSING) -> object:
    """Build a minimal Celery-like task object for signal handler tests.

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
