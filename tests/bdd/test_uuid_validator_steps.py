"""Step definitions for uuid_validator.feature."""

from __future__ import annotations

import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc

from pytest_bdd import given, parsers, scenarios, then, when

from falcon_correlate import default_uuid_validator

scenarios("uuid_validator.feature")


class Context(typ.TypedDict, total=False):
    """Type definition for test context."""

    validator: cabc.Callable[[str], bool]
    validation_result: bool


@given("the default UUID validator", target_fixture="context")
def given_default_uuid_validator() -> Context:
    """Provide the default validator."""
    return {"validator": default_uuid_validator}


@when(parsers.parse('I validate "{value}"'))
def when_validate_value(context: Context, value: str) -> None:
    """Validate the given value using the default validator."""
    context["validation_result"] = context["validator"](value)


@when("I validate an empty string")
def when_validate_empty_string(context: Context) -> None:
    """Validate an empty string using the default validator."""
    context["validation_result"] = context["validator"]("")


@when(parsers.parse("I validate a string of {length:d} characters"))
def when_validate_long_string(context: Context, length: int) -> None:
    """Validate a string of the specified length."""
    long_string = "a" * length
    context["validation_result"] = context["validator"](long_string)


@then(parsers.parse("the validation result should be {expected}"))
def then_validation_result_is(context: Context, expected: str) -> None:
    """Verify the validation result matches the expected value."""
    expected_bool = expected == "True"
    assert context["validation_result"] is expected_bool, (
        f"expected validation result to be {expected_bool}, "
        f"got {context['validation_result']}"
    )
