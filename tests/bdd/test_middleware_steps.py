"""Step definitions for middleware.feature."""

from __future__ import annotations

import typing as typ
from http import HTTPStatus

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
