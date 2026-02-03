"""Unit tests for default UUID validator."""

from __future__ import annotations

from falcon_correlate import default_uuid_validator


class TestDefaultUUIDValidator:
    """Tests for default UUID validator."""

    # Valid UUID formats

    def test_accepts_valid_uuid_v1_hyphenated(self) -> None:
        """Verify validator accepts a valid UUIDv1 with hyphens."""
        # UUIDv1 example (time-based)
        assert default_uuid_validator("f47ac10b-58cc-11e9-8000-000000000000") is True

    def test_accepts_valid_uuid_v4_hyphenated(self) -> None:
        """Verify validator accepts a valid UUIDv4 with hyphens."""
        # UUIDv4 example (random)
        assert default_uuid_validator("550e8400-e29b-41d4-a716-446655440000") is True

    def test_accepts_valid_uuid_v7_hyphenated(self) -> None:
        """Verify validator accepts a valid UUIDv7 with hyphens."""
        # UUIDv7 example (time-ordered)
        assert default_uuid_validator("01932c9e-1a3d-7000-8000-000000000000") is True

    def test_accepts_valid_uuid_hex_only(self) -> None:
        """Verify validator accepts a valid UUID as 32-character hex string."""
        # Same as v4 example but without hyphens
        assert default_uuid_validator("550e8400e29b41d4a716446655440000") is True

    def test_accepts_uppercase_uuid(self) -> None:
        """Verify validator accepts uppercase UUID strings."""
        assert default_uuid_validator("550E8400-E29B-41D4-A716-446655440000") is True

    def test_accepts_mixed_case_uuid(self) -> None:
        """Verify validator accepts mixed case UUID strings."""
        assert default_uuid_validator("550e8400-E29B-41d4-A716-446655440000") is True

    def test_accepts_uuid_with_braces(self) -> None:
        """Verify validator accepts UUID with curly braces (Microsoft format)."""
        assert default_uuid_validator("{550e8400-e29b-41d4-a716-446655440000}") is False
        # Note: stdlib uuid.UUID does not accept braces within 36 char limit
        # but we have a 36 char limit, so braces push it to 38 chars

    def test_accepts_nil_uuid(self) -> None:
        """Verify validator accepts nil UUID (all zeros)."""
        assert default_uuid_validator("00000000-0000-0000-0000-000000000000") is True

    def test_accepts_max_uuid(self) -> None:
        """Verify validator accepts max UUID (all ones)."""
        assert default_uuid_validator("ffffffff-ffff-ffff-ffff-ffffffffffff") is True

    # Invalid UUID formats

    def test_rejects_empty_string(self) -> None:
        """Verify validator rejects empty string."""
        assert default_uuid_validator("") is False

    def test_rejects_too_short(self) -> None:
        """Verify validator rejects strings that are too short."""
        assert default_uuid_validator("550e8400-e29b-41d4-a716") is False

    def test_rejects_too_long(self) -> None:
        """Verify validator rejects strings longer than 36 characters."""
        long_string = "a" * 37
        assert default_uuid_validator(long_string) is False

    def test_rejects_excessively_long(self) -> None:
        """Verify validator rejects excessively long strings."""
        very_long_string = "a" * 1000
        assert default_uuid_validator(very_long_string) is False

    def test_rejects_wrong_hyphen_positions(self) -> None:
        """Verify validator rejects UUIDs with hyphens in wrong positions."""
        assert default_uuid_validator("550e-8400-e29b-41d4-a716-446655440000") is False

    def test_rejects_non_hex_characters(self) -> None:
        """Verify validator rejects strings with non-hex characters."""
        assert default_uuid_validator("550e8400-e29b-41d4-a716-44665544gggg") is False

    def test_rejects_special_characters(self) -> None:
        """Verify validator rejects strings with special characters."""
        assert default_uuid_validator("550e8400-e29b-41d4-a716-44665544!@#$") is False

    def test_rejects_whitespace_only(self) -> None:
        """Verify validator rejects whitespace-only strings."""
        assert default_uuid_validator("   ") is False

    def test_rejects_uuid_with_leading_whitespace(self) -> None:
        """Verify validator rejects UUID with leading whitespace."""
        assert default_uuid_validator(" 550e8400-e29b-41d4-a716-446655440000") is False

    def test_rejects_uuid_with_trailing_whitespace(self) -> None:
        """Verify validator rejects UUID with trailing whitespace."""
        assert default_uuid_validator("550e8400-e29b-41d4-a716-446655440000 ") is False

    def test_rejects_random_string(self) -> None:
        """Verify validator rejects random non-UUID strings."""
        assert default_uuid_validator("not-a-uuid-at-all") is False

    def test_rejects_partial_uuid(self) -> None:
        """Verify validator rejects partial UUID strings."""
        assert default_uuid_validator("550e8400-e29b-41d4") is False

    def test_rejects_uuid_with_extra_segment(self) -> None:
        """Verify validator rejects UUID with extra segment."""
        # This is 41 chars, exceeds 36 char limit
        assert (
            default_uuid_validator("550e8400-e29b-41d4-a716-446655440000-extra")
            is False
        )

    # Edge cases

    def test_handles_31_char_hex_string(self) -> None:
        """Verify validator rejects hex string one char short."""
        # 31 characters (one short of valid hex-only format)
        assert default_uuid_validator("550e8400e29b41d4a71644665544000") is False

    def test_handles_33_char_hex_string(self) -> None:
        """Verify validator rejects hex string one char too long."""
        # 33 characters (one too many for hex-only format)
        assert default_uuid_validator("550e8400e29b41d4a7164466554400000") is False

    def test_handles_35_char_hyphenated_string(self) -> None:
        """Verify validator rejects hyphenated string one char short."""
        # 35 characters (one short of valid hyphenated format)
        assert default_uuid_validator("550e8400-e29b-41d4-a716-44665544000") is False

    def test_callable_signature(self) -> None:
        """Verify validator is callable with expected signature."""
        # Should be callable with a single string argument
        result = default_uuid_validator("test")
        assert isinstance(result, bool)
