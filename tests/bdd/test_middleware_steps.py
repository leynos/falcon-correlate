"""Step definitions for middleware.feature."""

from __future__ import annotations

import typing as typ
from http import HTTPStatus

if typ.TYPE_CHECKING:
    import collections.abc as cabc

import falcon
import falcon.testing
from pytest_bdd import given, parsers, scenarios, then, when

from falcon_correlate import CorrelationIDMiddleware
from falcon_correlate.unittests.uuid7_helpers import assert_uuid7_hex
from tests.conftest import CorrelationEchoResource, SimpleResource, TrackingMiddleware

pytest_plugins = (
    "tests.bdd.middleware_validation_steps",
    "tests.bdd.middleware_config_steps",
)

scenarios("middleware.feature")


class Context(typ.TypedDict, total=False):
    """Type definition for test context."""

    middleware: CorrelationIDMiddleware | TrackingMiddleware
    app: falcon.App
    client: falcon.testing.TestClient
    response: falcon.testing.Result
    custom_generator: cabc.Callable[[], str]
    custom_validator: cabc.Callable[[str], bool]


@given("a new CorrelationIDMiddleware instance", target_fixture="context")
def given_middleware_instance() -> Context:
    """Create a new middleware instance.

    Returns
    -------
    Context
        A context mapping containing a default ``CorrelationIDMiddleware``.

    """
    return {"middleware": CorrelationIDMiddleware()}


@when("I create a Falcon application with the middleware")
def when_create_app_with_middleware(context: Context) -> None:
    """Create a Falcon app with the middleware."""
    context["app"] = falcon.App(middleware=[context["middleware"]])


@then("the application should be created successfully")
def then_app_created(context: Context) -> None:
    """Verify the app was created."""
    assert context["app"] is not None, "expected context['app'] not to be None"
    failure_message = "expected isinstance(context['app'], falcon.App) to be truthy"
    assert isinstance(context["app"], falcon.App), failure_message


@given("a Falcon application with CorrelationIDMiddleware", target_fixture="context")
def given_app_with_middleware() -> Context:
    """Create a Falcon app with tracking middleware.

    The middleware is configured to trust 127.0.0.1 (TestClient's default
    remote_addr) so that header capture tests work correctly.

    Returns
    -------
    Context
        A context mapping containing the middleware, Falcon app, and client.

    """
    middleware = TrackingMiddleware(trusted_sources=["127.0.0.1"])
    app = falcon.App(middleware=[middleware])
    client = falcon.testing.TestClient(app)
    return {"middleware": middleware, "app": app, "client": client}


@given(parsers.parse('a simple resource at "{path}"'))
def given_simple_resource(context: Context, path: str) -> None:
    """Add a simple resource to the app."""
    context["app"].add_route(path, SimpleResource())


@given(parsers.parse('a correlation echo resource at "{path}"'))
def given_correlation_resource(context: Context, path: str) -> None:
    """Add a correlation echo resource to the app."""
    context["app"].add_route(path, CorrelationEchoResource())


@when(parsers.parse('I make a GET request to "{path}"'))
def when_make_get_request(context: Context, path: str) -> None:
    """Make a GET request to the specified path."""
    context["response"] = context["client"].simulate_get(path)


@when(
    parsers.parse(
        'I request "{path}" with header "{header_name}" value "{header_value}"'
    )
)
def when_make_get_request_with_header(
    context: Context,
    path: str,
    header_name: str,
    header_value: str,
) -> None:
    """Make a GET request with a header."""
    context["response"] = context["client"].simulate_get(
        path,
        headers={header_name: header_value},
    )


@then("the request should complete successfully")
def then_request_complete(context: Context) -> None:
    """Verify the request completed successfully."""
    failure_message = "expected context['response'].status_code to equal HTTPStatus.OK"
    assert context["response"].status_code == HTTPStatus.OK, failure_message


@then("the response should be returned")
def then_response_returned(context: Context) -> None:
    """Verify a response was returned."""
    failure_message = "expected context['response'] not to be None"
    assert context["response"] is not None, failure_message
    failure_message = "expected context['response'].status_code to equal HTTPStatus.OK"
    assert context["response"].status_code == HTTPStatus.OK, failure_message


@then("process_response should have been called")
def then_process_response_called(context: Context) -> None:
    """Verify process_response was called."""
    middleware = context["middleware"]
    failure_message = "expected isinstance(middleware, TrackingMiddleware) to be truthy"
    assert isinstance(middleware, TrackingMiddleware), failure_message
    failure_message = "expected middleware.process_response_called to be truthy"
    assert middleware.process_response_called, failure_message


@then(parsers.parse('the response correlation id should be "{expected_id}"'))
def then_response_has_correlation_id(context: Context, expected_id: str) -> None:
    """Verify the response includes the expected correlation ID."""
    data = context["response"].json
    failure_message = "expected data['has_correlation_id'] to be True"
    assert data["has_correlation_id"] is True, failure_message
    failure_message = "expected data['correlation_id'] to equal expected_id"
    assert data["correlation_id"] == expected_id, failure_message


@then(
    parsers.parse('the HTTP response header "{header_name}" should be "{expected_id}"')
)
def then_http_response_header_matches(
    context: Context,
    header_name: str,
    expected_id: str,
) -> None:
    """Verify the HTTP response includes the expected header value."""
    actual_id = context["response"].headers[header_name]
    assert actual_id == expected_id, (
        f"expected response header {header_name!r} to be {expected_id!r} "
        f"but got {actual_id!r}"
    )


@then("the response should not include a correlation ID")
def then_response_has_no_correlation_id(context: Context) -> None:
    """Verify the response does not include a correlation ID."""
    data = context["response"].json
    failure_message = "expected data['has_correlation_id'] to be False"
    assert data["has_correlation_id"] is False, failure_message
    assert data["correlation_id"] is None, "expected data['correlation_id'] to be None"


# Configuration scenario steps


@given(
    parsers.parse('a CorrelationIDMiddleware with header_name "{header_name}"'),
    target_fixture="context",
)
def given_middleware_with_header_name(header_name: str) -> Context:
    """Create middleware with custom header name.

    Parameters
    ----------
    header_name : str
        Name of the HTTP header the middleware should use for the
        correlation ID.

    Returns
    -------
    Context
        A context mapping containing middleware with the requested header name.

    """
    return {"middleware": CorrelationIDMiddleware(header_name=header_name)}


@then(parsers.parse('the middleware should use "{header_name}" as the header name'))
def then_middleware_uses_header_name(context: Context, header_name: str) -> None:
    """Verify middleware uses specified header name."""
    failure_message = "expected context['middleware'].header_name to equal header_name"
    assert context["middleware"].header_name == header_name, failure_message


@given(
    parsers.parse('a CorrelationIDMiddleware with trusted_sources "{sources}"'),
    target_fixture="context",
)
def given_middleware_with_trusted_sources(sources: str) -> Context:
    """Create middleware with trusted sources (comma-separated).

    Parameters
    ----------
    sources : str
        Comma-separated trusted source addresses.

    Returns
    -------
    Context
        A context mapping containing middleware with the requested sources.

    """
    source_list = [s.strip() for s in sources.split(",")]
    return {"middleware": CorrelationIDMiddleware(trusted_sources=source_list)}


@then(parsers.parse("the middleware should have {count:d} trusted sources"))
def then_middleware_has_trusted_sources_count(context: Context, count: int) -> None:
    """Verify middleware has expected number of trusted sources."""
    failure_message = "expected condition: len(context['middleware'].trusted_sources..."
    assert len(context["middleware"].trusted_sources) == count, failure_message


# Trusted source scenario steps


@given(
    parsers.parse(
        'a Falcon application with CorrelationIDMiddleware trusting "{sources}"'
    ),
    target_fixture="context",
)
def given_app_with_trusted_sources(sources: str) -> Context:
    """Create a Falcon app with middleware configured with trusted sources.

    Parameters
    ----------
    sources : str
        Comma-separated trusted source addresses.

    Returns
    -------
    Context
        A context mapping containing the middleware, Falcon app, and client.

    """
    source_list = [s.strip() for s in sources.split(",")]
    middleware = CorrelationIDMiddleware(trusted_sources=source_list)
    app = falcon.App(middleware=[middleware])
    client = falcon.testing.TestClient(app)
    return {"middleware": middleware, "app": app, "client": client}


@given("a Falcon application with that custom generator")
def given_app_with_custom_generator(context: Context) -> None:
    """Create a Falcon app with the custom generator from context."""
    middleware = CorrelationIDMiddleware(generator=context["custom_generator"])
    app = falcon.App(middleware=[middleware])
    client = falcon.testing.TestClient(app)
    context["middleware"] = middleware
    context["app"] = app
    context["client"] = client


# Generator invocation steps


@then("a correlation ID should be generated")
def then_correlation_id_generated(context: Context) -> None:
    """Verify a correlation ID was generated."""
    data = context["response"].json
    assert data["has_correlation_id"] is True, "Expected has_correlation_id to be True"
    assert data["correlation_id"] is not None, (
        "Expected correlation_id to be set, got None"
    )
    assert len(data["correlation_id"]) > 0, "Expected correlation_id to be non-empty"


@then(parsers.parse('the correlation ID should not be "{unexpected_id}"'))
def then_correlation_id_not_equal(context: Context, unexpected_id: str) -> None:
    """Verify the correlation ID is not the unexpected value."""
    data = context["response"].json
    assert data["correlation_id"] != unexpected_id, (
        f"Expected correlation_id to differ from '{unexpected_id}'"
    )


@then("the correlation ID should be a valid UUIDv7")
def then_correlation_id_is_uuid7(context: Context) -> None:
    """Verify the correlation ID is a valid UUIDv7 hex string."""
    data = context["response"].json
    assert data["has_correlation_id"] is True, (
        "Expected has_correlation_id to be True before UUIDv7 validation"
    )
    # assert_uuid7_hex raises AssertionError with detailed message on failure
    assert_uuid7_hex(data["correlation_id"])
