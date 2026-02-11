"""Unit tests for validation integration in process_request()."""

from __future__ import annotations

import dataclasses
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
        """Build a Falcon TestClient with optional middleware configuration."""
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
        "validator_behavior",
        ["returns_false", "raises"],
        ids=["validator_returns_false", "validator_raises"],
    )
    def test_generator_invoked_on_validation_failure(
        self,
        create_test_client: cabc.Callable[..., falcon.testing.TestClient],
        validator_behavior: str,
    ) -> None:
        """Verify generator is called when the validator rejects or raises."""
        if validator_behavior == "raises":
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


@dataclasses.dataclass(frozen=True)
class ValidationLoggingScenario:
    """Encapsulates parameters for a validation logging test scenario."""

    validator_result: bool | None
    correlation_id: str
    expect_log: bool
    log_contains: str | None

    @property
    def description(self) -> str:
        """Return a human-readable description of this scenario."""
        if self.validator_result is False:
            return "validation_failure_logs"
        if self.validator_result is True:
            return "validation_success_no_log"
        return "no_validator_no_log"


class TestValidationLogging:
    """Tests for DEBUG-level logging of validation failures."""

    @pytest.mark.parametrize(
        "scenario",
        [
            ValidationLoggingScenario(
                validator_result=False,
                correlation_id="bad-id-value",
                expect_log=True,
                log_contains="failed validation",
            ),
            ValidationLoggingScenario(
                validator_result=True,
                correlation_id="good-id-value",
                expect_log=False,
                log_contains=None,
            ),
            ValidationLoggingScenario(
                validator_result=None,
                correlation_id="any-value",
                expect_log=False,
                log_contains=None,
            ),
        ],
        ids=lambda s: s.description,
    )
    def test_validation_logging_behavior(
        self,
        create_test_client: cabc.Callable[..., falcon.testing.TestClient],
        caplog: pytest.LogCaptureFixture,
        scenario: ValidationLoggingScenario,
    ) -> None:
        """Verify DEBUG logging behaviour for validation outcomes."""
        if scenario.validator_result is None:
            client = create_test_client(trusted_sources=["127.0.0.1"])
        else:
            mock_validator = mock.MagicMock(return_value=scenario.validator_result)
            client = create_test_client(
                trusted_sources=["127.0.0.1"],
                validator=mock_validator,
            )

        with caplog.at_level(logging.DEBUG, logger="falcon_correlate.middleware"):
            client.simulate_get(
                "/test",
                headers={"X-Correlation-ID": scenario.correlation_id},
            )

        if scenario.expect_log:
            assert scenario.log_contains is not None
            assert any(
                record.levelno == logging.DEBUG
                and scenario.log_contains in record.getMessage()
                for record in caplog.records
            ), f"Expected DEBUG log containing '{scenario.log_contains}'"
        else:
            middleware_records = [
                r for r in caplog.records if r.name == "falcon_correlate.middleware"
            ]
            assert len(middleware_records) == 0, (
                f"Expected no middleware log records, "
                f"got {len(middleware_records)}: "
                f"{[r.message for r in middleware_records]}"
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
        ("headers", "reason"),
        [
            (None, "header missing"),
            ({"X-Correlation-ID": "   "}, "whitespace header"),
        ],
        ids=["missing_header", "empty_header"],
    )
    def test_validator_not_called_when_unnecessary(
        self,
        create_test_client: cabc.Callable[..., falcon.testing.TestClient],
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


class TestValidatorExceptionHandling:
    """Tests for graceful handling of exceptions raised by user-supplied validators."""

    def test_validator_exception_logs_warning(
        self,
        create_test_client: cabc.Callable[..., falcon.testing.TestClient],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Verify a WARNING log is emitted when the validator raises."""
        mock_validator = mock.MagicMock(
            side_effect=RuntimeError("unexpected"),
        )
        client = create_test_client(
            trusted_sources=["127.0.0.1"],
            validator=mock_validator,
        )

        with caplog.at_level(logging.DEBUG, logger="falcon_correlate.middleware"):
            client.simulate_get(
                "/test",
                headers={"X-Correlation-ID": "crash-value"},
            )

        assert any(
            record.levelno == logging.WARNING
            and "exception" in record.getMessage().lower()
            for record in caplog.records
        ), "Expected WARNING log about validator exception"

    def test_request_succeeds_despite_validator_exception(
        self,
        create_test_client: cabc.Callable[..., falcon.testing.TestClient],
    ) -> None:
        """Verify the request completes with 200 even when the validator raises."""
        mock_validator = mock.MagicMock(side_effect=TypeError("bad type"))
        client = create_test_client(
            trusted_sources=["127.0.0.1"],
            validator=mock_validator,
        )

        response = client.simulate_get(
            "/test",
            headers={"X-Correlation-ID": "will-crash-validator"},
        )

        assert response.status == "200 OK", f"Expected 200 OK, got {response.status}"
        # A correlation ID should still be present (generated, not the incoming one)
        assert response.json["correlation_id"] is not None
        assert response.json["correlation_id"] != "will-crash-validator", (
            "Expected incoming ID not used when validator raises"
        )
