"""Unit tests for CorrelationIDMiddleware configuration options."""
# TODO(TECHDEBT): split classes; see https://github.com/leynos/falcon-correlate/issues/37.
# Suggested groups: DefaultValueTests, ValidationTests,
# ImmutabilityTests, and ConfigConstructionTests before this class grows.
# pylint: disable=too-many-public-methods

from __future__ import annotations

import pytest

from falcon_correlate import CorrelationIDConfig, CorrelationIDMiddleware
from falcon_correlate.middleware import default_uuid7_generator


class TestCorrelationIDMiddlewareConfiguration:
    """Tests for CorrelationIDMiddleware configuration options."""

    # Default value tests

    def test_default_header_name(self) -> None:
        """Verify default header_name is X-Correlation-ID."""
        middleware = CorrelationIDMiddleware()
        failure_message = "expected middleware.header_name to equal 'X-Correlation-ID'"
        assert middleware.header_name == "X-Correlation-ID", failure_message

    def test_default_trusted_sources_is_empty_frozenset(self) -> None:
        """Verify default trusted_sources is an empty frozenset."""
        middleware = CorrelationIDMiddleware()
        failure_message = "expected middleware.trusted_sources to equal frozenset()"
        assert middleware.trusted_sources == frozenset(), failure_message
        failure_message = (
            "expected condition: isinstance(middleware.trusted_sources, fr..."
        )
        assert isinstance(middleware.trusted_sources, frozenset), failure_message

    def test_default_generator_is_default_uuid7_generator(self) -> None:
        """Verify default generator is default_uuid7_generator."""
        middleware = CorrelationIDMiddleware()
        failure_message = "expected middleware.generator to be default_uuid7_generator"
        assert middleware.generator is default_uuid7_generator, failure_message

    def test_default_validator_is_none(self) -> None:
        """Verify default validator is None."""
        middleware = CorrelationIDMiddleware()
        assert middleware.validator is None, "expected middleware.validator to be None"

    def test_default_echo_header_in_response_is_true(self) -> None:
        """Verify default echo_header_in_response is True."""
        middleware = CorrelationIDMiddleware()
        failure_message = "expected middleware.echo_header_in_response to be True"
        assert middleware.echo_header_in_response is True, failure_message

    # Custom configuration tests

    def test_custom_header_name(self) -> None:
        """Verify custom header_name is stored."""
        middleware = CorrelationIDMiddleware(header_name="X-Request-ID")
        failure_message = "expected middleware.header_name to equal 'X-Request-ID'"
        assert middleware.header_name == "X-Request-ID", failure_message

    def test_custom_trusted_sources_from_list(self) -> None:
        """Verify trusted_sources from list is stored as frozenset."""
        sources = ["127.0.0.1", "10.0.0.1"]
        middleware = CorrelationIDMiddleware(trusted_sources=sources)
        failure_message = (
            "expected middleware.trusted_sources to equal frozenset(sources)"
        )
        assert middleware.trusted_sources == frozenset(sources), failure_message

    def test_custom_trusted_sources_from_tuple(self) -> None:
        """Verify trusted_sources from tuple is stored as frozenset."""
        sources = ("127.0.0.1", "192.168.1.1")
        middleware = CorrelationIDMiddleware(trusted_sources=sources)
        failure_message = (
            "expected middleware.trusted_sources to equal frozenset(sources)"
        )
        assert middleware.trusted_sources == frozenset(sources), failure_message

    def test_custom_trusted_sources_from_set(self) -> None:
        """Verify trusted_sources from set is stored as frozenset."""
        sources = {"127.0.0.1", "10.0.0.1"}
        middleware = CorrelationIDMiddleware(trusted_sources=sources)
        failure_message = (
            "expected middleware.trusted_sources to equal frozenset(sources)"
        )
        assert middleware.trusted_sources == frozenset(sources), failure_message

    def test_custom_generator(self) -> None:
        """Verify custom generator is stored."""

        def custom_gen() -> str:
            """Generate a custom correlation ID for the test.

            Returns
            -------
            str
                The value produced for the test scenario.

            """
            return "custom-id"

        middleware = CorrelationIDMiddleware(generator=custom_gen)
        failure_message = "expected middleware.generator to be custom_gen"
        assert middleware.generator is custom_gen, failure_message

    def test_custom_validator(self) -> None:
        """Verify custom validator is stored."""

        def custom_validator(value: str) -> bool:
            """Validate the candidate correlation ID for the test.

            Returns
            -------
            bool
                The value produced for the test scenario.

            """
            return len(value) > 0

        middleware = CorrelationIDMiddleware(validator=custom_validator)
        failure_message = "expected middleware.validator to be custom_validator"
        assert middleware.validator is custom_validator, failure_message

    def test_echo_header_in_response_false(self) -> None:
        """Verify echo_header_in_response can be set to False."""
        middleware = CorrelationIDMiddleware(echo_header_in_response=False)
        failure_message = "expected middleware.echo_header_in_response to be False"
        assert middleware.echo_header_in_response is False, failure_message

    # Validation and error handling tests

    def test_empty_header_name_raises_value_error(self) -> None:
        """Verify empty header_name raises ValueError."""
        with pytest.raises(ValueError, match="header_name must not be empty"):
            CorrelationIDMiddleware(header_name="")

    def test_whitespace_header_name_raises_value_error(self) -> None:
        """Verify whitespace-only header_name raises ValueError."""
        with pytest.raises(ValueError, match="header_name must not be empty"):
            CorrelationIDMiddleware(header_name="   ")

    def test_empty_trusted_source_raises_value_error(self) -> None:
        """Verify empty string in trusted_sources raises ValueError."""
        with pytest.raises(
            ValueError,
            match="trusted_sources must not contain empty strings",
        ):
            CorrelationIDMiddleware(trusted_sources=["127.0.0.1", ""])

    def test_whitespace_trusted_source_raises_value_error(self) -> None:
        """Verify whitespace-only string in trusted_sources raises ValueError."""
        with pytest.raises(
            ValueError,
            match="trusted_sources must not contain empty strings",
        ):
            CorrelationIDMiddleware(trusted_sources=["127.0.0.1", "   "])

    def test_non_callable_generator_raises_type_error(self) -> None:
        """Verify non-callable generator raises TypeError."""
        with pytest.raises(TypeError, match="generator must be callable"):
            CorrelationIDMiddleware(generator="not-callable")

    def test_non_callable_validator_raises_type_error(self) -> None:
        """Verify non-callable validator raises TypeError."""
        with pytest.raises(TypeError, match="validator must be callable"):
            CorrelationIDMiddleware(validator="not-callable")

    def test_unknown_kwarg_raises_type_error(self) -> None:
        """Verify unknown keyword arguments raise TypeError with helpful message."""
        with pytest.raises(TypeError) as excinfo:
            CorrelationIDMiddleware(foo=1)

        message = str(excinfo.value)
        assert "foo" in message, "expected 'foo' to be present in message"
        failure_message = (
            "expected 'Unknown keyword arguments' to be present in message"
        )
        assert "Unknown keyword arguments" in message, failure_message

    def test_config_and_kwargs_conflict_raises_value_error(self) -> None:
        """Verify providing both config and other kwargs raises ValueError."""
        config = CorrelationIDConfig()

        with pytest.raises(
            ValueError,
            match="Cannot specify both 'config' and individual parameters",
        ):
            CorrelationIDMiddleware(
                config=config,
                header_name="X-Request-ID",
            )

    # Immutability tests

    def test_trusted_sources_is_immutable(self) -> None:
        """Verify trusted_sources cannot be modified after creation."""
        sources = ["127.0.0.1"]
        middleware = CorrelationIDMiddleware(trusted_sources=sources)
        # Modifying original list should not affect middleware
        sources.append("10.0.0.1")
        failure_message = (
            "expected condition: middleware.trusted_sources == frozenset([..."
        )
        assert middleware.trusted_sources == frozenset(["127.0.0.1"]), failure_message

    def test_config_trusted_sources_is_frozen_from_mutable_input(self) -> None:
        """Verify direct config construction freezes trusted source inputs."""
        sources = {"127.0.0.1"}
        config = CorrelationIDConfig(trusted_sources=sources)

        sources.add("10.0.0.1")

        failure_message = (
            "expected condition: config.trusted_sources == frozenset(['127..."
        )
        assert config.trusted_sources == frozenset(["127.0.0.1"]), failure_message
        failure_message = (
            "expected condition: isinstance(config.trusted_sources, frozen..."
        )
        assert isinstance(config.trusted_sources, frozenset), failure_message

    # Combined configuration tests

    def test_all_parameters_can_be_set(self) -> None:
        """Verify all parameters can be set together."""

        def gen() -> str:
            """Generate a custom correlation ID for the test.

            Returns
            -------
            str
                The value produced for the test scenario.

            """
            return "id"

        def val(s: str) -> bool:
            """Validate the candidate correlation ID for the test.

            Returns
            -------
            bool
                The value produced for the test scenario.

            """
            return True

        middleware = CorrelationIDMiddleware(
            header_name="X-Custom-ID",
            trusted_sources=["10.0.0.1"],
            generator=gen,
            validator=val,
            echo_header_in_response=False,
        )
        failure_message = "expected middleware.header_name to equal 'X-Custom-ID'"
        assert middleware.header_name == "X-Custom-ID", failure_message
        failure_message = (
            "expected condition: middleware.trusted_sources == frozenset([..."
        )
        assert middleware.trusted_sources == frozenset(["10.0.0.1"]), failure_message
        assert middleware.generator is gen, "expected middleware.generator to be gen"
        assert middleware.validator is val, "expected middleware.validator to be val"
        failure_message = "expected middleware.echo_header_in_response to be False"
        assert middleware.echo_header_in_response is False, failure_message

    # Config-based construction tests

    def test_config_based_construction_uses_given_config(self) -> None:
        """Verify supplying a CorrelationIDConfig sets and exposes the same config."""
        cfg = CorrelationIDConfig(
            header_name="X-Request-ID",
            echo_header_in_response=False,
            trusted_sources=frozenset({"127.0.0.1", "10.0.0.1"}),
        )

        middleware = CorrelationIDMiddleware(config=cfg)

        # The middleware should hold a reference to the exact config object
        assert middleware.config is cfg, "expected middleware.config to be cfg"

        # And its exposed properties should reflect the config values
        failure_message = "expected middleware.header_name to equal cfg.header_name"
        assert middleware.header_name == cfg.header_name, failure_message
        failure_message = (
            "expected condition: middleware.echo_header_in_response == cfg..."
        )
        assert middleware.echo_header_in_response == cfg.echo_header_in_response, (
            failure_message
        )
        failure_message = (
            "expected middleware.trusted_sources to equal cfg.trusted_sources"
        )
        assert middleware.trusted_sources == cfg.trusted_sources, failure_message

    def test_config_from_kwargs_equivalence(self) -> None:
        """Verify CorrelationIDConfig.from_kwargs matches direct construction."""
        header_name = "X-Request-ID"
        trusted_sources_list = ["127.0.0.1", "10.0.0.1"]
        echo_header_in_response = False

        cfg_direct = CorrelationIDConfig(
            header_name=header_name,
            trusted_sources=frozenset(trusted_sources_list),
            echo_header_in_response=echo_header_in_response,
        )
        cfg_from_kwargs = CorrelationIDConfig.from_kwargs(
            header_name=header_name,
            trusted_sources=trusted_sources_list,
            echo_header_in_response=echo_header_in_response,
        )

        # from_kwargs should produce an equivalent configuration
        failure_message = (
            "expected condition: cfg_from_kwargs.header_name == cfg_direct..."
        )
        assert cfg_from_kwargs.header_name == cfg_direct.header_name, failure_message
        failure_message = (
            "expected condition: cfg_from_kwargs.echo_header_in_response =..."
        )
        assert (
            cfg_from_kwargs.echo_header_in_response
            == cfg_direct.echo_header_in_response
        ), failure_message
        failure_message = (
            "expected condition: cfg_from_kwargs.trusted_sources == cfg_di..."
        )
        assert cfg_from_kwargs.trusted_sources == cfg_direct.trusted_sources, (
            failure_message
        )
