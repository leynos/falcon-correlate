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

from pytest_bdd import (  # ruff: ignore[module-import-not-at-top-of-file] -- dependency probe first.
    given,
    parsers,
    scenarios,
    then,
    when,
)

from falcon_correlate import (  # ruff: ignore[module-import-not-at-top-of-file] -- dependency probe first.
    correlation_id_var,
)
from falcon_correlate.httpx import (  # ruff: ignore[module-import-not-at-top-of-file] -- dependency probe first.
    AsyncCorrelationIDTransport,
    CorrelationIDTransport,
)
from falcon_correlate.unittests.test_httpx_transport_helpers import (  # ruff: ignore[module-import-not-at-top-of-file] -- dependency probe first.
    _recorded_request,
    _RecordingAsyncTransport,
    _RecordingTransport,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc

scenarios("httpx_transport.feature")


class Context(typ.TypedDict, total=False):
    """Type definition for test context."""

    captured_headers: dict[str, str]


@pytest.fixture(autouse=True)
def _reset_context_variables() -> cabc.Generator[None, None, None]:
    """Reset context variables after each scenario."""
    yield
    correlation_id_var.set(None)


@given(
    parsers.parse('the correlation ID is set to "{value}"'),
    target_fixture="context",
)
def given_correlation_id_set(value: str) -> Context:
    """Set the correlation ID context variable.

    Parameters
    ----------
    value : str
        Correlation ID to store in the context variable.

    Returns
    -------
    Context
        The value produced for the test scenario.

    """
    correlation_id_var.set(value)
    return {}


@given("no correlation ID is set", target_fixture="context")
def given_no_correlation_id() -> Context:
    """Ensure no correlation ID is set.

    Returns
    -------
    Context
        The value produced for the test scenario.

    """
    correlation_id_var.set(None)
    return {}


@when(
    "I send a request using an httpx client with the correlation transport",
    target_fixture="context",
)
def when_send_request_with_transport(context: Context) -> Context:
    """Send a sync request with a client configured to use the transport.

    Parameters
    ----------
    context : Context
        Scenario state passed through the step chain.

    Returns
    -------
    Context
        The value produced for the test scenario.

    """
    transport = _RecordingTransport()

    with httpx.Client(transport=CorrelationIDTransport(transport)) as client:
        client.get("http://example.com")

    context["captured_headers"] = dict(_recorded_request(transport).headers)
    return context


@when(
    "I send an async request using an httpx client with the correlation transport",
    target_fixture="context",
)
def when_send_async_request_with_transport(context: Context) -> Context:
    """Send an async request with a client configured to use the transport.

    Parameters
    ----------
    context : Context
        Scenario state passed through the step chain.

    Returns
    -------
    Context
        The value produced for the test scenario.

    """

    async def _run() -> dict[str, str]:
        transport = _RecordingAsyncTransport()
        async with httpx.AsyncClient(
            transport=AsyncCorrelationIDTransport(transport)
        ) as client:
            await client.get("http://example.com")

        return dict(_recorded_request(transport).headers)

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
