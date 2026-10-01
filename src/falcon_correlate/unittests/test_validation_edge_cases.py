"""Integration tests for validation logging and edge cases."""

from __future__ import annotations

import dataclasses
import logging
import typing as typ
from unittest import mock

import pytest

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    import falcon.testing


@dataclasses.dataclass(frozen=True, slots=True)
class ValidationLoggingScenario:
    """Encapsulates parameters for a validation logging test scenario."""

    validator_result: bool | None
    correlation_id: str
    expect_log: bool
    log_contains: str | None

    @property
    def description(self) -> str:
        """Human-readable description of this scenario."""
        if self.validator_result is False:
            return "validation_failure_logs"
        if self.validator_result is True:
            return "validation_success_no_log"
        return "no_validator_no_log"


def _is_debug_log_containing(record: logging.LogRecord, text: str) -> bool:
    """Return True if *record* is a DEBUG entry whose message contains *text*."""
    return (
        record.name == "falcon_correlate.middleware"
        and record.levelno == logging.DEBUG
        and text in record.getMessage()
    )


def _is_validation_failure_debug_log(record: logging.LogRecord) -> bool:
    """Return True if *record* is a falcon_correlate DEBUG 'failed validation' entry."""
    return (
        record.name == "falcon_correlate.middleware"
        and record.levelno == logging.DEBUG
        and "failed validation" in record.getMessage()
    )


def build_test_client(
    create_test_client: cabc.Callable[..., falcon.testing.TestClient],
    validator_result: bool | None,  # ruff: ignore[boolean-type-hint-positional-argument] - test scenario value
) -> falcon.testing.TestClient:
    """Build a validation logging test client for the given validator result.

    Parameters
    ----------
    create_test_client : cabc.Callable[..., falcon.testing.TestClient]
        Factory fixture that builds a configured test client.
    validator_result : bool | None
        The value the mock validator should return, or ``None`` to build
        a client with no validator.

    Returns
    -------
    falcon.testing.TestClient
        A client with no validator when ``validator_result`` is ``None``;
        otherwise, a client with a mock validator returning that result.

    """
    if validator_result is None:
        return create_test_client(trusted_sources=["127.0.0.1"])

    mock_validator = mock.MagicMock(return_value=validator_result)
    return create_test_client(
        trusted_sources=["127.0.0.1"],
        validator=mock_validator,
    )


def assert_validation_logged(
    caplog: pytest.LogCaptureFixture,
    expected_substring: str,
) -> None:
    """Assert that a falcon_correlate.middleware DEBUG log contains the expected substring."""  # ruff: ignore[line-too-long] -- descriptive BDD assertion wording.
    assert any(
        _is_debug_log_containing(r, expected_substring) for r in caplog.records
    ), (
        f"Expected DEBUG log from 'falcon_correlate.middleware' "
        f"containing '{expected_substring}'"
    )


def assert_validation_not_logged(caplog: pytest.LogCaptureFixture) -> None:
    """Assert that no validation failure debug log was emitted."""
    assert not any(_is_validation_failure_debug_log(r) for r in caplog.records), (
        "Expected no validation failure log records, "
        f"got {[r.getMessage() for r in caplog.records]}"
    )


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
    def test_validation_logging_behaviour(
        self,
        create_test_client: cabc.Callable[..., falcon.testing.TestClient],
        caplog: pytest.LogCaptureFixture,
        scenario: ValidationLoggingScenario,
    ) -> None:
        """Verify DEBUG logging behaviour for validation outcomes."""
        client = build_test_client(create_test_client, scenario.validator_result)

        with caplog.at_level(logging.DEBUG, logger="falcon_correlate.middleware"):
            client.simulate_get(
                "/test",
                headers={"X-Correlation-ID": scenario.correlation_id},
            )

        if scenario.expect_log:
            failure_message = "expected scenario.log_contains not to be None"
            assert scenario.log_contains is not None, failure_message
            assert_validation_logged(caplog, scenario.log_contains)
        else:
            assert_validation_not_logged(caplog)


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

        warning_record = next(
            record
            for record in caplog.records
            if record.name == "falcon_correlate.middleware"
            and record.levelno == logging.WARNING
            and record.getMessage()
            == "Validator raised an exception for correlation ID, treating as invalid"
        )
        warning_log = typ.cast("typ.Any", warning_record)
        assert warning_log.correlation_id == "crash-value", (
            "expected validator warning correlation_id to be 'crash-value' but got "
            f"{warning_log.correlation_id!r}"
        )
        assert warning_log.header_name == "X-Correlation-ID", (
            "expected validator warning header_name to be 'X-Correlation-ID' but got "
            f"{warning_log.header_name!r}"
        )

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
        failure_message = "expected response.json['correlation_id'] not to be None"
        assert response.json["correlation_id"] is not None, failure_message
        assert response.json["correlation_id"] != "will-crash-validator", (
            "Expected incoming ID not used when validator raises"
        )
