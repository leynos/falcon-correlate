"""httpx propagation utilities for correlation ID propagation.

Provides wrapper functions and reusable transports that read the current
correlation ID from ``correlation_id_var`` and inject it into outgoing
``httpx`` requests.

``httpx`` is an **optional** dependency.  This module can be imported
without ``httpx`` installed; an ``ImportError`` is raised only when a
wrapper function is called or a transport is instantiated without
``httpx`` being available.
"""

from __future__ import annotations

import typing as typ

from .middleware import DEFAULT_HEADER_NAME, correlation_id_var

if typ.TYPE_CHECKING:
    import httpx


def _require_httpx() -> typ.Any:  # noqa: ANN401
    """Return the optional ``httpx`` module or raise ``ImportError``."""
    try:
        import httpx
    except ImportError as exc:
        msg = "httpx is required to use falcon_correlate.httpx"
        raise ImportError(msg) from exc
    else:
        return httpx


def _inject_correlation_id_header(
    headers: httpx.Headers,
    header_name: str = DEFAULT_HEADER_NAME,
) -> None:
    """Inject the current correlation ID unless the header already exists."""
    correlation_id = correlation_id_var.get()
    if correlation_id and header_name not in headers:
        headers[header_name] = correlation_id


class CorrelationIDTransport:
    """Inject correlation IDs into sync requests before transport delegation."""

    def __init__(
        self,
        wrapped_transport: httpx.BaseTransport,
        header_name: str = DEFAULT_HEADER_NAME,
    ) -> None:
        """Store the wrapped transport and configured outbound header name."""
        _require_httpx()
        self._wrapped_transport = wrapped_transport
        self._header_name = header_name

    def handle_request(
        self,
        request: httpx.Request,
    ) -> httpx.Response:
        """Add the correlation ID header and delegate the request."""
        _inject_correlation_id_header(request.headers, self._header_name)
        return self._wrapped_transport.handle_request(request)

    def close(self) -> None:
        """Delegate transport shutdown to the wrapped transport."""
        self._wrapped_transport.close()

    def __enter__(self) -> CorrelationIDTransport:
        """Enter the transport context (required by httpx.Client)."""
        self._wrapped_transport.__enter__()
        return self

    def __exit__(self, *args: typ.Any) -> None:  # noqa: ANN401
        """Exit the transport context (required by httpx.Client)."""
        self._wrapped_transport.__exit__(*args)


class AsyncCorrelationIDTransport:
    """Inject correlation IDs into async requests before transport delegation."""

    def __init__(
        self,
        wrapped_transport: httpx.AsyncBaseTransport,
        header_name: str = DEFAULT_HEADER_NAME,
    ) -> None:
        """Store the wrapped transport and configured outbound header name."""
        _require_httpx()
        self._wrapped_transport = wrapped_transport
        self._header_name = header_name

    async def handle_async_request(
        self,
        request: httpx.Request,
    ) -> httpx.Response:
        """Add the correlation ID header and delegate the request."""
        _inject_correlation_id_header(request.headers, self._header_name)
        return await self._wrapped_transport.handle_async_request(request)

    async def aclose(self) -> None:
        """Delegate transport shutdown to the wrapped transport."""
        await self._wrapped_transport.aclose()

    async def __aenter__(self) -> AsyncCorrelationIDTransport:
        """Enter the async transport context (required by httpx.AsyncClient)."""
        await self._wrapped_transport.__aenter__()
        return self

    async def __aexit__(self, *args: typ.Any) -> None:  # noqa: ANN401
        """Exit the async transport context (required by httpx.AsyncClient)."""
        await self._wrapped_transport.__aexit__(*args)


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
    httpx = _require_httpx()
    headers = _prepare_headers(kwargs)
    return httpx.request(method, url, headers=headers, **kwargs)


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
    httpx = _require_httpx()
    headers = _prepare_headers(kwargs)
    async with httpx.AsyncClient() as client:
        return await client.request(method, url, headers=headers, **kwargs)


def _prepare_headers(
    kwargs: dict[str, typ.Any],
) -> httpx.Headers:
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
    httpx.Headers
        The enriched headers.

    """
    httpx = _require_httpx()
    raw_headers = kwargs.pop("headers", None)
    # Use httpx.Headers to preserve duplicate entries
    if raw_headers is not None:
        headers = (
            raw_headers
            if isinstance(raw_headers, httpx.Headers)
            else httpx.Headers(raw_headers)
        )
    else:
        headers = httpx.Headers()

    _inject_correlation_id_header(headers)
    return headers
