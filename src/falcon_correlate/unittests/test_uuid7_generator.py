"""Unit tests for default UUIDv7 generator."""

from __future__ import annotations

import sys
import typing as typ
from types import SimpleNamespace

if typ.TYPE_CHECKING:
    import pytest

from falcon_correlate import default_uuid7_generator
from falcon_correlate.unittests.uuid7_helpers import assert_uuid7_hex


class TestDefaultUUID7Generator:
    """Tests for default UUIDv7 generator."""

    def test_returns_uuid7_hex_string(self) -> None:
        """Verify the generator returns a UUIDv7 hex string."""
        value = default_uuid7_generator()
        assert_uuid7_hex(value)

    def test_returns_unique_values(self) -> None:
        """Verify generator returns unique values across calls."""
        first = default_uuid7_generator()
        second = default_uuid7_generator()
        assert first != second, "expected unique UUIDv7 values across calls"

    def test_falls_back_when_uuid7_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify fallback to uuid_utils when uuid.uuid7 is unavailable."""
        monkeypatch.setattr(
            "falcon_correlate.middleware.uuid.uuid7", None, raising=False
        )
        sentinel_hex = "f" * 32
        fake_uuid_utils = SimpleNamespace(
            uuid7=lambda: SimpleNamespace(hex=sentinel_hex),
        )
        monkeypatch.setitem(sys.modules, "uuid_utils", fake_uuid_utils)

        value = default_uuid7_generator()
        assert value == sentinel_hex, "expected fallback UUIDv7 value to be used"
