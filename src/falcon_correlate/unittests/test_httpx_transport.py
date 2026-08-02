"""Unit tests for httpx correlation ID transport classes."""

from __future__ import annotations

import asyncio
import contextlib
import typing as typ
from unittest import mock

import pytest

if typ.TYPE_CHECKING:
    import collections.abc as cabc

from falcon_correlate import correlation_id_var
from falcon_correlate.httpx import (
    AsyncCorrelationIDTransport,
    CorrelationIDTransport,
)
from falcon_correlate.middleware import DEFAULT_HEADER_NAME
from falcon_correlate.unittests.test_httpx_transport_helpers import (
    _assert_header,
    _assert_header_absent,
    _assert_response_ok,
    _RecordingAsyncTransport,
    _RecordingTransport,
)

# falcon_correlate.httpx is import-safe without optional httpx installed;
# importorskip only guards direct use of the optional httpx package below.
httpx = pytest.importorskip("httpx")


@contextlib.contextmanager
def _cid_context(cid: str) -> cabc.Generator[None, None, None]:
    """Set *cid* on ``correlation_id_var`` for the duration of the block."""
    token = correlation_id_var.set(cid)
    try:
        yield
    finally:
        correlation_id_var.reset(token)


def _make_delegation_request() -> httpx.Request:
    """Return a fresh GET request suitable for delegation tests.

    Returns
    -------
    httpx.Request
        The value produced for the test scenario.

    """
    return httpx.Request("GET", "http://example.com")


def test_sync_transport_injects_header_when_context_is_set(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
) -> None:
    """Sync transport should add the correlation header before delegation."""
    transport = _RecordingTransport()
    wrapped_transport = CorrelationIDTransport(transport)

    def _logic() -> None:
        """Exercise the isolated test scenario."""
        correlation_id_var.set("sync-transport-cid")
        with httpx.Client(transport=wrapped_transport) as client:
            response = client.get("http://example.com")

        _assert_response_ok(response)
        _assert_header(transport, DEFAULT_HEADER_NAME, "sync-transport-cid")

    isolated_context(_logic)


def test_sync_transport_does_not_add_header_when_context_is_empty(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
) -> None:
    """Sync transport should leave the request unchanged with no correlation ID."""
    transport = _RecordingTransport()
    wrapped_transport = CorrelationIDTransport(transport)

    def _logic() -> None:
        """Exercise the isolated test scenario."""
        with httpx.Client(transport=wrapped_transport) as client:
            client.get("http://example.com")

        _assert_header_absent(transport, DEFAULT_HEADER_NAME)

    isolated_context(_logic)


def test_sync_transport_preserves_existing_correlation_header(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
) -> None:
    """Sync transport should not overwrite an explicit caller header."""
    transport = _RecordingTransport()
    wrapped_transport = CorrelationIDTransport(transport)

    def _logic() -> None:
        """Exercise the isolated test scenario."""
        correlation_id_var.set("ignored-context-cid")
        with httpx.Client(transport=wrapped_transport) as client:
            client.get(
                "http://example.com",
                headers={DEFAULT_HEADER_NAME: "caller-cid"},
            )

        _assert_header(transport, DEFAULT_HEADER_NAME, "caller-cid")

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
    failure_message = "expected request.headers[DEFAULT_HEADER_NAME] to equal cid"
    assert request.headers[DEFAULT_HEADER_NAME] == cid, failure_message


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
    transport = _RecordingTransport()
    wrapped_transport = CorrelationIDTransport(transport, header_name="X-Alt-CID")

    def _logic() -> None:
        """Exercise the isolated test scenario."""
        correlation_id_var.set("sync-transport-alt-cid")
        with httpx.Client(transport=wrapped_transport) as client:
            response = client.get("http://example.com")

        _assert_response_ok(response)
        _assert_header(transport, "X-Alt-CID", "sync-transport-alt-cid")
        _assert_header_absent(transport, DEFAULT_HEADER_NAME)

    isolated_context(_logic)


def test_sync_transport_does_not_override_existing_custom_header(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
) -> None:
    """Sync transport should not overwrite an explicitly provided custom header."""
    transport = _RecordingTransport()
    wrapped_transport = CorrelationIDTransport(transport, header_name="X-Alt-CID")

    def _logic() -> None:
        """Exercise the isolated test scenario."""
        correlation_id_var.set("sync-transport-alt-cid")
        with httpx.Client(transport=wrapped_transport) as client:
            response = client.get(
                "http://example.com",
                headers={"X-Alt-CID": "explicit-sync-header"},
            )

        _assert_response_ok(response)
        _assert_header(transport, "X-Alt-CID", "explicit-sync-header")

    isolated_context(_logic)


@pytest.mark.asyncio
async def test_async_transport_injects_header_when_context_is_set() -> None:
    """Async transport should add the correlation header before delegation."""
    transport = _RecordingAsyncTransport()
    wrapped_transport = AsyncCorrelationIDTransport(transport)

    with _cid_context("async-transport-cid"):
        async with httpx.AsyncClient(transport=wrapped_transport) as client:
            response = await client.get("http://example.com")

    _assert_response_ok(response)
    _assert_header(transport, DEFAULT_HEADER_NAME, "async-transport-cid")


@pytest.mark.asyncio
async def test_async_transport_does_not_add_header_when_context_is_empty() -> None:
    """Async transport should leave the request unchanged with no correlation ID."""
    transport = _RecordingAsyncTransport()
    wrapped_transport = AsyncCorrelationIDTransport(transport)

    async with httpx.AsyncClient(transport=wrapped_transport) as client:
        await client.get("http://example.com")

    _assert_header_absent(transport, DEFAULT_HEADER_NAME)


@pytest.mark.asyncio
async def test_async_transport_preserves_existing_correlation_header() -> None:
    """Async transport should not overwrite an explicit caller header."""
    transport = _RecordingAsyncTransport()
    wrapped_transport = AsyncCorrelationIDTransport(transport)

    with _cid_context("ignored-async-context-cid"):
        async with httpx.AsyncClient(transport=wrapped_transport) as client:
            await client.get(
                "http://example.com",
                headers={DEFAULT_HEADER_NAME: "caller-async-cid"},
            )

    _assert_header(transport, DEFAULT_HEADER_NAME, "caller-async-cid")


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
    failure_message = "expected request.headers[DEFAULT_HEADER_NAME] to equal cid"
    assert request.headers[DEFAULT_HEADER_NAME] == cid, failure_message


@pytest.mark.asyncio
async def test_async_transport_delegates_aclose() -> None:
    """Async transport should forward aclose calls to the wrapped transport."""
    transport = mock.AsyncMock(spec=httpx.AsyncBaseTransport)
    wrapped_transport = AsyncCorrelationIDTransport(transport)

    await wrapped_transport.aclose()

    transport.aclose.assert_awaited_once_with()


@pytest.mark.parametrize(
    ("mock_factory", "transport_spec", "wrapped_cls", "exit_attr"),
    [
        pytest.param(
            mock.MagicMock,
            httpx.BaseTransport,
            CorrelationIDTransport,
            "__exit__",
            id="sync",
        ),
        pytest.param(
            mock.AsyncMock,
            httpx.AsyncBaseTransport,
            AsyncCorrelationIDTransport,
            "__aexit__",
            id="async",
        ),
    ],
)
@pytest.mark.asyncio
async def test_transport_preserves_exit_return_value(
    mock_factory: type,
    transport_spec: type,
    wrapped_cls: type,
    exit_attr: str,
) -> None:
    """Transport should preserve wrapped exception-suppression behaviour."""
    transport = mock_factory(spec=transport_spec)
    getattr(transport, exit_attr).return_value = True
    wrapped_transport = wrapped_cls(transport)

    raw = getattr(wrapped_transport, exit_attr)(
        RuntimeError,
        RuntimeError("boom"),
        None,
    )
    result = await raw if asyncio.iscoroutine(raw) else raw

    exit_mock = getattr(transport, exit_attr)
    if isinstance(transport, mock.AsyncMock):
        exit_mock.assert_awaited_once_with(RuntimeError, mock.ANY, None)
    else:
        exit_mock.assert_called_once_with(RuntimeError, mock.ANY, None)
    assert result is True, "expected result to be True"


@pytest.mark.asyncio
async def test_async_transport_uses_custom_header_name() -> None:
    """Async transport should use the configured custom header name when set."""
    transport = _RecordingAsyncTransport()
    wrapped_transport = AsyncCorrelationIDTransport(
        transport,
        header_name="X-Alt-CID",
    )

    with _cid_context("async-transport-alt-cid"):
        async with httpx.AsyncClient(transport=wrapped_transport) as client:
            response = await client.get("http://example.com")

    _assert_response_ok(response)
    _assert_header(transport, "X-Alt-CID", "async-transport-alt-cid")
    _assert_header_absent(transport, DEFAULT_HEADER_NAME)


@pytest.mark.asyncio
async def test_async_transport_does_not_override_existing_custom_header() -> None:
    """Async transport should not overwrite an explicitly provided custom header."""
    transport = _RecordingAsyncTransport()
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

    _assert_response_ok(response)
    _assert_header(transport, "X-Alt-CID", "explicit-async-header")


def test_sync_transport_is_exported_from_package_root() -> None:
    """Sync transport should be re-exported from ``falcon_correlate``."""
    import falcon_correlate

    failure_message = "expected condition: 'CorrelationIDTransport' in falcon_correl..."
    assert "CorrelationIDTransport" in falcon_correlate.__all__, failure_message
    failure_message = "expected condition: falcon_correlate.CorrelationIDTransport i..."
    assert falcon_correlate.CorrelationIDTransport is CorrelationIDTransport, (
        failure_message
    )


def test_async_transport_is_exported_from_package_root() -> None:
    """Async transport should be re-exported from ``falcon_correlate``."""
    import falcon_correlate

    failure_message = "expected condition: 'AsyncCorrelationIDTransport' in falcon_c..."
    assert "AsyncCorrelationIDTransport" in falcon_correlate.__all__, failure_message
    failure_message = "expected condition: falcon_correlate.AsyncCorrelationIDTransp..."
    assert (
        falcon_correlate.AsyncCorrelationIDTransport is AsyncCorrelationIDTransport
    ), failure_message
