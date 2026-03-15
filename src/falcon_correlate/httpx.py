"""httpx wrapper functions for correlation ID propagation.

Provides ``request_with_correlation_id`` and its async variant
``async_request_with_correlation_id``.  Both read the current
correlation ID from ``correlation_id_var`` and inject it as the
``X-Correlation-ID`` header on outgoing ``httpx`` requests.

``httpx`` is an **optional** dependency.  This module can be imported
without ``httpx`` installed; an ``ImportError`` is raised only when one
of the wrapper functions is actually called.
"""

from __future__ import annotations

import typing as typ

from .middleware import DEFAULT_HEADER_NAME, correlation_id_var

if typ.TYPE_CHECKING:
    import httpx


def request_with_correlation_id(
    method: str,
    url: str,
    **kwargs: typ.Any,  # noqa: ANN401
) -> httpx.Response:
    """Send an HTTP request, injecting the correlation ID header.

    This is a thin wrapper around ``httpx.request`` that reads the
    current correlation ID from ``correlation_id_var`` and, when set,
    adds it as the ``X-Correlation-ID`` header.  Existing headers
    passed by the caller are preserved.

    Parameters
    ----------
    method : str
        The HTTP method (e.g. ``"GET"``, ``"POST"``).
    url : str
        The URL to request.
    **kwargs : Any
        Additional keyword arguments passed through to
        ``httpx.request``.

    Returns
    -------
    httpx.Response
        The HTTP response.

    """
    import httpx as _httpx  # lazy: optional dependency

    headers = _prepare_headers(kwargs)
    return _httpx.request(method, url, headers=headers, **kwargs)


async def async_request_with_correlation_id(
    method: str,
    url: str,
    **kwargs: typ.Any,  # noqa: ANN401
) -> httpx.Response:
    """Send an async HTTP request, injecting the correlation ID header.

    Asynchronous counterpart of ``request_with_correlation_id``.
    Creates a temporary ``httpx.AsyncClient`` for the request.

    Parameters
    ----------
    method : str
        The HTTP method (e.g. ``"GET"``, ``"POST"``).
    url : str
        The URL to request.
    **kwargs : Any
        Additional keyword arguments passed through to
        ``httpx.AsyncClient.request``.

    Returns
    -------
    httpx.Response
        The HTTP response.

    """
    import httpx as _httpx  # lazy: optional dependency

    headers = _prepare_headers(kwargs)
    async with _httpx.AsyncClient() as client:
        return await client.request(method, url, headers=headers, **kwargs)


def _prepare_headers(
    kwargs: dict[str, typ.Any],
) -> dict[str, str] | httpx.Headers:
    """Extract and enrich headers with the correlation ID.

    Pops ``headers`` from *kwargs*, converts to a mutable structure,
    and injects the correlation ID when the context variable is set.
    Preserves duplicate header entries when present.

    Parameters
    ----------
    kwargs : dict[str, Any]
        The keyword arguments dict (mutated in place to remove
        ``headers``).

    Returns
    -------
    dict[str, str] | httpx.Headers
        The enriched headers dict or Headers instance.

    """
    import httpx as _httpx  # lazy: optional dependency

    raw_headers = kwargs.pop("headers", None)
    # Use httpx.Headers to preserve duplicate entries
    if raw_headers is not None:
        headers = (
            raw_headers
            if isinstance(raw_headers, _httpx.Headers)
            else _httpx.Headers(raw_headers)
        )
    else:
        headers = _httpx.Headers()

    cid = correlation_id_var.get()
    # Only inject correlation ID if caller hasn't already provided it
    if cid and DEFAULT_HEADER_NAME not in headers:
        headers[DEFAULT_HEADER_NAME] = cid
    return headers
