"""Unit tests for validation integration in process_request()."""

from __future__ import annotations

import typing as typ
from unittest import mock

import pytest

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    import falcon.testing


class TestValidationWhenNoValidatorConfigured:
    """Tests for backwards compatibility when no validator is configured."""

    @pytest.mark.parametrize(
        "incoming_id",
        ["any-string-is-fine", "not-a-uuid-at-all"],
        ids=["arbitrary_string", "non_uuid_string"],
    )
    def test_incoming_id_accepted_without_validation(
        self,
        create_test_client: cabc.Callable[..., falcon.testing.TestClient],
        incoming_id: str,
    ) -> None:
        """Verify incoming ID from trusted source is accepted when no validator set."""
        client = create_test_client(trusted_sources=["127.0.0.1"])

        response = client.simulate_get(
            "/test",
            headers={"X-Correlation-ID": incoming_id},
        )

        assert response.json["correlation_id"] == incoming_id, (
            f"Expected incoming ID '{incoming_id}' accepted verbatim without validator"
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

    @pytest.mark.parametrize(
        "validator_behaviour",
        ["returns_false", "raises"],
        ids=["validator_returns_false", "validator_raises"],
    )
    def test_generator_invoked_on_validation_failure(
        self,
        create_test_client: cabc.Callable[..., falcon.testing.TestClient],
        validator_behaviour: str,
    ) -> None:
        """Verify generator is called when the validator rejects or raises."""
        if validator_behaviour == "raises":
            mock_validator = mock.MagicMock(side_effect=ValueError("boom"))
        else:
            mock_validator = mock.MagicMock(return_value=False)
        mock_generator = mock.MagicMock(return_value="fallback-id")
        client = create_test_client(
            generator=mock_generator,
            trusted_sources=["127.0.0.1"],
            validator=mock_validator,
        )

        response = client.simulate_get(
            "/test",
            headers={"X-Correlation-ID": "bad-format-id"},
        )

        assert response.json["correlation_id"] == "fallback-id", (
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
            """Record the input and reject values that do not start with ``ok-``."""
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
