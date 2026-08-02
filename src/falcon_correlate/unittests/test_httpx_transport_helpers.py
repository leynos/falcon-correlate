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
    expected: str | None,
) -> None:
    """Assert that the sole recorded request has the expected header."""
    request = _recorded_request(transport)
    if expected is None:
        failure_message = (
            f"expected header {name!r} to be absent, got {request.headers!r}"
        )
        assert name not in request.headers, failure_message
        return

    failure_message = f"expected header {name!r}={expected!r}, got {request.headers!r}"
    assert request.headers[name] == expected, failure_message


def _assert_response_ok(response: httpx.Response) -> None:
    """Assert that a transport response has the expected success status."""
    failure_message = f"expected status {_OK_STATUS}, got {response.status_code}"
    assert response.status_code == _OK_STATUS, failure_message


def _recorded_request(transport: _RecordingTransportT) -> httpx.Request:
    """Return the single request captured by a recording transport."""
    failure_message = f"expected one recorded request, got {transport.requests!r}"
    assert len(transport.requests) == 1, failure_message
    return transport.requests[0]
