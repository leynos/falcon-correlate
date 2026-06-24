"""Step definitions for quickstart.feature."""

from __future__ import annotations

import importlib
import io
import logging
import typing as typ

import falcon
import falcon.testing
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from falcon_correlate import (
    CorrelationIDConfig,
    CorrelationIDMiddleware,
    correlation_id_var,
    default_uuid_validator,
    user_id_var,
)
from tests.conftest import CorrelationEchoResource

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import contextvars
    import types

scenarios("quickstart.feature")


class Context(typ.TypedDict, total=False):
    """Type definition for quickstart scenario state."""

    app: falcon.App
    client: falcon.testing.TestClient
    response: falcon.testing.Result
    logger: logging.Logger
    stream: io.StringIO
    handlers: list[logging.Handler]
    correlation_id_token: contextvars.Token[str | None]


@pytest.fixture(autouse=True)
def _reset_context_variables() -> cabc.Generator[None, None, None]:
    """Reset context variables before and after each scenario."""
    correlation_id_var.set(None)
    user_id_var.set(None)
    yield
    correlation_id_var.set(None)
    user_id_var.set(None)


@pytest.fixture(autouse=True)
def _cleanup_logger(context: Context) -> cabc.Generator[None, None, None]:
    """Remove handlers installed by the logging example after each scenario."""
    yield
    logger = context.get("logger")
    if logger is None:
        return
    for handler in context.get("handlers", []):
        logger.removeHandler(handler)
        handler.close()


@pytest.fixture
def context() -> Context:
    """Provide mutable state for a quickstart scenario."""
    return {}


def _load_quickstart_module(module_name: str) -> types.ModuleType:
    """Import a quickstart example module by short name."""
    return importlib.import_module(f"examples.quickstart.{module_name}")


def _configure_client(context: Context, app: falcon.App) -> Context:
    """Store an app and matching test client in the scenario context."""
    context["app"] = app
    context["client"] = falcon.testing.TestClient(app)
    return context


@given(
    "a Falcon app built from the quickstart minimal example",
    target_fixture="context",
)
def given_minimal_quickstart_app(context: Context) -> Context:
    """Load the minimal quickstart app."""
    module = _load_quickstart_module("minimal_app")
    return _configure_client(context, typ.cast("falcon.App", vars(module)["app"]))


@given(
    "a Falcon app built from the quickstart configured example",
    target_fixture="context",
)
def given_configured_quickstart_app(context: Context) -> Context:
    """Load the configured quickstart app."""
    module = _load_quickstart_module("configured_app")
    return _configure_client(context, typ.cast("falcon.App", vars(module)["app"]))


@given(
    "a Falcon app from the configured example with no trusted sources",
    target_fixture="context",
)
def given_untrusted_configured_quickstart_app(context: Context) -> Context:
    """Build a configured-style app that trusts no incoming sources."""
    module = _load_quickstart_module("configured_app")
    config = typ.cast("CorrelationIDConfig", vars(module)["config"])
    app = falcon.App(
        middleware=[
            CorrelationIDMiddleware(
                header_name=config.header_name,
                trusted_sources=[],
                echo_header_in_response=config.echo_header_in_response,
            ),
        ],
    )
    app.add_route("/hello", CorrelationEchoResource())
    return _configure_client(context, app)


@given("the quickstart logging configuration", target_fixture="context")
def given_quickstart_logging_configuration(context: Context) -> Context:
    """Configure logging from the quickstart example."""
    module = _load_quickstart_module("logging_setup")
    configure_logging = typ.cast(
        "cabc.Callable[[], logging.Logger]",
        vars(module)["configure_logging"],
    )
    stream = io.StringIO()
    logger = configure_logging()
    handlers = list(logger.handlers)
    for handler in handlers:
        if isinstance(handler, logging.StreamHandler):
            handler.stream = stream
    context["logger"] = logger
    context["stream"] = stream
    context["handlers"] = handlers
    return context


@given(parsers.parse('the correlation ID is set to "{value}"'))
def given_correlation_id_set(context: Context, value: str) -> None:
    """Set the correlation ID context variable."""
    context["correlation_id_token"] = correlation_id_var.set(value)


@when(parsers.parse('I request "{path}" without a correlation ID header'))
def when_request_without_correlation_id(context: Context, path: str) -> None:
    """Make a request without an incoming correlation ID."""
    context["response"] = context["client"].simulate_get(path)


@when(
    parsers.parse(
        'I request "{path}" with header "{header_name}" value "{header_value}"'
    )
)
def when_request_with_correlation_id(
    context: Context,
    path: str,
    header_name: str,
    header_value: str,
) -> None:
    """Make a request with an incoming correlation ID header."""
    context["response"] = context["client"].simulate_get(
        path,
        headers={header_name: header_value},
    )


@when(parsers.parse('the example emits a log message "{message}"'))
def when_example_emits_log_message(context: Context, message: str) -> None:
    """Emit a log message through the configured quickstart logger."""
    context["logger"].info(message)


@then(parsers.parse("the response status should be {status_code:d}"))
def then_response_status_should_be(context: Context, status_code: int) -> None:
    """Verify the response status code."""
    assert context["response"].status_code == status_code


@then("the response should include a valid correlation ID header")
def then_response_should_include_valid_correlation_id(context: Context) -> None:
    """Verify the default response correlation ID header is valid."""
    correlation_id = context["response"].headers["X-Correlation-ID"]
    assert default_uuid_validator(correlation_id)


@then(parsers.parse('the response correlation ID header should be "{expected}"'))
def then_response_correlation_id_should_be(context: Context, expected: str) -> None:
    """Verify the response correlation ID header equals the expected value."""
    assert context["response"].headers["X-Correlation-ID"] == expected


@then(parsers.parse('the response correlation ID header should not be "{unexpected}"'))
def then_response_correlation_id_should_not_be(
    context: Context,
    unexpected: str,
) -> None:
    """Verify the response correlation ID header is not an unexpected value."""
    assert context["response"].headers["X-Correlation-ID"] != unexpected


@then(parsers.parse('the log output should contain "{expected}"'))
def then_log_output_should_contain(context: Context, expected: str) -> None:
    """Verify the logging example output contains expected text."""
    assert expected in context["stream"].getvalue()
