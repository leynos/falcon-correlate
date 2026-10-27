"""Step definitions for HTTPX wrapper propagation through Falcon middleware."""

from __future__ import annotations

import typing as typ
from http import HTTPStatus
from unittest import mock

import falcon
import pytest

httpx = pytest.importorskip("httpx")

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    import falcon.testing

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
    async_request_with_correlation_id,
    request_with_correlation_id,
)
from falcon_correlate.middleware import (  # ruff: ignore[module-import-not-at-top-of-file] -- dependency probe first.
    DEFAULT_HEADER_NAME,
)
from tests.bdd.httpx_test_helpers import (  # ruff: ignore[module-import-not-at-top-of-file] -- dependency probe first.
    build_test_client,
    dispatch_inbound_request,
)

scenarios("httpx_propagation.feature")


class Context(typ.TypedDict, total=False):
    """State shared by the HTTPX wrapper steps."""

    mode: typ.Literal["sync", "async"]
    client: falcon.testing.TestClient
    response: falcon.testing.Result
    captured_headers: dict[str, str]


class _SyncWrapperResource:
    """Call the synchronous correlation wrapper from a Falcon request."""

    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """Make one outbound request through the synchronous wrapper."""
        request_with_correlation_id("GET", "http://example.com")


class _AsyncWrapperResource:
    """Call the asynchronous correlation wrapper from a Falcon request."""

    async def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """Make one outbound request through the asynchronous wrapper."""
        await async_request_with_correlation_id("GET", "http://example.com")


def _build_wrapper_context(
    mode: typ.Literal["sync", "async"],
    generated_id: str | None = None,
) -> Context:
    """Build the real Falcon request boundary for one wrapper mode."""
    match mode:
        case "sync":
            resource = _SyncWrapperResource()
        case "async":
            resource = _AsyncWrapperResource()

    return {
        "mode": mode,
        "client": build_test_client(mode, resource, generated_id=generated_id),
    }


def _dispatch_with_httpx_patches(
    context: Context,
    correlation_id: str | None,
) -> Context:
    """Hold HTTPX patches through real Falcon test-client dispatch."""
    sync_response = httpx.Response(200)
    async_response = httpx.Response(200)
    async_client = mock.AsyncMock()
    async_client.request.return_value = async_response

    with (
        mock.patch("httpx.request", return_value=sync_response) as sync_request,
        mock.patch("httpx.AsyncClient") as async_client_class,
    ):
        async_client_class.return_value.__aenter__ = mock.AsyncMock(
            return_value=async_client
        )
        async_client_class.return_value.__aexit__ = mock.AsyncMock(return_value=False)
        response = dispatch_inbound_request(
            context["client"],
            correlation_id,
        )
        context["response"] = response
        failure_message = (
            f"expected Falcon status {HTTPStatus.OK}, got {response.status_code}"
        )
        assert response.status_code == HTTPStatus.OK, failure_message

        match context["mode"]:
            case "sync":
                request_call = sync_request.call_args
            case "async":
                request_call = async_client.request.call_args

        failure_message = "expected the wrapper to call HTTPX during Falcon dispatch"
        assert request_call is not None, failure_message
        context["captured_headers"] = dict(request_call.kwargs.get("headers", {}))

    return context


@pytest.fixture(autouse=True)
def _reset_context_variables() -> cabc.Generator[None, None, None]:
    """Reset request context after each Falcon scenario."""
    yield
    correlation_id_var.set(None)


@given(
    parsers.parse("a {mode} Falcon app with a trusted source and HTTPX wrapper"),
    target_fixture="context",
)
def given_trusted_source_wrapper_app(
    mode: typ.Literal["sync", "async"],
) -> Context:
    """Build a WSGI or ASGI app for trusted inbound wrapper propagation."""
    return _build_wrapper_context(mode)


@given(
    parsers.parse(
        'a {mode} Falcon app with a generated ID "{generated_id}" and HTTPX wrapper'
    ),
    target_fixture="context",
)
def given_generated_id_wrapper_app(
    mode: typ.Literal["sync", "async"],
    generated_id: str,
) -> Context:
    """Build a WSGI or ASGI app with a deterministic generated correlation ID."""
    return _build_wrapper_context(mode, generated_id)


@when(
    parsers.parse(
        'I dispatch an inbound Falcon request with correlation ID "{correlation_id}"'
    ),
    target_fixture="context",
)
def when_dispatch_with_trusted_id(context: Context, correlation_id: str) -> Context:
    """Dispatch a trusted inbound request while HTTPX calls are patched."""
    return _dispatch_with_httpx_patches(context, correlation_id)


@when(
    "I dispatch an inbound Falcon request without a correlation ID",
    target_fixture="context",
)
def when_dispatch_without_correlation_id(context: Context) -> Context:
    """Dispatch a request that makes middleware generate its correlation ID."""
    return _dispatch_with_httpx_patches(context, None)


@then(
    parsers.parse(
        'the outgoing request should contain header "{name}" with value "{value}"'
    ),
)
def then_header_present(context: Context, name: str, value: str) -> None:
    """Verify the outbound wrapper call contains the expected header."""
    headers = context["captured_headers"]
    header_key = next((key for key in headers if key.lower() == name.lower()), None)
    assert header_key is not None, f"header {name!r} not found in {headers!r}"
    actual = headers[header_key]
    assert actual == value, (
        f"expected header {header_key!r} to be {value!r} but was {actual!r}"
    )


@then("the outbound correlation ID should match the echoed response header")
def then_outbound_id_matches_echoed_response_header(context: Context) -> None:
    """Verify the generated outbound ID equals the middleware response echo."""
    outbound_id = next(
        (
            value
            for name, value in context["captured_headers"].items()
            if name.lower() == DEFAULT_HEADER_NAME.lower()
        ),
        None,
    )
    response_id = context["response"].headers.get(DEFAULT_HEADER_NAME)
    assert outbound_id is not None, "expected the outbound correlation header"
    failure_message = (
        f"expected response ID {response_id!r} to equal outbound ID {outbound_id!r}"
    )
    assert response_id == outbound_id, failure_message
