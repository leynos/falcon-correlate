"""Unit tests for httpx correlation ID transport classes."""

from __future__ import annotations

import contextlib
import typing as typ

import pytest

# Skip the entire test module if httpx is not installed (optional dependency).
# This MUST happen before importing falcon_correlate.httpx, which requires httpx.
# The E402 warnings below are unavoidable: pytest.importorskip() is executable
# code that validates the dependency before we can safely import modules that
# depend on it. Without this ordering, the test module would fail to collect
# in environments where httpx is not available.
httpx = pytest.importorskip("httpx")

from unittest import mock  # noqa: E402

if typ.TYPE_CHECKING:
    import collections.abc as cabc

from falcon_correlate import correlation_id_var  # noqa: E402
from falcon_correlate.httpx import (  # noqa: E402
    AsyncCorrelationIDTransport,
    CorrelationIDTransport,
)
from falcon_correlate.middleware import DEFAULT_HEADER_NAME  # noqa: E402

_OK_STATUS = 200


@contextlib.contextmanager
def _cid_context(cid: str) -> typ.Generator[None, None, None]:
    """Set *cid* on ``correlation_id_var`` for the duration of the block."""
    token = correlation_id_var.set(cid)
    try:
        yield
    finally:
        correlation_id_var.reset(token)


def _make_delegation_request() -> httpx.Request:
    """Return a fresh GET request suitable for delegation tests."""
    return httpx.Request("GET", "http://example.com")


class RecordingTransport(httpx.BaseTransport):
    """Capture sync requests received by a client transport."""

    def __init__(self) -> None:
        """Initialise an empty request log."""
        self.requests: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Capture the request and return a simple response."""
        self.requests.append(request)
        return httpx.Response(200, request=request)


class RecordingAsyncTransport(httpx.AsyncBaseTransport):
    """Capture async requests received by a client transport."""

    def __init__(self) -> None:
        """Initialise an empty request log."""
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Capture the request and return a simple response."""
        self.requests.append(request)
        return httpx.Response(200, request=request)


def test_sync_transport_injects_header_when_context_is_set(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
) -> None:
    """Sync transport should add the correlation header before delegation."""
    transport = RecordingTransport()
    wrapped_transport = CorrelationIDTransport(transport)

    def _logic() -> None:
        correlation_id_var.set("sync-transport-cid")
        with httpx.Client(transport=wrapped_transport) as client:
            response = client.get("http://example.com")

        assert response.status_code == _OK_STATUS
        assert len(transport.requests) == 1
        assert transport.requests[0].headers[DEFAULT_HEADER_NAME] == (
            "sync-transport-cid"
        )

    isolated_context(_logic)


def test_sync_transport_does_not_add_header_when_context_is_empty(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
) -> None:
    """Sync transport should leave the request unchanged with no correlation ID."""
    transport = RecordingTransport()
    wrapped_transport = CorrelationIDTransport(transport)

    def _logic() -> None:
        with httpx.Client(transport=wrapped_transport) as client:
            client.get("http://example.com")

        assert len(transport.requests) == 1
        assert DEFAULT_HEADER_NAME not in transport.requests[0].headers

    isolated_context(_logic)


def test_sync_transport_preserves_existing_correlation_header(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
) -> None:
    """Sync transport should not overwrite an explicit caller header."""
    transport = RecordingTransport()
    wrapped_transport = CorrelationIDTransport(transport)

    def _logic() -> None:
        correlation_id_var.set("ignored-context-cid")
        with httpx.Client(transport=wrapped_transport) as client:
            client.get(
                "http://example.com",
                headers={DEFAULT_HEADER_NAME: "caller-cid"},
            )

        assert transport.requests[0].headers[DEFAULT_HEADER_NAME] == "caller-cid"

    isolated_context(_logic)


def test_sync_transport_delegates_same_request_object() -> None:
    """Sync transport should delegate exactly once with the mutated request."""
    cid = "delegated-sync-cid"
    request = _make_delegation_request()
    transport = mock.Mock(spec=httpx.BaseTransport)
    transport.handle_request.return_value = httpx.Response(200, request=request)
    wrapped_transport = CorrelationIDTransport(transport)

    with _cid_context(cid):
        wrapped_transport.handle_request(request)

    transport.handle_request.assert_called_once_with(request)
    assert request.headers[DEFAULT_HEADER_NAME] == cid


def test_sync_transport_delegates_close() -> None:
    """Sync transport should forward close calls to the wrapped transport."""
    transport = mock.Mock(spec=httpx.BaseTransport)
    wrapped_transport = CorrelationIDTransport(transport)

    wrapped_transport.close()

    transport.close.assert_called_once_with()


def test_sync_transport_uses_custom_header_name(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
) -> None:
    """Sync transport should use the configured custom header name when set."""
    transport = RecordingTransport()
    wrapped_transport = CorrelationIDTransport(transport, header_name="X-Alt-CID")

    def _logic() -> None:
        correlation_id_var.set("sync-transport-alt-cid")
        with httpx.Client(transport=wrapped_transport) as client:
            response = client.get("http://example.com")

        assert response.status_code == _OK_STATUS
        assert len(transport.requests) == 1
        assert transport.requests[0].headers["X-Alt-CID"] == "sync-transport-alt-cid"
        assert DEFAULT_HEADER_NAME not in transport.requests[0].headers

    isolated_context(_logic)


def test_sync_transport_does_not_override_existing_custom_header(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
) -> None:
    """Sync transport should not overwrite an explicitly provided custom header."""
    transport = RecordingTransport()
    wrapped_transport = CorrelationIDTransport(transport, header_name="X-Alt-CID")

    def _logic() -> None:
        correlation_id_var.set("sync-transport-alt-cid")
        with httpx.Client(transport=wrapped_transport) as client:
            response = client.get(
                "http://example.com",
                headers={"X-Alt-CID": "explicit-sync-header"},
            )

        assert response.status_code == _OK_STATUS
        assert len(transport.requests) == 1
        assert transport.requests[0].headers["X-Alt-CID"] == "explicit-sync-header"

    isolated_context(_logic)


@pytest.mark.asyncio
async def test_async_transport_injects_header_when_context_is_set() -> None:
    """Async transport should add the correlation header before delegation."""
    transport = RecordingAsyncTransport()
    wrapped_transport = AsyncCorrelationIDTransport(transport)

    with _cid_context("async-transport-cid"):
        async with httpx.AsyncClient(transport=wrapped_transport) as client:
            response = await client.get("http://example.com")

    assert response.status_code == _OK_STATUS
    assert len(transport.requests) == 1
    assert transport.requests[0].headers[DEFAULT_HEADER_NAME] == ("async-transport-cid")


@pytest.mark.asyncio
async def test_async_transport_does_not_add_header_when_context_is_empty() -> None:
    """Async transport should leave the request unchanged with no correlation ID."""
    transport = RecordingAsyncTransport()
    wrapped_transport = AsyncCorrelationIDTransport(transport)

    async with httpx.AsyncClient(transport=wrapped_transport) as client:
        await client.get("http://example.com")

    assert len(transport.requests) == 1
    assert DEFAULT_HEADER_NAME not in transport.requests[0].headers


@pytest.mark.asyncio
async def test_async_transport_preserves_existing_correlation_header() -> None:
    """Async transport should not overwrite an explicit caller header."""
    transport = RecordingAsyncTransport()
    wrapped_transport = AsyncCorrelationIDTransport(transport)

    with _cid_context("ignored-async-context-cid"):
        async with httpx.AsyncClient(transport=wrapped_transport) as client:
            await client.get(
                "http://example.com",
                headers={DEFAULT_HEADER_NAME: "caller-async-cid"},
            )

    assert transport.requests[0].headers[DEFAULT_HEADER_NAME] == "caller-async-cid"


@pytest.mark.asyncio
async def test_async_transport_delegates_same_request_object() -> None:
    """Async transport should delegate exactly once with the mutated request."""
    cid = "delegated-async-cid"
    request = _make_delegation_request()
    transport = mock.AsyncMock(spec=httpx.AsyncBaseTransport)
    transport.handle_async_request.return_value = httpx.Response(200, request=request)
    wrapped_transport = AsyncCorrelationIDTransport(transport)

    with _cid_context(cid):
        await wrapped_transport.handle_async_request(request)

    transport.handle_async_request.assert_awaited_once_with(request)
    assert request.headers[DEFAULT_HEADER_NAME] == cid


@pytest.mark.asyncio
async def test_async_transport_delegates_aclose() -> None:
    """Async transport should forward aclose calls to the wrapped transport."""
    transport = mock.AsyncMock(spec=httpx.AsyncBaseTransport)
    wrapped_transport = AsyncCorrelationIDTransport(transport)

    await wrapped_transport.aclose()

    transport.aclose.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_async_transport_uses_custom_header_name() -> None:
    """Async transport should use the configured custom header name when set."""
    transport = RecordingAsyncTransport()
    wrapped_transport = AsyncCorrelationIDTransport(
        transport,
        header_name="X-Alt-CID",
    )

    with _cid_context("async-transport-alt-cid"):
        async with httpx.AsyncClient(transport=wrapped_transport) as client:
            response = await client.get("http://example.com")

    assert response.status_code == _OK_STATUS
    assert len(transport.requests) == 1
    assert transport.requests[0].headers["X-Alt-CID"] == "async-transport-alt-cid"
    assert DEFAULT_HEADER_NAME not in transport.requests[0].headers


@pytest.mark.asyncio
async def test_async_transport_does_not_override_existing_custom_header() -> None:
    """Async transport should not overwrite an explicitly provided custom header."""
    transport = RecordingAsyncTransport()
    wrapped_transport = AsyncCorrelationIDTransport(
        transport,
        header_name="X-Alt-CID",
    )

    with _cid_context("async-transport-alt-cid"):
        async with httpx.AsyncClient(transport=wrapped_transport) as client:
            response = await client.get(
                "http://example.com",
                headers={"X-Alt-CID": "explicit-async-header"},
            )

    assert response.status_code == _OK_STATUS
    assert len(transport.requests) == 1
    assert transport.requests[0].headers["X-Alt-CID"] == "explicit-async-header"


def test_sync_transport_is_exported_from_package_root() -> None:
    """Sync transport should be re-exported from ``falcon_correlate``."""
    import falcon_correlate

    assert "CorrelationIDTransport" in falcon_correlate.__all__
    assert falcon_correlate.CorrelationIDTransport is CorrelationIDTransport


def test_async_transport_is_exported_from_package_root() -> None:
    """Async transport should be re-exported from ``falcon_correlate``."""
    import falcon_correlate

    assert "AsyncCorrelationIDTransport" in falcon_correlate.__all__
    assert falcon_correlate.AsyncCorrelationIDTransport is AsyncCorrelationIDTransport
