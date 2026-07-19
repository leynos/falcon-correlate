"""BDD step definitions for the quickstart guide examples.

These steps execute the runnable modules that back ``docs/quickstart.md`` so
the guide, examples, and behavioural scenarios stay aligned as the tutorial
evolves.
"""

from __future__ import annotations

import dataclasses
import io
import logging
import typing as typ

import falcon
import falcon.testing
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from falcon_correlate import (
    CorrelationIDConfig,
    correlation_id_var,
    default_uuid_validator,
    user_id_var,
)
from tests._quickstart_support import _load_quickstart_module

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import contextvars

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
    """Provide mutable state for a quickstart scenario.

    Returns
    -------
    Context
        Empty mutable scenario state.

    """
    return {}


def _configure_client(context: Context, app: falcon.App) -> Context:
    """Store an app and matching test client in the scenario context.

    Returns
    -------
    Context
        The updated scenario state.

    """
    context["app"] = app
    context["client"] = falcon.testing.TestClient(app)
    return context


@given(
    "a Falcon app built from the quickstart minimal example",
    target_fixture="context",
)
def given_minimal_quickstart_app(context: Context) -> Context:
    """Load the minimal quickstart app.

    Returns
    -------
    Context
        Scenario state containing the app and test client.

    """
    module = _load_quickstart_module("minimal_app")
    return _configure_client(context, typ.cast("falcon.App", vars(module)["app"]))


@given(
    "a Falcon app built from the quickstart configured example",
    target_fixture="context",
)
def given_configured_quickstart_app(context: Context) -> Context:
    """Load the configured quickstart app.

    Returns
    -------
    Context
        Scenario state containing the app and test client.

    """
    module = _load_quickstart_module("configured_app")
    return _configure_client(context, typ.cast("falcon.App", vars(module)["app"]))


@given(
    "a Falcon app from the configured example with no trusted sources",
    target_fixture="context",
)
def given_untrusted_configured_quickstart_app(context: Context) -> Context:
    """Load the configured quickstart app with only trusted sources varied.

    Returns
    -------
    Context
        Scenario state containing the app and test client.

    """
    module = _load_quickstart_module("configured_app")
    config = typ.cast("CorrelationIDConfig", vars(module)["config"])
    build_app = typ.cast(
        "cabc.Callable[[CorrelationIDConfig], falcon.App]",
        vars(module)["build_app"],
    )
    untrusted_config = dataclasses.replace(config, trusted_sources=frozenset())
    return _configure_client(context, build_app(untrusted_config))


@given("the quickstart logging configuration", target_fixture="context")
def given_quickstart_logging_configuration(context: Context) -> Context:
    """Configure logging from the quickstart example.

    Returns
    -------
    Context
        Scenario state containing the configured logger and output stream.

    """
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
    actual_status = context["response"].status_code
    assert actual_status == status_code, (
        f"expected response status {status_code}, got {actual_status}"
    )


@then("the response should include a valid correlation ID header")
def then_response_should_include_valid_correlation_id(context: Context) -> None:
    """Verify the default response correlation ID header is valid."""
    correlation_id = context["response"].headers["X-Correlation-ID"]
    assert default_uuid_validator(correlation_id), (
        f"expected a valid X-Correlation-ID header, got {correlation_id!r}"
    )


@then(parsers.parse('the response correlation ID header should be "{expected}"'))
def then_response_correlation_id_should_be(context: Context, expected: str) -> None:
    """Verify the response correlation ID header equals the expected value."""
    actual = context["response"].headers["X-Correlation-ID"]
    assert actual == expected, (
        f"expected X-Correlation-ID header {expected!r}, got {actual!r}"
    )


@then(parsers.parse('the response correlation ID header should not be "{unexpected}"'))
def then_response_correlation_id_should_not_be(
    context: Context,
    unexpected: str,
) -> None:
    """Verify the response correlation ID header is not an unexpected value."""
    actual = context["response"].headers["X-Correlation-ID"]
    assert actual != unexpected, (
        f"expected X-Correlation-ID header not to be {unexpected!r}, got {actual!r}"
    )


@then(parsers.parse('the log output should contain "{expected}"'))
def then_log_output_should_contain(context: Context, expected: str) -> None:
    """Verify the logging example output contains expected text."""
    output = context["stream"].getvalue()
    assert expected in output, (
        f"expected log output to contain {expected!r}: {output!r}"
    )
