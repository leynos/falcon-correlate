"""Step definitions for httpx_propagation.feature."""

from __future__ import annotations

import typing as typ

import pytest

httpx = pytest.importorskip("httpx")

from unittest import mock  # noqa: E402

from pytest_bdd import given, parsers, scenarios, then, when  # noqa: E402

from falcon_correlate import correlation_id_var  # noqa: E402
from falcon_correlate.httpx import (  # noqa: E402
    async_request_with_correlation_id,
    request_with_correlation_id,
)

scenarios("httpx_propagation.feature")


def _run_async_request(**kwargs: typ.Any) -> dict[str, str]:  # noqa: ANN401
    """Run ``async_request_with_correlation_id`` with a mocked AsyncClient.

    Returns the headers dict captured from the mocked request call.
    """
    import asyncio

    async def _run() -> dict[str, str]:
        mock_response = httpx.Response(200)
        with mock.patch("httpx.AsyncClient") as mock_cls:
            mock_client = mock.AsyncMock()
            mock_client.request.return_value = mock_response
            mock_cls.return_value.__aenter__ = mock.AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = mock.AsyncMock(return_value=False)
            await async_request_with_correlation_id(
                "GET", "http://example.com", **kwargs
            )
            return dict(mock_client.request.call_args.kwargs["headers"])

    return asyncio.run(_run())


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
    """Ensure no correlation ID is set (default state)."""
    correlation_id_var.set(None)
    return {}


@when(
    "I send a request using the correlation ID wrapper",
    target_fixture="context",
)
def when_send_request(context: Context) -> Context:
    """Send a sync request using the wrapper and capture headers."""
    with mock.patch("httpx.request") as mock_request:
        mock_request.return_value = httpx.Response(200)
        request_with_correlation_id("GET", "http://example.com")
        context["captured_headers"] = dict(mock_request.call_args.kwargs["headers"])
    return context


@when(
    parsers.parse('I send a request with existing header "{name}" set to "{value}"'),
    target_fixture="context",
)
def when_send_request_with_header(context: Context, name: str, value: str) -> Context:
    """Send a sync request with an existing header."""
    with mock.patch("httpx.request") as mock_request:
        mock_request.return_value = httpx.Response(200)
        request_with_correlation_id(
            "GET",
            "http://example.com",
            headers={name: value},
        )
        context["captured_headers"] = dict(mock_request.call_args.kwargs["headers"])
    return context


@when(
    "I send an async request using the correlation ID wrapper",
    target_fixture="context",
)
def when_send_async_request(context: Context) -> Context:
    """Send an async request using the wrapper and capture headers."""
    context["captured_headers"] = _run_async_request()
    return context


@when(
    parsers.parse(
        'I send an async request with existing header "{name}" set to "{value}"'
    ),
    target_fixture="context",
)
def when_send_async_request_with_header(
    context: Context, name: str, value: str
) -> Context:
    """Send an async request with an existing header."""
    context["captured_headers"] = _run_async_request(headers={name: value})
    return context


@then(
    parsers.parse(
        'the outgoing request should contain header "{name}" with value "{value}"'
    ),
)
def then_header_present(context: Context, name: str, value: str) -> None:
    """Verify the outgoing request contains the expected header."""
    headers = context["captured_headers"]
    # HTTP headers are case-insensitive; httpx.Headers normalizes to lowercase
    header_key = next((k for k in headers if k.lower() == name.lower()), None)
    assert header_key is not None, f"header {name!r} not found in {headers!r}"
    assert headers[header_key] == value, (
        f"expected {name}={value!r}, got {headers[header_key]!r}"
    )


@then(
    parsers.parse('the outgoing request should not contain header "{name}"'),
)
def then_header_absent(context: Context, name: str) -> None:
    """Verify the outgoing request does not contain the header."""
    headers = context["captured_headers"]
    # HTTP headers are case-insensitive
    header_key = next((k for k in headers if k.lower() == name.lower()), None)
    assert header_key is None, f"header {name!r} unexpectedly found in {headers!r}"
