"""Validation step definitions for middleware.feature.

These steps provide utilities for building Falcon applications and test
clients used by trusted-source and custom-validator feature scenarios.
"""

from __future__ import annotations

import typing as typ

import falcon
import falcon.testing
from pytest_bdd import given, parsers

from falcon_correlate import CorrelationIDMiddleware

if typ.TYPE_CHECKING:
    from tests.bdd.test_middleware_steps import Context


@given(
    parsers.parse(
        "a Falcon application with CorrelationIDMiddleware trusting"
        ' "{sources}" and a rejecting validator'
    ),
    target_fixture="context",
)
def given_app_with_trusted_sources_and_rejecting_validator(
    sources: str,
) -> Context:
    """Create a Falcon app with trusted sources and a validator that rejects all IDs.

    Returns
    -------
    Context
        The value produced for the test scenario.

    """
    source_list = [s.strip() for s in sources.split(",")]
    middleware = CorrelationIDMiddleware(
        trusted_sources=source_list,
        validator=lambda value: False,
    )
    app = falcon.App(middleware=[middleware])
    client = falcon.testing.TestClient(app)
    return {"middleware": middleware, "app": app, "client": client}


@given(
    parsers.parse(
        "a Falcon application with CorrelationIDMiddleware trusting"
        ' "{sources}" and an accepting validator'
    ),
    target_fixture="context",
)
def given_app_with_trusted_sources_and_accepting_validator(
    sources: str,
) -> Context:
    """Create a Falcon app with trusted sources and a validator that accepts all IDs.

    Returns
    -------
    Context
        The value produced for the test scenario.

    """
    source_list = [s.strip() for s in sources.split(",")]
    middleware = CorrelationIDMiddleware(
        trusted_sources=source_list,
        validator=lambda value: True,
    )
    app = falcon.App(middleware=[middleware])
    client = falcon.testing.TestClient(app)
    return {"middleware": middleware, "app": app, "client": client}


@given(
    parsers.parse('a custom validator that rejects IDs starting with "{prefix}"'),
    target_fixture="context",
)
def given_custom_prefix_rejecting_validator(prefix: str) -> Context:
    """Create a custom validator that rejects IDs starting with the given prefix.

    Returns
    -------
    Context
        The value produced for the test scenario.

    """

    def prefix_validator(value: str) -> bool:
        """Reject correlation IDs that begin with the configured prefix.

        Returns
        -------
        bool
            The value produced for the test scenario.

        """
        return not value.startswith(prefix)

    return {"custom_validator": prefix_validator}


@given(parsers.parse('a Falcon application with that validator trusting "{sources}"'))
# pylint: disable-next=useless-return  # Explicit return is intentional.
def given_app_with_custom_validator_and_trusted_sources(
    context: Context,
    sources: str,
) -> None:
    """Create a Falcon app with the custom validator and trusted sources.

    Parameters
    ----------
    context : Context
        Scenario context containing the custom validator and receiving the
        middleware, application and test client.
    sources : str
        Comma-separated trusted source addresses.

    """
    source_list = [s.strip() for s in sources.split(",")]
    middleware = CorrelationIDMiddleware(
        trusted_sources=source_list,
        validator=context["custom_validator"],
    )
    app = falcon.App(middleware=[middleware])
    client = falcon.testing.TestClient(app)
    context["middleware"] = middleware
    context["app"] = app
    context["client"] = client
    return  # noqa: PLR1711
