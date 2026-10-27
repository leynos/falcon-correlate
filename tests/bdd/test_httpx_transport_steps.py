"""Step definitions for HTTPX transport propagation through Falcon middleware."""

from __future__ import annotations

import typing as typ
from http import HTTPStatus

import falcon
import pytest

# Skip the module before importing HTTPX-backed adapter or recording helpers.
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
    AsyncCorrelationIDTransport,
    CorrelationIDTransport,
)
from falcon_correlate.unittests.test_httpx_transport_helpers import (  # ruff: ignore[module-import-not-at-top-of-file] -- dependency probe first.
    _assert_header,
    _recorded_request,
    _RecordingAsyncTransport,
    _RecordingTransport,
)
from tests.bdd.httpx_test_helpers import (  # ruff: ignore[module-import-not-at-top-of-file] -- dependency probe first.
    build_test_client,
    dispatch_inbound_request,
)

scenarios("httpx_transport.feature")


class Context(typ.TypedDict, total=False):
    """State shared by the HTTPX transport steps."""

    client: falcon.testing.TestClient
    response: falcon.testing.Result
    transport: _RecordingTransport | _RecordingAsyncTransport


class _SyncTransportResource:
    """Make a real HTTPX client request through a recording sync transport."""

    def __init__(
        self, header_name: str | None = None, headers: dict[str, str] | None = None
    ) -> None:
        """Create the transport that records this resource's outbound request."""
        self.header_name = header_name
        self.headers = headers
        self.transport = _RecordingTransport()

    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """Send the outbound request while Falcon middleware context is active."""
        with httpx.Client(
            transport=CorrelationIDTransport(
                self.transport, **({"header_name": self.header_name} if self.header_name else {})
            ),
        ) as client:
            client.get("http://example.com", headers=self.headers)
        resp.status = HTTPStatus.OK


class _AsyncTransportResource:
    """Make a real HTTPX client request through a recording async transport."""

    def __init__(
        self, header_name: str | None = None, headers: dict[str, str] | None = None
    ) -> None:
        """Create the transport that records this resource's outbound request."""
        self.header_name = header_name
        self.headers = headers
        self.transport = _RecordingAsyncTransport()

    async def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """Send the outbound request while Falcon middleware context is active."""
        async with httpx.AsyncClient(
            transport=AsyncCorrelationIDTransport(
                self.transport, **({"header_name": self.header_name} if self.header_name else {})
            ),
        ) as client:
            await client.get("http://example.com", headers=self.headers)
        resp.status = HTTPStatus.OK


def _build_transport_context(
    mode: typ.Literal["sync", "async"],
    header_name: str | None = None,
    headers: dict[str, str] | None = None,
) -> Context:
    """Build a Falcon client and recording transport for one mode."""
    match mode:
        case "sync":
            resource = _SyncTransportResource(header_name, headers)
        case "async":
            resource = _AsyncTransportResource(header_name, headers)

    return {
        "client": build_test_client(mode, resource),
        "transport": resource.transport,
    }


@pytest.fixture(autouse=True)
def _reset_context_variables() -> cabc.Generator[None, None, None]:
    """Reset request context after each Falcon scenario."""
    yield
    correlation_id_var.set(None)


@given(
    parsers.parse(
        "a {mode} Falcon app with a trusted source and HTTPX recording transport"
    ),
    target_fixture="context",
)
def given_recording_transport_app(mode: typ.Literal["sync", "async"]) -> Context:
    """Build the real Falcon request boundary for a sync or async transport."""
    return _build_transport_context(mode)


@given(
    parsers.parse(
        'a {mode} Falcon app with a trusted source and HTTPX recording transport '
        'configured with header "{header_name}"'
    ),
    target_fixture="context",
)
def given_custom_transport_app(
    mode: typ.Literal["sync", "async"], header_name: str
) -> Context:
    """Build a Falcon app with a custom transport header."""
    return _build_transport_context(mode, header_name)


@given(
    parsers.parse(
        'a {mode} Falcon app with a trusted source and HTTPX recording transport '
        'configured with header "{header_name}" and existing header "{name}" '
        'set to "{value}"'
    ),
    target_fixture="context",
)
def given_transport_app_with_header(
    mode: typ.Literal["sync", "async"], header_name: str, name: str, value: str
) -> Context:
    """Build a Falcon app with a caller-supplied outbound header."""
    return _build_transport_context(mode, header_name, {name: value})


@when(
    parsers.parse(
        'I dispatch an inbound Falcon request with correlation ID "{correlation_id}"'
    ),
    target_fixture="context",
)
def when_dispatch_with_trusted_id(context: Context, correlation_id: str) -> Context:
    """Dispatch a trusted inbound request through Falcon middleware."""
    response = dispatch_inbound_request(context["client"], correlation_id)
    context["response"] = response
    failure_message = (
        f"expected Falcon status {HTTPStatus.OK}, got {response.status_code}"
    )
    assert response.status_code == HTTPStatus.OK, failure_message
    return context


@then(
    parsers.parse(
        'the recording transport should receive header "{name}" with value "{value}"'
    ),
)
def then_recorded_request_has_header(context: Context, name: str, value: str) -> None:
    """Verify the recording transport received the expected correlation header."""
    _assert_header(context["transport"], name, value)


@then(parsers.parse('the recording transport should not receive header "{name}"'))
def then_recorded_request_lacks_header(context: Context, name: str) -> None:
    """Verify the recorded request does not contain the header."""
    assert name not in _recorded_request(context["transport"]).headers
