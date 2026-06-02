"""Step definitions for asgi_middleware.feature."""

from __future__ import annotations

import asyncio
import collections.abc as cabc  # noqa: TC003 - requested runtime import.
import typing as typ
from http import HTTPStatus

import falcon.asgi
import falcon.testing
from pytest_bdd import given, parsers, scenarios, then, when

from falcon_correlate import CorrelationIDMiddlewareASGI, correlation_id_var
from tests.asgi_resources import (
    ASGICorrelationEchoResource,
    ASGIInterleavedCorrelationResource,
)

scenarios("asgi_middleware.feature")

_TRUSTED_APP_STEP = (
    'a Falcon ASGI application with CorrelationIDMiddlewareASGI trusting "{sources}"'
)
_GENERATING_APP_STEP = (
    "a Falcon ASGI application with CorrelationIDMiddlewareASGI trusting "
    '"{sources}" and generator "{generated_id}"'
)
_REJECTING_APP_STEP = (
    "a Falcon ASGI application with CorrelationIDMiddlewareASGI trusting "
    '"{sources}", generator "{generated_id}", and a rejecting validator'
)
_ECHO_DISABLED_APP_STEP = (
    "a Falcon ASGI application with CorrelationIDMiddlewareASGI generator "
    '"{generated_id}" and response echo disabled'
)
_GET_WITH_HEADER_STEP = (
    'I make an ASGI GET request to "{path}" with header "{header_name}" '
    'value "{header_value}"'
)


class Context(typ.TypedDict, total=False):
    """Type definition for ASGI middleware BDD context."""

    app: falcon.asgi.App
    client: falcon.testing.TestClient
    response: falcon.testing.Result
    concurrent_responses: dict[str, falcon.testing.Result]


def _build_asgi_context(
    *,
    sources: list[str] | None = None,
    generated_id: str | None = None,
    validator: cabc.Callable[[str], bool] | None = None,
    echo_header_in_response: bool = True,
) -> Context:
    """Build a Falcon ASGI test context with CorrelationIDMiddlewareASGI."""
    kwargs: dict[str, object] = {}
    if sources is not None:
        kwargs["trusted_sources"] = sources
    if generated_id is not None:
        kwargs["generator"] = lambda: generated_id
    if validator is not None:
        kwargs["validator"] = validator
    if not echo_header_in_response:
        kwargs["echo_header_in_response"] = False
    app = falcon.asgi.App(
        middleware=[CorrelationIDMiddlewareASGI(**typ.cast("typ.Any", kwargs))],
    )
    return {"app": app, "client": falcon.testing.TestClient(app)}


@given(
    parsers.parse(_TRUSTED_APP_STEP),
    target_fixture="context",
)
def given_asgi_app_with_trusted_sources(sources: str) -> Context:
    """Create a Falcon ASGI app with trusted-source middleware."""
    return _build_asgi_context(
        sources=[source.strip() for source in sources.split(",")],
    )


@given(
    parsers.parse(_GENERATING_APP_STEP),
    target_fixture="context",
)
def given_asgi_app_with_generator(
    sources: str,
    generated_id: str,
) -> Context:
    """Create a Falcon ASGI app with a fixed ID generator."""
    return _build_asgi_context(
        sources=[source.strip() for source in sources.split(",")],
        generated_id=generated_id,
    )


@given(
    parsers.parse(_REJECTING_APP_STEP),
    target_fixture="context",
)
def given_asgi_app_with_rejecting_validator(
    sources: str,
    generated_id: str,
) -> Context:
    """Create a Falcon ASGI app with fixed generation and rejected input."""
    return _build_asgi_context(
        sources=[source.strip() for source in sources.split(",")],
        generated_id=generated_id,
        validator=lambda _: False,
    )


@given(
    parsers.parse(_ECHO_DISABLED_APP_STEP),
    target_fixture="context",
)
def given_asgi_app_with_echo_disabled(generated_id: str) -> Context:
    """Create a Falcon ASGI app with response-header echoing disabled."""
    return _build_asgi_context(
        generated_id=generated_id,
        echo_header_in_response=False,
    )


@given(parsers.parse('an ASGI correlation echo resource at "{path}"'))
def given_asgi_correlation_resource(context: Context, path: str) -> None:
    """Add a correlation echo resource to the ASGI application."""
    context["app"].add_route(path, ASGICorrelationEchoResource())


@given(
    parsers.parse(
        "an interleaved ASGI correlation resource expecting {request_count:d} "
        'requests at "{path}"',
    ),
)
def given_interleaved_asgi_correlation_resource(
    context: Context,
    request_count: int,
    path: str,
) -> None:
    """Add a correlation resource that waits for concurrent ASGI requests."""
    context["app"].add_route(
        path,
        ASGIInterleavedCorrelationResource(expected_requests=request_count),
    )


@when(parsers.parse(_GET_WITH_HEADER_STEP))
def when_make_asgi_get_request_with_header(
    context: Context,
    path: str,
    header_name: str,
    header_value: str,
) -> None:
    """Make an ASGI GET request with a correlation header."""
    context["response"] = context["client"].simulate_get(
        path,
        headers={header_name: header_value},
    )


@when(parsers.parse('I make an ASGI GET request to "{path}"'))
def when_make_asgi_get_request(context: Context, path: str) -> None:
    """Make an ASGI GET request without a correlation header."""
    context["response"] = context["client"].simulate_get(path)


@when(
    parsers.parse(
        'I make concurrent ASGI GET requests to "{path}" with correlation IDs '
        '"{first_id}" and "{second_id}"',
    ),
)
def when_make_concurrent_asgi_get_requests(
    context: Context,
    path: str,
    first_id: str,
    second_id: str,
) -> None:
    """Make concurrent ASGI requests with distinct correlation IDs."""

    async def _request(
        conductor: falcon.testing.ASGIConductor,
        correlation_id: str,
    ) -> tuple[str, falcon.testing.Result]:
        result = await conductor.simulate_get(
            path,
            headers={"X-Correlation-ID": correlation_id},
        )
        return correlation_id, result

    async def _run_requests() -> dict[str, falcon.testing.Result]:
        async with falcon.testing.ASGIConductor(context["app"]) as conductor:
            pairs = await asyncio.wait_for(
                asyncio.gather(
                    _request(conductor, first_id),
                    _request(conductor, second_id),
                ),
                timeout=5.0,
            )
        return dict(pairs)

    context["concurrent_responses"] = asyncio.run(_run_requests())


@then("the ASGI response should complete successfully")
def then_asgi_response_complete(context: Context) -> None:
    """Verify the ASGI response was successful."""
    assert context["response"].status_code == HTTPStatus.OK, (
        "expected ASGI response status to be 200 but got "
        f"{context['response'].status_code}"
    )


@then(parsers.parse('the ASGI resource should observe correlation id "{expected_id}"'))
def then_asgi_resource_observes_correlation_id(
    context: Context,
    expected_id: str,
) -> None:
    """Verify application code observed the expected correlation ID."""
    assert context["response"].json == {
        "context_correlation_id": expected_id,
        "contextvar_correlation_id": expected_id,
    }, (
        "expected ASGI resource to observe correlation ID "
        f"{expected_id!r} but got {context['response'].json!r}"
    )


@then(
    parsers.parse('the ASGI response header "{header_name}" should be "{expected_id}"')
)
def then_asgi_response_header_matches(
    context: Context,
    header_name: str,
    expected_id: str,
) -> None:
    """Verify the ASGI response echoes the correlation header."""
    actual_header = context["response"].headers[header_name]
    assert actual_header == expected_id, (
        f"expected ASGI response header {header_name!r} to be "
        f"{expected_id!r} but got {actual_header!r}"
    )


@then(parsers.parse('the ASGI response header "{header_name}" should be absent'))
def then_asgi_response_header_absent(
    context: Context,
    header_name: str,
) -> None:
    """Verify the ASGI response does not include the correlation header."""
    actual_header = context["response"].headers.get(header_name)
    assert actual_header is None, (
        f"expected ASGI response header {header_name!r} to be absent but got "
        f"{actual_header!r}"
    )


@then("each ASGI concurrent response should observe its own correlation id")
def then_each_asgi_concurrent_response_observes_own_id(context: Context) -> None:
    """Verify concurrent ASGI responses observed isolated context state."""
    for expected_id, result in context["concurrent_responses"].items():
        expected_json = {
            "context_correlation_id": expected_id,
            "contextvar_correlation_id": expected_id,
            "contextvar_correlation_id_after_wait": expected_id,
        }
        assert result.status_code == HTTPStatus.OK, (
            f"expected ASGI response status to be 200 but got {result.status_code}"
        )
        assert result.json == expected_json, (
            f"expected ASGI resource to observe {expected_json!r} but got "
            f"{result.json!r}"
        )


@then("each ASGI concurrent response header should match its own correlation id")
def then_each_asgi_concurrent_response_header_matches_own_id(
    context: Context,
) -> None:
    """Verify concurrent ASGI responses echoed their own request IDs."""
    for expected_id, result in context["concurrent_responses"].items():
        actual_header = result.headers["X-Correlation-ID"]
        assert actual_header == expected_id, (
            "expected ASGI response header 'X-Correlation-ID' to be "
            f"{expected_id!r} but got {actual_header!r}"
        )


@then("the ASGI ambient correlation ID context should be cleared")
def then_asgi_ambient_context_cleared() -> None:
    """Verify ASGI request handling left no ambient correlation ID."""
    assert correlation_id_var.get() is None, (
        "expected correlation_id_var.get() to be None after ASGI request but got "
        f"{correlation_id_var.get()!r}"
    )
