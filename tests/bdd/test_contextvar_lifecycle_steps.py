"""Step definitions for contextvar_lifecycle.feature."""

from __future__ import annotations

import time
import typing as typ
from concurrent.futures import ThreadPoolExecutor

import falcon
import falcon.testing
from pytest_bdd import given, parsers, scenarios, then, when

from falcon_correlate import CorrelationIDMiddleware, correlation_id_var

scenarios("contextvar_lifecycle.feature")


class _LifecycleResource:
    """Falcon resource that echoes request and context variable correlation IDs."""

    def __init__(self, *, delay_seconds: float = 0.0) -> None:
        """Initialise with an optional delay to encourage request overlap."""
        self._delay_seconds = delay_seconds

    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """Return correlation IDs observed via request context and contextvars."""
        correlation_id = getattr(req.context, "correlation_id", None)
        context_var_id = correlation_id_var.get()
        if self._delay_seconds > 0:
            time.sleep(self._delay_seconds)
        resp.media = {
            "correlation_id": correlation_id,
            "context_var_id": context_var_id,
        }


class Context(typ.TypedDict, total=False):
    """Type definition for scenario context."""

    app: falcon.App
    client: falcon.testing.TestClient
    response: falcon.testing.Result
    concurrent_results: dict[str, dict[str, str | None]]


def _build_context(*, delay_seconds: float = 0.0) -> Context:
    """Create a Falcon app/client pair configured for lifecycle tests."""
    middleware = CorrelationIDMiddleware(trusted_sources=["127.0.0.1"])
    app = falcon.App(middleware=[middleware])
    app.add_route(
        "/lifecycle",
        _LifecycleResource(delay_seconds=delay_seconds),
    )
    client = falcon.testing.TestClient(app)
    return {
        "app": app,
        "client": client,
    }


@given(
    "a Falcon application with lifecycle middleware support",
    target_fixture="context",
)
def given_app_with_lifecycle_middleware() -> Context:
    """Provide a Falcon app configured for lifecycle scenarios."""
    return _build_context()


@given(
    "a Falcon application with concurrent lifecycle middleware support",
    target_fixture="context",
)
def given_app_with_concurrent_lifecycle_middleware() -> Context:
    """Provide a Falcon app configured for concurrent lifecycle scenarios."""
    return _build_context(delay_seconds=0.05)


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
        'I send concurrent lifecycle requests with IDs "{first_id}" and "{second_id}"'
    )
)
def when_send_concurrent_requests(
    context: Context,
    first_id: str,
    second_id: str,
) -> None:
    """Send two lifecycle requests concurrently with distinct correlation IDs."""

    def _request(correlation_id: str) -> tuple[str, dict[str, str | None]]:
        result = context["client"].simulate_get(
            "/lifecycle",
            headers={"X-Correlation-ID": correlation_id},
        )
        return correlation_id, typ.cast("dict[str, str | None]", result.json)

    with ThreadPoolExecutor(max_workers=2) as executor:
        pairs = list(executor.map(_request, [first_id, second_id]))

    context["concurrent_results"] = dict(pairs)


@then(parsers.parse('the resource should observe context variable value "{expected}"'))
def then_resource_observes_context_value(context: Context, expected: str) -> None:
    """Verify the in-request context variable value matches the correlation ID."""
    payload = typ.cast("dict[str, str | None]", context["response"].json)
    assert payload["correlation_id"] == expected
    assert payload["context_var_id"] == expected


@then("the correlation ID context variable should be cleared")
def then_context_variable_cleared() -> None:
    """Verify request handling left no lingering correlation ID context."""
    assert correlation_id_var.get() is None


@then("each lifecycle response should contain its own correlation ID")
def then_each_response_contains_own_correlation_id(context: Context) -> None:
    """Verify concurrent lifecycle requests observe isolated context state."""
    results = context["concurrent_results"]

    for expected_id, payload in results.items():
        assert payload["correlation_id"] == expected_id
        assert payload["context_var_id"] == expected_id
