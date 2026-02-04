"""Unit tests for default UUID validator."""

from __future__ import annotations

import pytest

from falcon_correlate import default_uuid_validator


class TestDefaultUUIDValidatorValidFormats:
    """Tests for valid UUID formats accepted by the default validator."""

    @pytest.mark.parametrize(
        ("uuid_string", "description"),
        [
            pytest.param(
                "f47ac10b-58cc-11e9-8000-000000000000",
                "UUIDv1 (time-based)",
                id="v1_hyphenated",
            ),
            pytest.param(
                "550e8400-e29b-21d4-a716-446655440000",
                "UUIDv2 (DCE security)",
                id="v2_hyphenated",
            ),
            pytest.param(
                "550e8400-e29b-31d4-a716-446655440000",
                "UUIDv3 (MD5 hash)",
                id="v3_hyphenated",
            ),
            pytest.param(
                "550e8400-e29b-41d4-a716-446655440000",
                "UUIDv4 (random)",
                id="v4_hyphenated",
            ),
            pytest.param(
                "550e8400-e29b-51d4-a716-446655440000",
                "UUIDv5 (SHA-1 hash)",
                id="v5_hyphenated",
            ),
            pytest.param(
                "1ef21e1a-0800-6000-8000-000000000000",
                "UUIDv6 (reordered time)",
                id="v6_hyphenated",
            ),
            pytest.param(
                "01932c9e-1a3d-7000-8000-000000000000",
                "UUIDv7 (time-ordered)",
                id="v7_hyphenated",
            ),
            pytest.param(
                "550e8400-e29b-81d4-a716-446655440000",
                "UUIDv8 (custom)",
                id="v8_hyphenated",
            ),
        ],
    )
    def test_accepts_valid_uuid_versions(
        self, uuid_string: str, description: str
    ) -> None:
        """Verify validator accepts valid UUIDs for all versions 1-8."""
        assert default_uuid_validator(uuid_string) is True, (
            f"{description} should be accepted"
        )

    def test_accepts_valid_uuid_hex_only(self) -> None:
        """Verify validator accepts a valid UUID as 32-character hex string."""
        assert default_uuid_validator("550e8400e29b41d4a716446655440000") is True, (
            "32-character hex-only UUID should be accepted"
        )

    def test_accepts_uppercase_uuid(self) -> None:
        """Verify validator accepts uppercase UUID strings."""
        assert default_uuid_validator("550E8400-E29B-41D4-A716-446655440000") is True, (
            "uppercase UUID should be accepted"
        )

    def test_accepts_mixed_case_uuid(self) -> None:
        """Verify validator accepts mixed case UUID strings."""
        assert default_uuid_validator("550e8400-E29B-41d4-A716-446655440000") is True, (
            "mixed-case UUID should be accepted"
        )


class TestDefaultUUIDValidatorInvalidFormats:
    """Tests for invalid UUID formats rejected by the default validator."""

    def test_rejects_uuid_with_braces(self) -> None:
        """Verify validator rejects UUID with curly braces due to length limit.

        Microsoft-format UUIDs with braces are 38 characters, which exceeds the
        36-character maximum length enforced by the validator.
        """
        assert (
            default_uuid_validator("{550e8400-e29b-41d4-a716-446655440000}") is False
        ), "brace-wrapped UUID (38 chars) should be rejected due to length limit"

    def test_rejects_nil_uuid(self) -> None:
        """Verify validator rejects nil UUID (version 0, outside valid range 1-8)."""
        assert (
            default_uuid_validator("00000000-0000-0000-0000-000000000000") is False
        ), "nil UUID (version 0) should be rejected"

    def test_rejects_max_uuid(self) -> None:
        """Verify validator rejects max UUID (version 15, outside valid range 1-8)."""
        assert (
            default_uuid_validator("ffffffff-ffff-ffff-ffff-ffffffffffff") is False
        ), "max UUID (version 15) should be rejected"

    def test_rejects_empty_string(self) -> None:
        """Verify validator rejects empty string."""
        assert default_uuid_validator("") is False, "empty string should be rejected"

    @pytest.mark.parametrize(
        ("value", "description"),
        [
            pytest.param("550e8400-e29b-41d4-a716", "partial UUID", id="partial"),
            pytest.param("a" * 31, "31 characters", id="31_chars"),
        ],
    )
    def test_rejects_too_short(self, value: str, description: str) -> None:
        """Verify validator rejects strings that are too short."""
        assert default_uuid_validator(value) is False, (
            f"{description} should be rejected"
        )

    @pytest.mark.parametrize(
        ("value", "description"),
        [
            pytest.param("a" * 37, "37 characters", id="37_chars"),
            pytest.param("a" * 1000, "excessively long (1000 chars)", id="1000_chars"),
        ],
    )
    def test_rejects_too_long(self, value: str, description: str) -> None:
        """Verify validator rejects strings longer than 36 characters."""
        assert default_uuid_validator(value) is False, (
            f"{description} should be rejected"
        )

    @pytest.mark.parametrize(
        ("value", "description"),
        [
            pytest.param("a" * 33, "33 characters", id="33_chars"),
            pytest.param("a" * 34, "34 characters", id="34_chars"),
            pytest.param("a" * 35, "35 characters", id="35_chars"),
        ],
    )
    def test_rejects_gap_length_strings(self, value: str, description: str) -> None:
        """Verify validator rejects strings in the 33-35 character gap."""
        assert default_uuid_validator(value) is False, (
            f"{description} (gap length) should be rejected"
        )

    @pytest.mark.parametrize(
        ("value", "description"),
        [
            pytest.param(
                "550e-8400-e29b-41d4-a716-446655440000",
                "extra hyphen at position 4",
                id="extra_hyphen",
            ),
            pytest.param(
                "550e8400e29b-41d4-a716-446655440000",
                "missing first hyphen",
                id="missing_first_hyphen",
            ),
            pytest.param(
                "550e8400--29b-41d4-a716-446655440000",
                "double hyphen",
                id="double_hyphen",
            ),
            pytest.param(
                "550e8400-e29b41d4-a716-446655440000",
                "misplaced hyphen",
                id="misplaced_hyphen",
            ),
        ],
    )
    def test_rejects_wrong_hyphen_positions(self, value: str, description: str) -> None:
        """Verify validator rejects UUIDs with hyphens in wrong positions."""
        assert default_uuid_validator(value) is False, (
            f"{description} should be rejected"
        )

    @pytest.mark.parametrize(
        ("value", "description"),
        [
            pytest.param(
                "550e8400-e29b-41d4-a716-44665544gggg",
                "non-hex characters",
                id="non_hex",
            ),
            pytest.param(
                "550e8400-e29b-41d4-a716-44665544!@#$",
                "special characters",
                id="special_chars",
            ),
        ],
    )
    def test_rejects_invalid_characters(self, value: str, description: str) -> None:
        """Verify validator rejects strings with invalid characters."""
        assert default_uuid_validator(value) is False, (
            f"{description} should be rejected"
        )

    @pytest.mark.parametrize(
        ("value", "description"),
        [
            pytest.param("   ", "whitespace only", id="whitespace_only"),
            pytest.param(
                " 550e8400-e29b-41d4-a716-446655440000",
                "leading whitespace",
                id="leading_whitespace",
            ),
            pytest.param(
                "550e8400-e29b-41d4-a716-446655440000 ",
                "trailing whitespace",
                id="trailing_whitespace",
            ),
        ],
    )
    def test_rejects_whitespace_variants(self, value: str, description: str) -> None:
        """Verify validator rejects strings with whitespace issues."""
        assert default_uuid_validator(value) is False, (
            f"{description} should be rejected"
        )

    def test_rejects_random_string(self) -> None:
        """Verify validator rejects random non-UUID strings."""
        assert default_uuid_validator("not-a-uuid-at-all") is False, (
            "random string should be rejected"
        )

    def test_rejects_uuid_with_extra_segment(self) -> None:
        """Verify validator rejects UUID with extra segment."""
        assert (
            default_uuid_validator("550e8400-e29b-41d4-a716-446655440000-extra")
            is False
        ), "UUID with extra segment (exceeds 36 chars) should be rejected"


class TestDefaultUUIDValidatorVersionEnforcement:
    """Tests for UUID version range enforcement (versions 1-8 only)."""

    def test_rejects_version_0(self) -> None:
        """Verify validator rejects UUIDs with version nibble 0."""
        # Version nibble is at position 12 (0-indexed) in the hex string
        assert (
            default_uuid_validator("550e8400-e29b-01d4-a716-446655440000") is False
        ), "version 0 UUID should be rejected"

    def test_rejects_version_9(self) -> None:
        """Verify validator rejects UUIDs with version nibble 9."""
        assert (
            default_uuid_validator("550e8400-e29b-91d4-a716-446655440000") is False
        ), "version 9 UUID should be rejected"

    @pytest.mark.parametrize(
        "version_nibble",
        ["a", "b", "c", "d", "e", "f"],
        ids=["v10", "v11", "v12", "v13", "v14", "v15"],
    )
    def test_rejects_versions_10_to_15(self, version_nibble: str) -> None:
        """Verify validator rejects UUIDs with version nibbles 10-15 (a-f)."""
        uuid_string = f"550e8400-e29b-{version_nibble}1d4-a716-446655440000"
        assert default_uuid_validator(uuid_string) is False, (
            f"version {int(version_nibble, 16)} UUID should be rejected"
        )


class TestDefaultUUIDValidatorCallableInterface:
    """Tests for the validator callable interface."""

    def test_callable_signature(self) -> None:
        """Verify validator is callable with expected signature."""
        result = default_uuid_validator("test")
        assert isinstance(result, bool), "validator should return a boolean"

    def test_returns_true_for_valid_input(self) -> None:
        """Verify validator returns True for valid UUID."""
        assert default_uuid_validator("550e8400-e29b-41d4-a716-446655440000") is True, (
            "valid UUID should return True"
        )

    def test_returns_false_for_invalid_input(self) -> None:
        """Verify validator returns False for invalid input."""
        assert default_uuid_validator("invalid") is False, (
            "invalid input should return False"
        )
