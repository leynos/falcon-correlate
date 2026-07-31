"""Shared recording transports and assertions for httpx transport tests."""

from __future__ import annotations

import pytest

httpx = pytest.importorskip("httpx")

_OK_STATUS = 200


class _RecordingTransport(httpx.BaseTransport):
    """Capture sync requests received by a client transport."""

    def __init__(self) -> None:
        """Initialize an empty request log."""
        self.requests: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Capture the request and return a simple response."""
        self.requests.append(request)
        return httpx.Response(_OK_STATUS, request=request)


class _RecordingAsyncTransport(httpx.AsyncBaseTransport):
    """Capture async requests received by a client transport."""

    def __init__(self) -> None:
        """Initialize an empty request log."""
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Capture the request and return a simple response."""
        self.requests.append(request)
        return httpx.Response(_OK_STATUS, request=request)


type _RecordingTransportT = _RecordingTransport | _RecordingAsyncTransport


def _assert_header(
    transport: _RecordingTransportT,
    name: str,
    expected: str,
) -> None:
    """Assert that the sole recorded request has the expected header."""
    request = _recorded_request(transport)
    assert request.headers[name] == expected, (
        f"expected header {name!r}={expected!r}, got {request.headers!r}"
    )


def _assert_header_absent(transport: _RecordingTransportT, name: str) -> None:
    """Assert that the sole recorded request omits a header."""
    request = _recorded_request(transport)
    assert name not in request.headers, (
        f"expected header {name!r} to be absent, got {request.headers!r}"
    )


def _assert_response_ok(response: httpx.Response) -> None:
    """Assert that a transport response has the expected success status."""
    assert response.status_code == _OK_STATUS, (
        f"expected status {_OK_STATUS}, got {response.status_code}"
    )


def _recorded_request(transport: _RecordingTransportT) -> httpx.Request:
    """Return the single request captured by a recording transport."""
    assert len(transport.requests) == 1, (
        f"expected one recorded request, got {transport.requests!r}"
    )
    return transport.requests[0]
