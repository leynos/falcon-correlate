"""Step definitions for context_variables.feature."""

from __future__ import annotations

import contextvars
import typing as typ

from pytest_bdd import given, parsers, scenarios, then, when

from falcon_correlate import correlation_id_var, user_id_var

scenarios("context_variables.feature")


class Context(typ.TypedDict, total=False):
    """Type definition for test context."""

    var: contextvars.ContextVar[str | None]
    value: str | None


@given("the correlation ID context variable", target_fixture="context")
def given_correlation_id_var() -> Context:
    """Provide the correlation ID context variable."""
    return {"var": correlation_id_var}


@given("the user ID context variable", target_fixture="context")
def given_user_id_var() -> Context:
    """Provide the user ID context variable."""
    return {"var": user_id_var}


@when("I retrieve its default value")
def when_retrieve_default_value(context: Context) -> None:
    """Retrieve the default value of the context variable."""
    context["value"] = context["var"].get()


@when(
    parsers.parse('I set the value to "{value}"'),
    target_fixture="context",
)
def when_set_value(context: Context, value: str) -> Context:
    """Set the context variable to a value and retrieve it.

    Runs inside a copied context to prevent test pollution.
    """
    var = context["var"]

    def _inner() -> str | None:
        token = var.set(value)
        result = var.get()
        var.reset(token)
        return result

    ctx = contextvars.copy_context()
    context["value"] = ctx.run(_inner)
    return context


@then("the value should be None")
def then_value_is_none(context: Context) -> None:
    """Verify the retrieved value is None."""
    assert context["value"] is None


@then(parsers.parse('the retrieved value should be "{expected}"'))
def then_retrieved_value_matches(context: Context, expected: str) -> None:
    """Verify the retrieved value matches the expected string."""
    assert context["value"] == expected
