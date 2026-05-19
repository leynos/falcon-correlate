"""Step definitions for asgi_middleware.feature."""

from __future__ import annotations

import typing as typ
from http import HTTPStatus

import falcon.asgi
import falcon.testing
from pytest_bdd import given, parsers, scenarios, then, when

from falcon_correlate import CorrelationIDMiddlewareASGI
from tests.asgi_resources import ASGICorrelationEchoResource

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


@given(
    parsers.parse(_TRUSTED_APP_STEP),
    target_fixture="context",
)
def given_asgi_app_with_trusted_sources(sources: str) -> Context:
    """Create a Falcon ASGI app with trusted-source middleware."""
    source_list = [source.strip() for source in sources.split(",")]
    app = falcon.asgi.App(
        middleware=[
            CorrelationIDMiddlewareASGI(trusted_sources=source_list),
        ],
    )
    return {"app": app, "client": falcon.testing.TestClient(app)}


@given(
    parsers.parse(_GENERATING_APP_STEP),
    target_fixture="context",
)
def given_asgi_app_with_generator(
    sources: str,
    generated_id: str,
) -> Context:
    """Create a Falcon ASGI app with a fixed ID generator."""
    source_list = [source.strip() for source in sources.split(",")]
    app = falcon.asgi.App(
        middleware=[
            CorrelationIDMiddlewareASGI(
                trusted_sources=source_list,
                generator=lambda: generated_id,
            ),
        ],
    )
    return {"app": app, "client": falcon.testing.TestClient(app)}


@given(
    parsers.parse(_REJECTING_APP_STEP),
    target_fixture="context",
)
def given_asgi_app_with_rejecting_validator(
    sources: str,
    generated_id: str,
) -> Context:
    """Create a Falcon ASGI app with fixed generation and rejected input."""
    source_list = [source.strip() for source in sources.split(",")]
    app = falcon.asgi.App(
        middleware=[
            CorrelationIDMiddlewareASGI(
                trusted_sources=source_list,
                generator=lambda: generated_id,
                validator=lambda _: False,
            ),
        ],
    )
    return {"app": app, "client": falcon.testing.TestClient(app)}


@given(
    parsers.parse(_ECHO_DISABLED_APP_STEP),
    target_fixture="context",
)
def given_asgi_app_with_echo_disabled(generated_id: str) -> Context:
    """Create a Falcon ASGI app with response-header echoing disabled."""
    app = falcon.asgi.App(
        middleware=[
            CorrelationIDMiddlewareASGI(
                generator=lambda: generated_id,
                echo_header_in_response=False,
            ),
        ],
    )
    return {"app": app, "client": falcon.testing.TestClient(app)}


@given(parsers.parse('an ASGI correlation echo resource at "{path}"'))
def given_asgi_correlation_resource(context: Context, path: str) -> None:
    """Add a correlation echo resource to the ASGI application."""
    context["app"].add_route(path, ASGICorrelationEchoResource())


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
