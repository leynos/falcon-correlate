"""Step definitions for uuidv7.feature."""

from __future__ import annotations

import typing as typ
import uuid

if typ.TYPE_CHECKING:
    import collections.abc as cabc

from pytest_bdd import given, scenarios, then, when

from falcon_correlate import default_uuid7_generator

scenarios("uuidv7.feature")

UUID_HEX_LENGTH = 32
UUID_VERSION = 7


class Context(typ.TypedDict, total=False):
    """Type definition for test context."""

    generator: cabc.Callable[[], str]
    generated_id: str
    first_id: str
    second_id: str


@given("the default UUIDv7 generator", target_fixture="context")
def given_default_uuid7_generator() -> Context:
    """Provide the default generator."""
    return {"generator": default_uuid7_generator}


@when("I generate a correlation ID")
def when_generate_correlation_id(context: Context) -> None:
    """Generate a correlation ID using the default generator."""
    context["generated_id"] = context["generator"]()


@when("I generate two correlation IDs")
def when_generate_two_correlation_ids(context: Context) -> None:
    """Generate two correlation IDs using the default generator."""
    generator = context["generator"]
    context["first_id"] = generator()
    context["second_id"] = generator()


@then("the correlation ID should be a UUIDv7 hex string")
def then_correlation_id_is_uuid7_hex(context: Context) -> None:
    """Verify the correlation ID is a UUIDv7 hex string."""
    value = context["generated_id"]
    assert len(value) == UUID_HEX_LENGTH
    assert value == value.lower()
    _ = int(value, 16)
    parsed = uuid.UUID(hex=value)
    assert parsed.version == UUID_VERSION
    assert parsed.variant == uuid.RFC_4122


@then("the correlation IDs should be different")
def then_correlation_ids_differ(context: Context) -> None:
    """Verify the generated correlation IDs differ."""
    assert context["first_id"] != context["second_id"]
