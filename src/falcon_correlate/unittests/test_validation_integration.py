"""Unit tests for validation integration in process_request()."""

from __future__ import annotations

import logging
import typing as typ
from unittest import mock

import falcon
import falcon.testing
import pytest

from falcon_correlate import CorrelationIDMiddleware
from tests.conftest import CorrelationEchoResource

if typ.TYPE_CHECKING:
    import collections.abc as cabc


class _MiddlewareKwargs(typ.TypedDict, total=False):
    """Type definition for CorrelationIDMiddleware keyword arguments."""

    generator: cabc.Callable[[], str]
    trusted_sources: cabc.Iterable[str]
    validator: cabc.Callable[[str], bool]


@pytest.fixture
def correlation_echo_resource() -> CorrelationEchoResource:
    """Provide a CorrelationEchoResource instance for testing."""
    return CorrelationEchoResource()


@pytest.fixture
def create_test_client(
    correlation_echo_resource: CorrelationEchoResource,
) -> cabc.Callable[..., falcon.testing.TestClient]:
    """Build test clients with configurable middleware.

    Args:
        correlation_echo_resource: The resource fixture to add to the app.

    Returns:
        A factory function that creates TestClient instances.

    """

    def _create(
        generator: cabc.Callable[[], str] | None = None,
        trusted_sources: cabc.Iterable[str] | None = None,
        validator: cabc.Callable[[str], bool] | None = None,
    ) -> falcon.testing.TestClient:
        """Build a test client with the specified middleware configuration.

        Args:
            generator: Optional custom generator for correlation IDs.
            trusted_sources: Optional list of trusted source IPs/CIDRs.
            validator: Optional validator for incoming correlation IDs.

        Returns:
            A configured Falcon TestClient.

        """
        kwargs: _MiddlewareKwargs = {}
        if generator is not None:
            kwargs["generator"] = generator
        if trusted_sources is not None:
            kwargs["trusted_sources"] = trusted_sources
        if validator is not None:
            kwargs["validator"] = validator

        middleware = CorrelationIDMiddleware(**kwargs)
        app = falcon.App(middleware=[middleware])
        app.add_route("/test", correlation_echo_resource)
        return falcon.testing.TestClient(app)

    return _create


class TestValidationWhenNoValidatorConfigured:
    """Tests for backwards compatibility when no validator is configured."""

    def test_incoming_id_accepted_without_validation(
        self,
        create_test_client: cabc.Callable[..., falcon.testing.TestClient],
    ) -> None:
        """Verify incoming ID from trusted source is accepted when no validator set."""
        # Trust 127.0.0.1, which is TestClient's default remote_addr
        client = create_test_client(trusted_sources=["127.0.0.1"])

        response = client.simulate_get(
            "/test",
            headers={"X-Correlation-ID": "any-string-is-fine"},
        )

        assert response.json["correlation_id"] == "any-string-is-fine", (
            "Expected incoming ID accepted verbatim without validator"
        )

    def test_non_uuid_accepted_without_validation(
        self,
        create_test_client: cabc.Callable[..., falcon.testing.TestClient],
    ) -> None:
        """Verify non-UUID strings pass through when no validator is configured."""
        client = create_test_client(trusted_sources=["127.0.0.1"])

        response = client.simulate_get(
            "/test",
            headers={"X-Correlation-ID": "not-a-uuid-at-all"},
        )

        assert response.json["correlation_id"] == "not-a-uuid-at-all", (
            "Expected non-UUID ID accepted when no validator configured"
        )


class TestValidationWithValidatorAccepting:
    """Tests for validator returning True (valid ID accepted)."""

    def test_valid_id_accepted_when_validator_returns_true(
        self,
        create_test_client: cabc.Callable[..., falcon.testing.TestClient],
    ) -> None:
        """Verify incoming ID is accepted when validator returns True."""
        mock_validator = mock.MagicMock(return_value=True)
        client = create_test_client(
            trusted_sources=["127.0.0.1"],
            validator=mock_validator,
        )

        response = client.simulate_get(
            "/test",
            headers={"X-Correlation-ID": "valid-id-123"},
        )

        assert response.json["correlation_id"] == "valid-id-123", (
            "Expected incoming ID accepted when validator returns True"
        )

    def test_validator_called_with_incoming_value(
        self,
        create_test_client: cabc.Callable[..., falcon.testing.TestClient],
    ) -> None:
        """Verify validator is called with the incoming header value."""
        mock_validator = mock.MagicMock(return_value=True)
        client = create_test_client(
            trusted_sources=["127.0.0.1"],
            validator=mock_validator,
        )

        client.simulate_get(
            "/test",
            headers={"X-Correlation-ID": "check-this-value"},
        )

        mock_validator.assert_called_once_with("check-this-value")

    def test_generator_not_called_when_validation_passes(
        self,
        create_test_client: cabc.Callable[..., falcon.testing.TestClient],
    ) -> None:
        """Verify generator is not called when validation passes."""
        mock_generator = mock.MagicMock(return_value="should-not-be-used")
        mock_validator = mock.MagicMock(return_value=True)
        client = create_test_client(
            generator=mock_generator,
            trusted_sources=["127.0.0.1"],
            validator=mock_validator,
        )

        client.simulate_get(
            "/test",
            headers={"X-Correlation-ID": "valid-id"},
        )

        assert mock_generator.call_count == 0, (
            f"Expected generator not called, got {mock_generator.call_count} calls"
        )


class TestValidationWithValidatorRejecting:
    """Tests for validator returning False (invalid ID triggers generation)."""

    def test_invalid_id_triggers_new_generation(
        self,
        create_test_client: cabc.Callable[..., falcon.testing.TestClient],
    ) -> None:
        """Verify new ID is generated when validator returns False."""
        mock_generator = mock.MagicMock(return_value="freshly-generated")
        mock_validator = mock.MagicMock(return_value=False)
        client = create_test_client(
            generator=mock_generator,
            trusted_sources=["127.0.0.1"],
            validator=mock_validator,
        )

        response = client.simulate_get(
            "/test",
            headers={"X-Correlation-ID": "bad-format-id"},
        )

        assert response.json["correlation_id"] == "freshly-generated", (
            "Expected generated ID when validation fails"
        )
        assert mock_generator.call_count == 1, (
            f"Expected generator called once, got {mock_generator.call_count} calls"
        )

    def test_rejected_id_not_stored_in_context(
        self,
        create_test_client: cabc.Callable[..., falcon.testing.TestClient],
    ) -> None:
        """Verify rejected ID is not stored on req.context.correlation_id."""
        mock_validator = mock.MagicMock(return_value=False)
        client = create_test_client(
            generator=lambda: "replacement-id",
            trusted_sources=["127.0.0.1"],
            validator=mock_validator,
        )

        response = client.simulate_get(
            "/test",
            headers={"X-Correlation-ID": "should-be-rejected"},
        )

        assert response.json["correlation_id"] != "should-be-rejected", (
            "Expected rejected ID not stored in context"
        )
        assert response.json["correlation_id"] == "replacement-id", (
            "Expected generator output stored instead"
        )

    def test_custom_validator_is_called_when_provided(
        self,
        create_test_client: cabc.Callable[..., falcon.testing.TestClient],
    ) -> None:
        """Verify a custom validator callable is invoked for incoming IDs."""
        call_log: list[str] = []

        def tracking_validator(value: str) -> bool:
            call_log.append(value)
            return value.startswith("ok-")

        client = create_test_client(
            trusted_sources=["127.0.0.1"],
            validator=tracking_validator,
        )

        # Send a valid ID
        response_ok = client.simulate_get(
            "/test",
            headers={"X-Correlation-ID": "ok-valid"},
        )
        # Send an invalid ID
        response_bad = client.simulate_get(
            "/test",
            headers={"X-Correlation-ID": "nope-invalid"},
        )

        assert call_log == ["ok-valid", "nope-invalid"], (
            f"Expected validator called with both values, got {call_log}"
        )
        assert response_ok.json["correlation_id"] == "ok-valid", (
            "Expected valid ID accepted by custom validator"
        )
        assert response_bad.json["correlation_id"] != "nope-invalid", (
            "Expected invalid ID rejected by custom validator"
        )


class TestValidationLogging:
    """Tests for DEBUG-level logging of validation failures."""

    def test_debug_log_emitted_on_validation_failure(
        self,
        create_test_client: cabc.Callable[..., falcon.testing.TestClient],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Verify DEBUG log message emitted when validation fails."""
        mock_validator = mock.MagicMock(return_value=False)
        client = create_test_client(
            trusted_sources=["127.0.0.1"],
            validator=mock_validator,
        )

        with caplog.at_level(logging.DEBUG, logger="falcon_correlate.middleware"):
            client.simulate_get(
                "/test",
                headers={"X-Correlation-ID": "bad-id-value"},
            )

        assert any(
            record.levelno == logging.DEBUG and "bad-id-value" in record.getMessage()
            for record in caplog.records
        ), "Expected at least one DEBUG log containing the rejected correlation ID"

    def test_no_log_emitted_on_validation_success(
        self,
        create_test_client: cabc.Callable[..., falcon.testing.TestClient],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Verify no log message emitted when validation succeeds."""
        mock_validator = mock.MagicMock(return_value=True)
        client = create_test_client(
            trusted_sources=["127.0.0.1"],
            validator=mock_validator,
        )

        with caplog.at_level(logging.DEBUG, logger="falcon_correlate.middleware"):
            client.simulate_get(
                "/test",
                headers={"X-Correlation-ID": "good-id-value"},
            )

        assert len(caplog.records) == 0, (
            f"Expected no log records, got {len(caplog.records)}: "
            f"{[r.message for r in caplog.records]}"
        )

    def test_no_log_emitted_when_no_validator_configured(
        self,
        create_test_client: cabc.Callable[..., falcon.testing.TestClient],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Verify no log message when no validator is configured."""
        client = create_test_client(trusted_sources=["127.0.0.1"])

        with caplog.at_level(logging.DEBUG, logger="falcon_correlate.middleware"):
            client.simulate_get(
                "/test",
                headers={"X-Correlation-ID": "any-value"},
            )

        assert len(caplog.records) == 0, (
            f"Expected no log records without validator, got {len(caplog.records)}"
        )


class TestValidationNotCalledWhenUnnecessary:
    """Tests verifying validator is not called when it would be redundant."""

    def test_validator_not_called_when_source_untrusted(
        self,
        create_test_client: cabc.Callable[..., falcon.testing.TestClient],
    ) -> None:
        """Verify validator is not called when source is untrusted.

        When the source is untrusted, the incoming ID is already rejected
        before validation can occur. The validator should not be invoked.
        """
        mock_validator = mock.MagicMock(return_value=True)
        # Trust only 10.0.0.1, but TestClient uses 127.0.0.1 by default
        client = create_test_client(
            trusted_sources=["10.0.0.1"],
            validator=mock_validator,
        )

        client.simulate_get(
            "/test",
            headers={"X-Correlation-ID": "untrusted-source-id"},
        )

        assert mock_validator.call_count == 0, (
            f"Expected validator not called for untrusted source, "
            f"got {mock_validator.call_count} calls"
        )

    @pytest.mark.parametrize(
        ("scenario", "headers", "reason"),
        [
            ("header_missing", None, "header missing"),
            ("header_empty", {"X-Correlation-ID": "   "}, "whitespace header"),
        ],
        ids=["missing_header", "empty_header"],
    )
    def test_validator_not_called_when_unnecessary(
        self,
        create_test_client: cabc.Callable[..., falcon.testing.TestClient],
        scenario: str,
        headers: dict[str, str] | None,
        reason: str,
    ) -> None:
        """Verify validator is not called when no valid incoming header exists."""
        mock_validator = mock.MagicMock(return_value=True)
        client = create_test_client(
            trusted_sources=["127.0.0.1"],
            validator=mock_validator,
        )

        client.simulate_get("/test", headers=headers)

        assert mock_validator.call_count == 0, (
            f"Expected validator not called for {reason}, "
            f"got {mock_validator.call_count} calls"
        )
