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

import importlib
import typing as typ

from .middleware_config import DEFAULT_HEADER_NAME
from .middleware_utils import correlation_id_var

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    from types import TracebackType

    import httpx
    from httpx import AsyncBaseTransport as _AsyncBaseTransport
    from httpx import AsyncBaseTransport as _AsyncWrappedTransport
    from httpx import BaseTransport as _SyncBaseTransport
    from httpx import BaseTransport as _SyncWrappedTransport

    class _SupportsSyncExit(typ.Protocol):
        """Protocol for synchronous transport context manager exits."""

        def __exit__(
            self,
            exc_type: type[BaseException] | None = None,
            exc_value: BaseException | None = None,
            traceback: TracebackType | None = None,
        ) -> object:
            """Exit the transport context manager.

            Parameters
            ----------
            exc_type : type[BaseException] | None
                The exception type, if any.
            exc_value : BaseException | None
                The exception instance, if any.
            traceback : TracebackType | None
                The traceback for the exception, if any.

            Returns
            -------
            object
                A protocol-level return value passed through to callers.

            """
            pass

    class _SupportsAsyncExit(typ.Protocol):
        """Protocol for asynchronous transport context manager exits."""

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None = None,
            exc_value: BaseException | None = None,
            traceback: TracebackType | None = None,
        ) -> object:
            """Exit the asynchronous transport context manager.

            Parameters
            ----------
            exc_type : type[BaseException] | None
                The exception type, if any.
            exc_value : BaseException | None
                The exception instance, if any.
            traceback : TracebackType | None
                The traceback for the exception, if any.

            Returns
            -------
            object
                A protocol-level return value passed through to callers.

            """
            pass

    type _ExitArgs = tuple[
        type[BaseException] | None,
        BaseException | None,
        TracebackType | None,
    ]
else:
    _SyncBaseTransport = object
    _SyncWrappedTransport = object
    _AsyncBaseTransport = object
    _AsyncWrappedTransport = object


def _require_httpx() -> None:
    """Raise ImportError when the optional httpx dependency is unavailable."""
    try:
        importlib.import_module("httpx")
    except ImportError as exc:
        msg = "httpx is required to use falcon_correlate.httpx"
        raise ImportError(msg) from exc


def _inject_correlation_id_header(
    headers: httpx.Headers,
    header_name: str = DEFAULT_HEADER_NAME,
) -> None:
    """Inject the current correlation ID unless the header already exists."""
    correlation_id = correlation_id_var.get()
    if correlation_id and header_name not in headers:
        headers[header_name] = correlation_id


class _CorrelationIDTransportBase[WrappedTransportT]:
    """Shared initialization for sync and async correlation ID transports."""

    # Intentionally Any: this base stores either sync or async httpx transports;
    # concrete subclasses enforce the specific transport type.
    _wrapped_transport: WrappedTransportT
    _header_name: str

    def __init__(
        self,
        wrapped_transport: WrappedTransportT,
        header_name: str = DEFAULT_HEADER_NAME,
    ) -> None:
        """Store the wrapped transport and configured outbound header name.

        Raises
        ------
        ValueError
            If ``header_name`` is empty or contains only whitespace.

        """
        _require_httpx()
        if not header_name or not header_name.strip():
            msg = "header_name must not be empty or whitespace"
            raise ValueError(msg)
        self._wrapped_transport = wrapped_transport
        self._header_name = header_name.strip()

    def _prepare_request(self, request: httpx.Request) -> None:
        """Inject the configured correlation ID header into a request."""
        _inject_correlation_id_header(request.headers, self._header_name)

    @staticmethod
    def _forward_lifecycle_result(result: object) -> None:
        """Preserve wrapped lifecycle results under HTTPX's ``None`` contract.

        HTTPX declares ``close``, ``aclose``, ``__exit__``, and ``__aexit__`` as
        returning ``None``. A wrapped exit may return a truthy value to suppress
        an exception, so this cast preserves each runtime result while keeping
        the wrapper signatures aligned with HTTPX.
        """
        return typ.cast("None", result)


class CorrelationIDTransport(
    _CorrelationIDTransportBase[_SyncWrappedTransport],
    _SyncBaseTransport,
):
    """Inject correlation IDs into sync requests before transport delegation."""

    # __init__ inherited from _CorrelationIDTransportBase

    def handle_request(
        self,
        request: httpx.Request,
    ) -> httpx.Response:
        """Add the correlation ID header and delegate the request.

        Returns
        -------
        httpx.Response
            The response returned by the wrapped transport.

        """
        self._prepare_request(request)
        return self._wrapped_transport.handle_request(request)

    # @codescene(disable:"Code Duplication") Explicit protocol methods (2026-10-25).
    def close(self) -> None:
        """Delegate shutdown to the wrapped transport.

        Returns
        -------
        None
            The declared HTTPX contract is ``None``. At runtime, the wrapped
            transport's result is forwarded unchanged.

        """
        return self._forward_lifecycle_result(self._wrapped_transport.close())

    def __enter__(self) -> CorrelationIDTransport:
        """Enter the transport context (required by httpx.Client).

        Returns
        -------
        CorrelationIDTransport
            This transport instance.

        """
        self._wrapped_transport.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        """Exit the transport context (required by httpx.Client)."""
        wrapped = typ.cast("_SupportsSyncExit", self._wrapped_transport)
        return self._forward_lifecycle_result(
            wrapped.__exit__(exc_type, exc_value, traceback)
        )


class AsyncCorrelationIDTransport(
    _CorrelationIDTransportBase[_AsyncWrappedTransport],
    _AsyncBaseTransport,
):
    """Inject correlation IDs into async requests before transport delegation."""

    # __init__ inherited from _CorrelationIDTransportBase

    async def handle_async_request(
        self,
        request: httpx.Request,
    ) -> httpx.Response:
        """Add the correlation ID header and delegate the request.

        Returns
        -------
        httpx.Response
            The response returned by the wrapped transport.

        """
        self._prepare_request(request)
        return await self._wrapped_transport.handle_async_request(request)

    # @codescene(disable:"Code Duplication") Explicit protocol methods (2026-10-25).
    async def aclose(self) -> None:
        """Delegate shutdown to the wrapped transport.

        Returns
        -------
        None
            The declared HTTPX contract is ``None``. At runtime, the wrapped
            transport's result is forwarded unchanged.

        """
        result = await self._wrapped_transport.aclose()
        return self._forward_lifecycle_result(result)

    async def __aenter__(self) -> AsyncCorrelationIDTransport:
        """Enter the async transport context (required by httpx.AsyncClient).

        Returns
        -------
        AsyncCorrelationIDTransport
            This transport instance.

        """
        await self._wrapped_transport.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        """Exit the async transport context (required by httpx.AsyncClient)."""
        wrapped = typ.cast("_SupportsAsyncExit", self._wrapped_transport)
        return self._forward_lifecycle_result(
            await wrapped.__aexit__(exc_type, exc_value, traceback)
        )


def request_with_correlation_id(
    method: str,
    url: str,
    **kwargs: typ.Any,  # ruff: ignore[any-type] -- mirrors flexible httpx request kwargs.
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
    _require_httpx()
    import httpx

    headers, request_kwargs = _prepare_headers(kwargs)
    return httpx.request(method, url, headers=headers, **request_kwargs)


async def async_request_with_correlation_id(
    method: str,
    url: str,
    **kwargs: typ.Any,  # ruff: ignore[any-type] -- mirrors flexible httpx request kwargs.
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
    _require_httpx()
    import httpx

    headers, request_kwargs = _prepare_headers(kwargs)
    async with httpx.AsyncClient() as client:
        return await client.request(method, url, headers=headers, **request_kwargs)


def _prepare_headers(
    kwargs: cabc.Mapping[str, typ.Any],
) -> tuple[httpx.Headers, dict[str, typ.Any]]:
    """Prepare headers and request arguments without mutating the input.

    Parameters
    ----------
    kwargs : Mapping[str, Any]
        A read-only mapping of request keyword arguments.

    Returns
    -------
    tuple[httpx.Headers, dict[str, Any]]
        New headers and a shallow copy of the request arguments without
        ``headers``. Neither the input mapping nor a caller-supplied header
        object is mutated.

    Notes
    -----
    Repeated header entries are preserved. Header names are case-insensitive,
    so any caller-supplied correlation ID header prevents injection.

    """
    _require_httpx()
    import httpx

    raw_headers = kwargs.get("headers")
    request_kwargs = {key: value for key, value in kwargs.items() if key != "headers"}
    headers = httpx.Headers(raw_headers) if raw_headers is not None else httpx.Headers()

    _inject_correlation_id_header(headers)
    return headers, request_kwargs
