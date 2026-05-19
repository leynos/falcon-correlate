"""Property tests for default UUID validation."""

from __future__ import annotations

import re
import uuid

from hypothesis import given, settings
from hypothesis import strategies as st

from falcon_correlate import default_uuid_validator

_UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{32}$|"
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


@st.composite
def valid_uuids(draw: st.DrawFn) -> uuid.UUID:
    """Generate UUIDs with validator-supported versions 1 through 8."""
    value = draw(st.uuids())
    version = draw(st.integers(min_value=1, max_value=8))
    hex_value = f"{value.int:032x}"
    versioned_hex = f"{hex_value[:12]}{version:x}{hex_value[13:16]}8{hex_value[17:]}"
    return uuid.UUID(hex=versioned_hex)


def is_valid_uuid_candidate(value: str) -> bool:
    """Return whether *value* has valid UUID syntax and version."""
    if not _UUID_PATTERN.fullmatch(value):
        return False

    try:
        parsed = uuid.UUID(value)
    except ValueError:
        return False
    return parsed.version in range(1, 9)


@given(value=valid_uuids())
@settings(max_examples=50)
def test_accepts_valid_hyphenated_and_hex_uuids(value: uuid.UUID) -> None:
    """Canonical valid UUID strings are accepted in both supported forms."""
    assert default_uuid_validator(str(value)) is True
    assert default_uuid_validator(value.hex) is True


@given(value=st.text().filter(lambda text: not is_valid_uuid_candidate(text)))
@settings(max_examples=50)
def test_rejects_invalid_uuid_strings(value: str) -> None:
    """Strings outside canonical UUID syntax or versions are rejected."""
    assert default_uuid_validator(value) is False


@given(
    value=st.sampled_from((
        "",
        "550e-8400-e29b-41d4-a716-446655440000",
        "550e8400e29b-41d4-a716-446655440000",
        "550e8400-e29b41d4-a716-446655440000",
        "00000000-0000-0000-0000-000000000000",
        "00000000000000000000000000000000",
    ))
)
@settings(max_examples=50)
def test_rejects_uuid_edge_cases(value: str) -> None:
    """Known malformed and version-zero edge cases are rejected."""
    assert default_uuid_validator(value) is False
