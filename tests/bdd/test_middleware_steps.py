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
from tests.conftest import SimpleResource, TrackingMiddleware

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
    """Create a new middleware instance."""
    return {"middleware": CorrelationIDMiddleware()}


@when("I create a Falcon application with the middleware")
def when_create_app_with_middleware(context: Context) -> None:
    """Create a Falcon app with the middleware."""
    context["app"] = falcon.App(middleware=[context["middleware"]])


@then("the application should be created successfully")
def then_app_created(context: Context) -> None:
    """Verify the app was created."""
    assert context["app"] is not None
    assert isinstance(context["app"], falcon.App)


@given("a Falcon application with CorrelationIDMiddleware", target_fixture="context")
def given_app_with_middleware() -> Context:
    """Create a Falcon app with tracking middleware."""
    middleware = TrackingMiddleware()
    app = falcon.App(middleware=[middleware])
    client = falcon.testing.TestClient(app)
    return {"middleware": middleware, "app": app, "client": client}


@given(parsers.parse('a simple resource at "{path}"'))
def given_simple_resource(context: Context, path: str) -> None:
    """Add a simple resource to the app."""
    context["app"].add_route(path, SimpleResource())


@when(parsers.parse('I make a GET request to "{path}"'))
def when_make_get_request(context: Context, path: str) -> None:
    """Make a GET request to the specified path."""
    context["response"] = context["client"].simulate_get(path)


@then("the request should complete successfully")
def then_request_complete(context: Context) -> None:
    """Verify the request completed successfully."""
    assert context["response"].status_code == HTTPStatus.OK


@then("the response should be returned")
def then_response_returned(context: Context) -> None:
    """Verify a response was returned."""
    assert context["response"] is not None
    assert context["response"].status_code == HTTPStatus.OK


@then("process_response should have been called")
def then_process_response_called(context: Context) -> None:
    """Verify process_response was called."""
    middleware = context["middleware"]
    assert isinstance(middleware, TrackingMiddleware)
    assert middleware.process_response_called


# Configuration scenario steps


@given(
    parsers.parse('a CorrelationIDMiddleware with header_name "{header_name}"'),
    target_fixture="context",
)
def given_middleware_with_header_name(header_name: str) -> Context:
    """Create middleware with custom header name."""
    return {"middleware": CorrelationIDMiddleware(header_name=header_name)}


@then(parsers.parse('the middleware should use "{header_name}" as the header name'))
def then_middleware_uses_header_name(context: Context, header_name: str) -> None:
    """Verify middleware uses specified header name."""
    assert context["middleware"].header_name == header_name


@given(
    parsers.parse('a CorrelationIDMiddleware with trusted_sources "{sources}"'),
    target_fixture="context",
)
def given_middleware_with_trusted_sources(sources: str) -> Context:
    """Create middleware with trusted sources (comma-separated)."""
    source_list = [s.strip() for s in sources.split(",")]
    return {"middleware": CorrelationIDMiddleware(trusted_sources=source_list)}


@then(parsers.parse("the middleware should have {count:d} trusted sources"))
def then_middleware_has_trusted_sources_count(context: Context, count: int) -> None:
    """Verify middleware has expected number of trusted sources."""
    assert len(context["middleware"].trusted_sources) == count


@given(
    parsers.parse('a custom ID generator that returns "{return_value}"'),
    target_fixture="context",
)
def given_custom_generator(return_value: str) -> Context:
    """Create a custom generator function."""

    def custom_gen() -> str:
        return return_value

    return {"custom_generator": custom_gen}


@given("a CorrelationIDMiddleware with that generator")
def given_middleware_with_custom_generator(context: Context) -> None:
    """Create middleware with the custom generator from context."""
    context["middleware"] = CorrelationIDMiddleware(
        generator=context["custom_generator"],
    )


@then("the middleware should use the custom generator")
def then_middleware_uses_custom_generator(context: Context) -> None:
    """Verify middleware uses the custom generator."""
    assert context["middleware"].generator is context["custom_generator"]


@given("a custom validator that accepts any string", target_fixture="context")
def given_custom_validator() -> Context:
    """Create a custom validator function."""

    def custom_val(value: str) -> bool:
        return True

    return {"custom_validator": custom_val}


@given("a CorrelationIDMiddleware with that validator")
def given_middleware_with_custom_validator(context: Context) -> None:
    """Create middleware with the custom validator from context."""
    context["middleware"] = CorrelationIDMiddleware(
        validator=context["custom_validator"],
    )


@then("the middleware should use the custom validator")
def then_middleware_uses_custom_validator(context: Context) -> None:
    """Verify middleware uses the custom validator."""
    assert context["middleware"].validator is context["custom_validator"]


@given(
    "a CorrelationIDMiddleware with echo_header_in_response disabled",
    target_fixture="context",
)
def given_middleware_with_echo_disabled() -> Context:
    """Create middleware with echo_header_in_response disabled."""
    return {"middleware": CorrelationIDMiddleware(echo_header_in_response=False)}


@then("the middleware should have echo_header_in_response set to False")
def then_middleware_echo_disabled(context: Context) -> None:
    """Verify echo_header_in_response is False."""
    assert context["middleware"].echo_header_in_response is False
