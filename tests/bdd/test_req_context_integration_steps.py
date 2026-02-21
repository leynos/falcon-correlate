"""Step definitions for req_context_integration.feature."""

from __future__ import annotations

import time
import typing as typ
from concurrent.futures import ThreadPoolExecutor

import falcon
import falcon.testing
from pytest_bdd import given, parsers, scenarios, then, when

from falcon_correlate import CorrelationIDMiddleware, correlation_id_var

scenarios("req_context_integration.feature")


class _ReqContextParityResource:
    """Falcon resource that reports both req.context and contextvar values."""

    def __init__(self, *, delay_seconds: float = 0.0) -> None:
        """Initialise with an optional delay to encourage request overlap."""
        self._delay_seconds = delay_seconds

    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """Return both access method values and whether they match."""
        req_context_value = getattr(req.context, "correlation_id", None)
        contextvar_value = correlation_id_var.get()
        if self._delay_seconds > 0:
            time.sleep(self._delay_seconds)
        resp.media = {
            "req_context_value": req_context_value,
            "contextvar_value": contextvar_value,
            "parity": req_context_value == contextvar_value,
        }


class Context(typ.TypedDict, total=False):
    """Type definition for scenario context."""

    app: falcon.App
    client: falcon.testing.TestClient
    response: falcon.testing.Result
    concurrent_results: dict[str, dict[str, typ.Any]]


def _build_context(*, delay_seconds: float = 0.0) -> Context:
    """Create a Falcon app/client pair for req.context parity tests."""
    middleware = CorrelationIDMiddleware(trusted_sources=["127.0.0.1"])
    app = falcon.App(middleware=[middleware])
    app.add_route(
        "/req-context",
        _ReqContextParityResource(delay_seconds=delay_seconds),
    )
    client = falcon.testing.TestClient(app)
    return {
        "app": app,
        "client": client,
    }


@given(
    "a Falcon application with req.context parity support",
    target_fixture="context",
)
def given_app_with_req_context_parity() -> Context:
    """Provide a Falcon app configured for req.context parity scenarios."""
    return _build_context()


@given(
    "a Falcon application with concurrent req.context parity support",
    target_fixture="context",
)
def given_app_with_concurrent_req_context_parity() -> Context:
    """Provide a Falcon app configured for concurrent parity scenarios."""
    return _build_context(delay_seconds=0.05)


@when(parsers.parse('I request "{path}" without a correlation ID header'))
def when_request_without_header(context: Context, path: str) -> None:
    """Send a request without an incoming correlation ID header."""
    context["response"] = context["client"].simulate_get(path)


@when(parsers.parse('I request "{path}" with correlation ID "{correlation_id}"'))
def when_request_with_correlation_id(
    context: Context,
    path: str,
    correlation_id: str,
) -> None:
    """Send a request with an incoming correlation ID header."""
    context["response"] = context["client"].simulate_get(
        path,
        headers={"X-Correlation-ID": correlation_id},
    )


@when(
    parsers.parse(
        'I send concurrent req-context requests with IDs "{first_id}" and "{second_id}"'
    )
)
def when_send_concurrent_req_context_requests(
    context: Context,
    first_id: str,
    second_id: str,
) -> None:
    """Send two req-context requests concurrently with distinct IDs."""

    def _request(
        correlation_id: str,
    ) -> tuple[str, dict[str, typ.Any]]:
        result = context["client"].simulate_get(
            "/req-context",
            headers={"X-Correlation-ID": correlation_id},
        )
        return correlation_id, typ.cast("dict[str, typ.Any]", result.json)

    with ThreadPoolExecutor(max_workers=2) as executor:
        pairs = list(executor.map(_request, [first_id, second_id]))

    context["concurrent_results"] = dict(pairs)


@then("req.context.correlation_id and contextvar should match")
def then_req_context_and_contextvar_match(context: Context) -> None:
    """Verify that req.context and contextvar returned the same value."""
    payload = typ.cast("dict[str, typ.Any]", context["response"].json)
    assert payload["parity"] is True
    assert payload["req_context_value"] == payload["contextvar_value"]


@then("both values should be non-empty")
def then_both_values_non_empty(context: Context) -> None:
    """Verify that both access methods returned a non-empty value."""
    payload = typ.cast("dict[str, typ.Any]", context["response"].json)
    assert payload["req_context_value"]
    assert payload["contextvar_value"]


@then(parsers.parse('req.context.correlation_id should be "{expected}"'))
def then_req_context_value_is(context: Context, expected: str) -> None:
    """Verify the req.context correlation ID matches the expected value."""
    payload = typ.cast("dict[str, typ.Any]", context["response"].json)
    assert payload["req_context_value"] == expected


@then(parsers.parse('the contextvar value should be "{expected}"'))
def then_contextvar_value_is(context: Context, expected: str) -> None:
    """Verify the contextvar value matches the expected value."""
    payload = typ.cast("dict[str, typ.Any]", context["response"].json)
    assert payload["contextvar_value"] == expected


@then("each req-context response should confirm parity")
def then_each_response_confirms_parity(context: Context) -> None:
    """Verify concurrent req-context requests each observe parity."""
    results = context["concurrent_results"]

    for expected_id, payload in results.items():
        assert payload["parity"] is True, f"Expected parity for {expected_id!r}"
        assert payload["req_context_value"] == expected_id
        assert payload["contextvar_value"] == expected_id
