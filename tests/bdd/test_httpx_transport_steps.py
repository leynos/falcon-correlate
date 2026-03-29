"""Step definitions for httpx_transport.feature.

This module provides pytest-bdd step definitions that verify correlation ID
propagation through httpx transport wrappers. It tests both sync
(CorrelationIDTransport) and async (AsyncCorrelationIDTransport) transport
classes to ensure they correctly inject correlation IDs into outgoing HTTP
requests and preserve explicitly-set headers.

Usage
-----
Run the BDD scenarios with pytest::

    pytest tests/bdd/test_httpx_transport_steps.py

Or run the entire BDD suite::

    pytest tests/bdd/

Example:
-------
A typical scenario from httpx_transport.feature::

    Given the correlation ID is set to "test-correlation-id"
    When I send a request using an httpx client with the correlation transport
    Then the outgoing request should contain header "X-Correlation-ID"
         with value "test-correlation-id"

The steps defined here handle context setup (Given), request execution (When),
and header verification (Then).

"""

from __future__ import annotations

import asyncio
import typing as typ

import pytest

# Skip the entire test module if httpx is not installed (optional dependency).
# This MUST happen before importing falcon_correlate.httpx, which requires httpx.
# The E402 warnings below are unavoidable: pytest.importorskip() is executable
# code that validates the dependency before we can safely import modules that
# depend on it. Without this ordering, the test module would fail to collect
# in environments where httpx is not available.
httpx = pytest.importorskip("httpx")

from pytest_bdd import given, parsers, scenarios, then, when  # noqa: E402

from falcon_correlate import correlation_id_var  # noqa: E402
from falcon_correlate.httpx import (  # noqa: E402
    AsyncCorrelationIDTransport,
    CorrelationIDTransport,
)

scenarios("httpx_transport.feature")


class RecordingTransport(httpx.BaseTransport):
    """Capture sync requests made by the configured client."""

    def __init__(self) -> None:
        """Initialise the transport with no captured request."""
        self.request: httpx.Request | None = None

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Capture the request and return a success response."""
        self.request = request
        return httpx.Response(200, request=request)


class RecordingAsyncTransport(httpx.AsyncBaseTransport):
    """Capture async requests made by the configured client."""

    def __init__(self) -> None:
        """Initialise the transport with no captured request."""
        self.request: httpx.Request | None = None

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Capture the request and return a success response."""
        self.request = request
        return httpx.Response(200, request=request)


class Context(typ.TypedDict, total=False):
    """Type definition for test context."""

    captured_headers: dict[str, str]


@pytest.fixture(autouse=True)
def _reset_context_variables() -> typ.Generator[None, None, None]:
    """Reset context variables after each scenario."""
    yield
    correlation_id_var.set(None)


@given(
    parsers.parse('the correlation ID is set to "{value}"'),
    target_fixture="context",
)
def given_correlation_id_set(value: str) -> Context:
    """Set the correlation ID context variable."""
    correlation_id_var.set(value)
    return {}


@given("no correlation ID is set", target_fixture="context")
def given_no_correlation_id() -> Context:
    """Ensure no correlation ID is set."""
    correlation_id_var.set(None)
    return {}


@when(
    "I send a request using an httpx client with the correlation transport",
    target_fixture="context",
)
def when_send_request_with_transport(context: Context) -> Context:
    """Send a sync request with a client configured to use the transport."""
    transport = RecordingTransport()

    with httpx.Client(transport=CorrelationIDTransport(transport)) as client:
        client.get("http://example.com")

    assert transport.request is not None, (
        "expected RecordingTransport to have captured a request"
    )
    context["captured_headers"] = dict(transport.request.headers)
    return context


@when(
    "I send an async request using an httpx client with the correlation transport",
    target_fixture="context",
)
def when_send_async_request_with_transport(context: Context) -> Context:
    """Send an async request with a client configured to use the transport."""

    async def _run() -> dict[str, str]:
        transport = RecordingAsyncTransport()
        async with httpx.AsyncClient(
            transport=AsyncCorrelationIDTransport(transport)
        ) as client:
            await client.get("http://example.com")

        assert transport.request is not None, (
            "expected RecordingAsyncTransport to have captured a request"
        )
        assert transport.request.headers is not None, (
            "expected transport.request.headers to be present"
        )
        return dict(transport.request.headers)

    context["captured_headers"] = asyncio.run(_run())
    return context


@then(
    parsers.parse(
        'the outgoing request should contain header "{name}" with value "{value}"'
    ),
)
def then_header_present(context: Context, name: str, value: str) -> None:
    """Verify the outgoing request contains the expected header."""
    headers = context["captured_headers"]
    header_key = next((key for key in headers if key.lower() == name.lower()), None)
    assert header_key is not None, f"header {name!r} not found in {headers!r}"
    actual = headers[header_key]
    assert actual == value, (
        f"Expected header {header_key!r} to be {value!r} but was {actual!r}"
    )


@then(parsers.parse('the outgoing request should not contain header "{name}"'))
def then_header_absent(context: Context, name: str) -> None:
    """Verify the outgoing request does not contain the header."""
    headers = context["captured_headers"]
    header_key = next((key for key in headers if key.lower() == name.lower()), None)
    assert header_key is None, f"header {name!r} unexpectedly found in {headers!r}"
