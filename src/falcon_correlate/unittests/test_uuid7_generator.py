"""Unit tests for default UUIDv7 generator."""

from __future__ import annotations

import uuid

from falcon_correlate import default_uuid7_generator

UUID_HEX_LENGTH = 32
UUID_VERSION = 7


class TestDefaultUUID7Generator:
    """Tests for default UUIDv7 generator."""

    def test_returns_uuid7_hex_string(self) -> None:
        """Verify the generator returns a UUIDv7 hex string."""
        value = default_uuid7_generator()
        assert isinstance(value, str)
        assert len(value) == UUID_HEX_LENGTH
        assert value == value.lower()
        _ = int(value, 16)

        parsed = uuid.UUID(hex=value)
        assert parsed.version == UUID_VERSION
        assert parsed.variant == uuid.RFC_4122

    def test_returns_unique_values(self) -> None:
        """Verify generator returns unique values across calls."""
        first = default_uuid7_generator()
        second = default_uuid7_generator()
        assert first != second
