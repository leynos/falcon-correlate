"""Contract and snapshot tests for observability events and diagnostics."""

from __future__ import annotations

import dataclasses
import logging
import typing as typ

import pytest

from falcon_correlate import (
    CorrelationIDConfig,
    CorrelationIDMiddleware,
    CorrelationIDSelectionEvent,
    IncomingIDOutcome,
    SourceTrust,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    import falcon
    from syrupy.assertion import SnapshotAssertion


_EVENT_CASES = (
    CorrelationIDSelectionEvent(
        IncomingIDOutcome.missing,
        SourceTrust.not_evaluated,
        "X-Correlation-ID",
    ),
    CorrelationIDSelectionEvent(
        IncomingIDOutcome.untrusted,
        SourceTrust.untrusted,
        "X-Correlation-ID",
    ),
    CorrelationIDSelectionEvent(
        IncomingIDOutcome.accepted,
        SourceTrust.trusted,
        "X-Correlation-ID",
    ),
    CorrelationIDSelectionEvent(
        IncomingIDOutcome.rejected_invalid,
        SourceTrust.trusted,
        "X-Request-ID",
    ),
    CorrelationIDSelectionEvent(
        IncomingIDOutcome.rejected_validator_error,
        SourceTrust.trusted,
        "other",
    ),
)


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    [
        pytest.param("outcome", IncomingIDOutcome.accepted, id="outcome"),
        pytest.param("trust", SourceTrust.trusted, id="trust"),
        pytest.param("header_name", "X-Request-ID", id="header-name"),
    ],
)
def test_selection_event_fields_are_immutable(
    field_name: str,
    replacement: object,
) -> None:
    """Event fields cannot change and slotted instances have no dict."""
    event = _EVENT_CASES[0]

    assert not hasattr(event, "__dict__"), "expected event to have no instance dict"
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(event, field_name, replacement)


def test_selection_enum_values_match_the_documented_finite_sets() -> None:
    """Enum values remain the documented bounded metric label domains."""
    assert {outcome.value for outcome in IncomingIDOutcome} == {
        "missing",
        "untrusted",
        "accepted",
        "rejected_invalid",
        "rejected_validator_error",
    }, "unexpected incoming-ID outcome label"
    assert {trust.value for trust in SourceTrust} == {
        "trusted",
        "untrusted",
        "not_evaluated",
    }, "unexpected source-trust label"


@pytest.mark.parametrize(
    ("configured_header", "expected_label"),
    [
        pytest.param("X-Correlation-ID", "X-Correlation-ID", id="default"),
        pytest.param("x-request-id", "X-Request-ID", id="case-folded"),
        pytest.param("X-Private-Company-ID", "other", id="custom"),
    ],
)
def test_selection_event_header_label_uses_a_finite_allowlist(
    request_response_factory: cabc.Callable[
        ..., tuple[falcon.Request, falcon.Response]
    ],
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    configured_header: str,
    expected_label: str,
) -> None:
    """Arbitrary configured header names collapse to a bounded event label."""
    events: list[CorrelationIDSelectionEvent] = []
    middleware = CorrelationIDMiddleware(
        header_name=configured_header,
        generator=lambda: "generated-id",
        metrics_recorder=events.append,
    )
    req, resp = request_response_factory()

    def process_request_and_response() -> None:
        """Run and clean up a missing-header request."""
        middleware.process_request(req, resp)
        middleware.process_response(
            req,
            resp,
            resource=None,
            req_succeeded=True,
        )

    isolated_context(process_request_and_response)

    assert len(events) == 1, "expected one metric event"
    assert events[0].header_name == expected_label, "unbounded header label escaped"


def test_selection_event_matrix_matches_snapshot(
    snapshot: SnapshotAssertion,
) -> None:
    """The finite event matrix remains stable for metric integrations."""
    serialized = [
        {
            "outcome": event.outcome.value,
            "trust": event.trust.value,
            "header_name": event.header_name,
        }
        for event in _EVENT_CASES
    ]

    assert serialized == snapshot, "selection event matrix changed"


def _close_wsgi_request(
    middleware: CorrelationIDMiddleware,
    req: falcon.Request,
    resp: falcon.Response,
) -> None:
    """Run and clean up a successful WSGI request."""
    middleware.process_request(req, resp)
    middleware.process_response(
        req,
        resp,
        resource=None,
        req_succeeded=True,
    )


def _snapshot_log_record(record: logging.LogRecord) -> dict[str, str | bool | None]:
    """Keep stable log fields while redacting rejected values and tracebacks."""
    config_field = getattr(record, "config_field", None)
    if config_field is not None:
        message = (
            "Correlation ID configuration validation failed for "
            f"{config_field}: rejected value <redacted>"
        )
    else:
        message = record.getMessage()

    exception_type = None
    if record.exc_info is not None:
        exception_type = type(record.exc_info[1]).__qualname__

    return {
        "logger": record.name,
        "level": record.levelname,
        "message": message,
        "config_field": config_field,
        "config_rejected_value": (
            "<redacted>" if hasattr(record, "config_rejected_value") else None
        ),
        "header_name": record.__dict__.get("header_name"),
        "exception_type": exception_type,
        "has_correlation_id": "correlation_id" in record.__dict__,
    }


def _record_validator_exception(
    request_response_factory: cabc.Callable[
        ..., tuple[falcon.Request, falcon.Response]
    ],
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
) -> None:
    """Capture the validator-exception diagnostic without retaining request data."""

    def failing_validator(_incoming: str) -> bool:
        """Raise to exercise validator failure logging."""
        msg = "private validator detail"
        raise RuntimeError(msg)

    middleware = CorrelationIDMiddleware(
        trusted_sources=["127.0.0.1"],
        validator=failing_validator,
        generator=lambda: "fallback-id",
    )
    req, resp = request_response_factory(correlation_id="private-incoming-id")
    isolated_context(lambda: _close_wsgi_request(middleware, req, resp))


def _record_generator_exception(
    request_response_factory: cabc.Callable[
        ..., tuple[falcon.Request, falcon.Response]
    ],
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
) -> None:
    """Capture the generator-exception diagnostic and propagated failure."""

    def failing_generator() -> str:
        """Raise to exercise generator failure logging."""
        msg = "private generator detail"
        raise RuntimeError(msg)

    middleware = CorrelationIDMiddleware(generator=failing_generator)
    req, resp = request_response_factory()
    with pytest.raises(RuntimeError, match="private generator detail"):
        isolated_context(lambda: middleware.process_request(req, resp))


def _record_recorder_exception(
    request_response_factory: cabc.Callable[
        ..., tuple[falcon.Request, falcon.Response]
    ],
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
) -> None:
    """Capture the isolated metrics-recorder failure diagnostic."""

    def failing_recorder(_event: CorrelationIDSelectionEvent) -> None:
        """Raise to exercise recorder failure logging."""
        msg = "private recorder detail"
        raise RuntimeError(msg)

    middleware = CorrelationIDMiddleware(
        generator=lambda: "fallback-id",
        metrics_recorder=failing_recorder,
    )
    req, resp = request_response_factory()
    isolated_context(lambda: _close_wsgi_request(middleware, req, resp))


def test_canonical_observability_logs_match_redacted_snapshot(
    caplog: pytest.LogCaptureFixture,
    request_response_factory: cabc.Callable[
        ..., tuple[falcon.Request, falcon.Response]
    ],
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    snapshot: SnapshotAssertion,
) -> None:
    """Config and request failure logs expose stable diagnostics only."""
    caplog.set_level(logging.DEBUG, logger="falcon_correlate.middleware_config")
    caplog.set_level(logging.DEBUG, logger="falcon_correlate.middleware")
    rejected_header = "\r\n\t"

    with pytest.raises(ValueError, match="header_name must not be empty"):
        CorrelationIDConfig(header_name=rejected_header)

    _record_validator_exception(request_response_factory, isolated_context)
    _record_generator_exception(request_response_factory, isolated_context)
    _record_recorder_exception(request_response_factory, isolated_context)

    messages = {
        "Correlation ID configuration validation failed for %s: rejected value %s",
        "Validator raised an exception for correlation ID, treating as invalid",
        "Correlation ID generator raised an exception",
        "Metrics recorder raised an exception, ignoring",
    }
    records = [record for record in caplog.records if record.msg in messages]
    serialized = [_snapshot_log_record(record) for record in records]

    assert len(records) == 4, f"expected four observability records, got {records!r}"
    assert repr(rejected_header) in records[0].getMessage(), (
        "expected rejected header rendering to escape line breaks"
    )
    assert "private-incoming-id" not in repr(serialized), (
        "snapshot exposed an incoming correlation ID"
    )
    assert "private validator detail" not in repr(serialized), (
        "snapshot exposed validator exception details"
    )
    assert "private generator detail" not in repr(serialized), (
        "snapshot exposed generator exception details"
    )
    assert "private recorder detail" not in repr(serialized), (
        "snapshot exposed recorder exception details"
    )
    assert serialized == snapshot, "redacted observability log contract changed"
