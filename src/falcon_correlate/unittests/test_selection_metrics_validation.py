"""Regression tests for selection metric validation classification."""

from __future__ import annotations

import logging
import typing as typ

from falcon_correlate import (
    CorrelationIDMiddleware,
    CorrelationIDSelectionEvent,
    IncomingIDOutcome,
    SourceTrust,
    correlation_id_var,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    import falcon
    import pytest


class _FalseResult:
    """A falsey validator result that rejects repeated truthiness checks."""

    def __init__(self) -> None:
        """Initialize the truthiness call counter."""
        self.calls = 0

    def __bool__(self) -> bool:
        """Return false once, then fail if classification coerces twice."""
        self.calls += 1
        if self.calls > 1:
            msg = "validator result was coerced more than once"
            raise AssertionError(msg)
        return False


class _RaisingResult:
    """A validator result whose truthiness check raises an error."""

    def __bool__(self) -> bool:
        """Raise to emulate a broken validator result."""
        msg = "validator result could not be classified"
        raise RuntimeError(msg)


def test_rejected_result_is_coerced_once(
    request_response_factory: cabc.Callable[
        ..., tuple[falcon.Request, falcon.Response]
    ],
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
) -> None:
    """Classify one falsey validator result without repeating its coercion."""
    result = _FalseResult()
    events: list[CorrelationIDSelectionEvent] = []

    def validator(_: str) -> bool:
        """Expose a stateful falsey result through the validator API."""
        return typ.cast("bool", result)

    middleware = CorrelationIDMiddleware(
        generator=lambda: "generated-id",
        trusted_sources=["127.0.0.1"],
        validator=validator,
        metrics_recorder=events.append,
    )
    req, resp = request_response_factory(correlation_id="incoming-id")

    def exercise_request() -> None:
        """Assert classification and clean the request context."""
        middleware.process_request(req, resp)
        assert result.calls == 1, "expected one validator-result coercion"
        assert len(events) == 1, "expected one selection event"
        assert events[0].outcome is IncomingIDOutcome.rejected_invalid, (
            "expected falsey result to be classified as rejected"
        )
        assert events[0].trust is SourceTrust.trusted, "expected trusted request source"
        middleware.process_response(
            req,
            resp,
            resource=None,
            req_succeeded=True,
        )

    isolated_context(exercise_request)
    assert correlation_id_var.get() is None, "expected request context cleanup"


def test_raising_result_is_logged_and_records_validator_error(
    caplog: pytest.LogCaptureFixture,
    request_response_factory: cabc.Callable[
        ..., tuple[falcon.Request, falcon.Response]
    ],
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
) -> None:
    """A truthiness exception becomes a validator-error selection event."""
    result = _RaisingResult()
    events: list[CorrelationIDSelectionEvent] = []
    validator_calls: list[str] = []

    def validator(value: str) -> bool:
        """Return a result that raises when validation checks truthiness."""
        validator_calls.append(value)
        return typ.cast("bool", result)

    middleware = CorrelationIDMiddleware(
        generator=lambda: "generated-id",
        trusted_sources=["127.0.0.1"],
        validator=validator,
        metrics_recorder=events.append,
    )
    req, resp = request_response_factory(correlation_id="incoming-id")

    def exercise_request() -> None:
        """Check the fallback ID, event, warning, and request cleanup."""
        with caplog.at_level(logging.WARNING, logger="falcon_correlate.middleware"):
            middleware.process_request(req, resp)
        assert validator_calls == ["incoming-id"], "expected one validator call"
        assert len(events) == 1, "expected one selection event"
        assert events[0].outcome is IncomingIDOutcome.rejected_validator_error, (
            "expected result truthiness failure to be a validator error"
        )
        assert req.context.correlation_id == "generated-id", (
            "expected generated ID after result truthiness failure"
        )
        warning_records = [
            record
            for record in caplog.records
            if record.getMessage().startswith("Validator raised an exception")
        ]
        assert len(warning_records) == 1, "expected one validator warning"
        assert warning_records[0].exc_info is not None, (
            "expected validation failure traceback in warning"
        )
        middleware.process_response(
            req,
            resp,
            resource=None,
            req_succeeded=True,
        )

    isolated_context(exercise_request)
    assert correlation_id_var.get() is None, "expected request context cleanup"
