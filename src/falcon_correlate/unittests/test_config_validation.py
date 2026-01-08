"""Unit tests for CorrelationIDConfig validation."""

from __future__ import annotations

import pytest

from falcon_correlate import CorrelationIDConfig


class TestCorrelationIDConfigValidation:
    """Direct unit tests for CorrelationIDConfig validation."""

    def test_config_empty_header_name_raises_value_error(self) -> None:
        """Verify empty header_name on CorrelationIDConfig raises ValueError."""
        with pytest.raises(ValueError, match="header_name must not be empty"):
            CorrelationIDConfig(header_name="")

    def test_config_whitespace_header_name_raises_value_error(self) -> None:
        """Verify whitespace-only header_name raises ValueError."""
        with pytest.raises(ValueError, match="header_name must not be empty"):
            CorrelationIDConfig(header_name="   ")

    def test_config_empty_trusted_source_raises_value_error(self) -> None:
        """Verify empty string in trusted_sources raises ValueError."""
        with pytest.raises(
            ValueError,
            match="trusted_sources must not contain empty strings",
        ):
            CorrelationIDConfig(trusted_sources=frozenset(["127.0.0.1", ""]))

    def test_config_whitespace_trusted_source_raises_value_error(self) -> None:
        """Verify whitespace-only string in trusted_sources raises ValueError."""
        with pytest.raises(
            ValueError,
            match="trusted_sources must not contain empty strings",
        ):
            CorrelationIDConfig(trusted_sources=frozenset(["127.0.0.1", "   "]))

    def test_config_non_callable_generator_raises_type_error(self) -> None:
        """Verify non-callable generator on CorrelationIDConfig raises TypeError."""
        with pytest.raises(TypeError, match="generator must be callable"):
            CorrelationIDConfig(generator="not-a-callable")  # type: ignore[arg-type]

    def test_config_non_callable_validator_raises_type_error(self) -> None:
        """Verify non-callable validator on CorrelationIDConfig raises TypeError."""
        with pytest.raises(TypeError, match="validator must be callable"):
            CorrelationIDConfig(validator="not-a-callable")  # type: ignore[arg-type]
