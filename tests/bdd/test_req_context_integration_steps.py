"""BDD step definitions for req_context_integration.feature.

This module provides the ``pytest-bdd`` step implementations that drive
the ``req_context_integration.feature`` scenarios.  Each scenario
verifies that ``req.context.correlation_id`` and
``correlation_id_var.get()`` return the same value after
``CorrelationIDMiddleware.process_request`` executes — both for single
requests and under concurrent request handling.

The step definitions use ``falcon.testing.TestClient`` to simulate HTTP
requests against a minimal Falcon app wired with
``CorrelationIDMiddleware``.

Usage
-----
Run the BDD scenarios with pytest::

    pytest tests/bdd/test_req_context_integration_steps.py -v

Or run all BDD tests::

    make test

Examples
--------
The feature scenarios are registered via the ``scenarios()`` call at
module level::

    from pytest_bdd import scenarios

    scenarios("req_context_integration.feature")

Key symbols used in this module:

- ``CorrelationIDMiddleware`` — the middleware under test.
- ``correlation_id_var`` — the ``ContextVar`` that stores the
  correlation ID.
- ``scenarios()`` — ``pytest-bdd`` helper that collects all scenarios
  from the linked feature file.

"""

from __future__ import annotations

import time
import typing as typ
from concurrent.futures import ThreadPoolExecutor

import falcon
import falcon.testing
from pytest_bdd import given, parsers, scenarios, then, when

from falcon_correlate import CorrelationIDMiddleware, correlation_id_var

scenarios("req_context_integration.feature")


class _ParityPayload(typ.TypedDict):
    """Typed response payload from ``_ReqContextParityResource``."""

    req_context_value: str | None
    contextvar_value: str | None
    parity: bool


class _ReqContextParityResource:
    """Falcon resource that reports both req.context and contextvar values."""

    def __init__(self, *, delay_seconds: float = 0.0) -> None:
        """Initialise with an optional delay to encourage request overlap."""
        self._delay_seconds = delay_seconds

    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """Return both access method values and whether they match."""
        req_context_value = getattr(req.context, "correlation_id", None)
        pre_delay_contextvar = correlation_id_var.get()
        if self._delay_seconds > 0:
            time.sleep(self._delay_seconds)
        # Re-read contextvar after delay to verify isolation holds
        # when concurrent requests overlap.
        post_delay_contextvar = correlation_id_var.get()
        resp.media = {
            "req_context_value": req_context_value,
            "contextvar_value": post_delay_contextvar,
            "parity": (
                req_context_value == pre_delay_contextvar
                and req_context_value == post_delay_contextvar
            ),
        }


class Context(typ.TypedDict, total=False):
    """Type definition for scenario context."""

    app: falcon.App
    client: falcon.testing.TestClient
    response: falcon.testing.Result
    concurrent_results: dict[str, _ParityPayload]


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
    assert context["response"].status == falcon.HTTP_200, (
        f"Expected HTTP 200, got {context['response'].status}"
    )


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
    assert context["response"].status == falcon.HTTP_200, (
        f"Expected HTTP 200, got {context['response'].status}"
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
    """Send two req-context requests concurrently with distinct IDs.

    Each worker creates its own ``TestClient`` to avoid sharing a
    single client instance across threads.  ``TestClient`` is not
    documented as thread-safe, so per-thread clients eliminate the
    risk of intermittent failures from concurrent access.
    """

    def _request(
        correlation_id: str,
    ) -> tuple[str, _ParityPayload]:
        client = falcon.testing.TestClient(context["app"])
        result = client.simulate_get(
            "/req-context",
            headers={"X-Correlation-ID": correlation_id},
        )
        assert result.status == falcon.HTTP_200, (
            f"Expected HTTP 200 for correlation ID {correlation_id!r}, "
            f"got {result.status}"
        )
        return correlation_id, typ.cast("_ParityPayload", result.json)

    with ThreadPoolExecutor(max_workers=2) as executor:
        pairs = list(executor.map(_request, [first_id, second_id]))

    context["concurrent_results"] = dict(pairs)


@then("req.context.correlation_id and contextvar should match")
def then_req_context_and_contextvar_match(context: Context) -> None:
    """Verify that req.context and contextvar returned the same value."""
    payload = typ.cast("_ParityPayload", context["response"].json)
    assert payload["parity"] is True, f"Expected parity True, got {payload['parity']!r}"
    assert payload["req_context_value"] == payload["contextvar_value"], (
        f"Expected req_context_value == contextvar_value, "
        f"got {payload['req_context_value']!r} != {payload['contextvar_value']!r}"
    )


@then("both values should be non-empty")
def then_both_values_non_empty(context: Context) -> None:
    """Verify that both access methods returned a non-empty value."""
    payload = typ.cast("_ParityPayload", context["response"].json)
    assert payload["req_context_value"], (
        f"Expected non-empty req_context_value, got {payload['req_context_value']!r}"
    )
    assert payload["contextvar_value"], (
        f"Expected non-empty contextvar_value, got {payload['contextvar_value']!r}"
    )


@then(parsers.parse('req.context.correlation_id should be "{expected}"'))
def then_req_context_value_is(context: Context, expected: str) -> None:
    """Verify the req.context correlation ID matches the expected value."""
    payload = typ.cast("_ParityPayload", context["response"].json)
    assert payload["req_context_value"] == expected, (
        f"Expected req_context_value == {expected!r}, "
        f"got {payload['req_context_value']!r}"
    )


@then(parsers.parse('the contextvar value should be "{expected}"'))
def then_contextvar_value_is(context: Context, expected: str) -> None:
    """Verify the contextvar value matches the expected value."""
    payload = typ.cast("_ParityPayload", context["response"].json)
    assert payload["contextvar_value"] == expected, (
        f"Expected contextvar_value == {expected!r}, "
        f"got {payload['contextvar_value']!r}"
    )


@then("each req-context response should confirm parity")
def then_each_response_confirms_parity(context: Context) -> None:
    """Verify concurrent req-context requests each observe parity."""
    results = context["concurrent_results"]

    for expected_id, payload in results.items():
        assert payload["parity"] is True, f"Expected parity for {expected_id!r}"
        assert payload["req_context_value"] == expected_id, (
            f"Expected req_context_value == {expected_id!r}, "
            f"got {payload['req_context_value']!r}"
        )
        assert payload["contextvar_value"] == expected_id, (
            f"Expected contextvar_value == {expected_id!r}, "
            f"got {payload['contextvar_value']!r}"
        )
