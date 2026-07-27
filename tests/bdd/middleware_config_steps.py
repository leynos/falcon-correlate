"""Configuration-option step definitions for middleware.feature.

These steps build custom generators and validators and configure response
echoing, keeping the custom-callable scenarios separate from the core
``test_middleware_steps`` module.
"""

from __future__ import annotations

import typing as typ

from pytest_bdd import given, parsers, then

from falcon_correlate import CorrelationIDMiddleware

if typ.TYPE_CHECKING:
    from tests.bdd.test_middleware_steps import Context


@given(
    parsers.parse('a custom ID generator that returns "{return_value}"'),
    target_fixture="context",
)
def given_custom_generator(return_value: str) -> Context:
    """Create a custom generator function.

    Parameters
    ----------
    return_value : str
        The fixed value the custom generator returns.

    Returns
    -------
    Context
        A context mapping containing the custom generator callable.

    """

    def custom_gen() -> str:
        """Return the configured custom correlation ID.

        Returns
        -------
        str
            The fixed correlation ID value supplied by the step.

        """
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
    assert context["middleware"].generator is context["custom_generator"], (
        "the configured generator must be retained"
    )


@given("a custom validator that accepts any string", target_fixture="context")
def given_custom_validator() -> Context:
    """Create a custom validator function.

    Returns
    -------
    Context
        A context mapping containing the custom validator callable.

    """

    def custom_val(value: str) -> bool:
        """Accept any supplied correlation ID value.

        Parameters
        ----------
        value : str
            The candidate correlation ID the validator inspects.

        Returns
        -------
        bool
            Always ``True`` so the step exercises the accepting path.

        """
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
    assert context["middleware"].validator is context["custom_validator"], (
        "the configured validator must be retained"
    )


@given(
    "a CorrelationIDMiddleware with echo_header_in_response disabled",
    target_fixture="context",
)
def given_middleware_with_echo_disabled() -> Context:
    """Create middleware with echo_header_in_response disabled.

    Returns
    -------
    Context
        A context mapping containing middleware with response echo disabled.

    """
    return {"middleware": CorrelationIDMiddleware(echo_header_in_response=False)}


@then("the middleware should have echo_header_in_response set to False")
def then_middleware_echo_disabled(context: Context) -> None:
    """Verify echo_header_in_response is False."""
    assert context["middleware"].echo_header_in_response is False, (
        "response-header echoing must be disabled"
    )
