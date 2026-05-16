"""Unit tests for CorrelationIDConfig validation."""

from __future__ import annotations

import typing as typ

import pytest

from falcon_correlate import CorrelationIDConfig

if typ.TYPE_CHECKING:
    import collections.abc as cabc


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

    def test_config_scalar_trusted_source_raises_type_error(self) -> None:
        """Verify trusted_sources rejects a single string value."""
        with pytest.raises(TypeError, match="trusted_sources must be an iterable"):
            CorrelationIDConfig(trusted_sources="127.0.0.1")

    def test_config_non_string_trusted_source_raises_type_error(self) -> None:
        """Verify trusted_sources rejects non-string members."""
        with pytest.raises(TypeError, match="trusted_sources must contain strings"):
            CorrelationIDConfig(
                trusted_sources=typ.cast("cabc.Iterable[str]", ["127.0.0.1", 123])
            )

    def test_config_non_callable_generator_raises_type_error(self) -> None:
        """Verify non-callable generator on CorrelationIDConfig raises TypeError."""
        with pytest.raises(TypeError, match="generator must be callable"):
            CorrelationIDConfig(
                generator=typ.cast("cabc.Callable[[], str]", "not-a-callable")
            )

    def test_config_non_callable_validator_raises_type_error(self) -> None:
        """Verify non-callable validator on CorrelationIDConfig raises TypeError."""
        with pytest.raises(TypeError, match="validator must be callable"):
            CorrelationIDConfig(
                validator=typ.cast("cabc.Callable[[str], bool]", "not-a-callable")
            )
