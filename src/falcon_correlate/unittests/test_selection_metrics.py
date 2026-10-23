"""Tests for pluggable correlation ID selection metrics."""

from __future__ import annotations

import dataclasses
import logging
import typing as typ

import pytest

from falcon_correlate import (
    CorrelationIDMiddleware,
    CorrelationIDMiddlewareASGI,
    CorrelationIDSelectionEvent,
    IncomingIDOutcome,
    SourceTrust,
    correlation_id_var,
)
from falcon_correlate.middleware_utils import CORRELATION_ID_RESET_TOKEN_ATTR
from falcon_correlate.unittests.asgi_middleware_helpers import (
    _process_request as _process_asgi_request,
)
from falcon_correlate.unittests.asgi_middleware_helpers import (
    _process_response as _process_asgi_response,
)
from falcon_correlate.unittests.asgi_middleware_helpers import (
    _Request as _ASGIRequest,
)
from falcon_correlate.unittests.asgi_middleware_helpers import (
    _Response as _ASGIResponse,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    import falcon


class _OutcomeCase(typ.NamedTuple):
    """Inputs and expected classifications for one adapter request case."""

    header: str | None
    remote_addr: str
    validator_mode: str
    outcome: IncomingIDOutcome
    trust: SourceTrust


@dataclasses.dataclass(slots=True)
class _CallbackCalls:
    """Call counts observed while processing one selection scenario."""

    validator: list[str] = dataclasses.field(default_factory=list)
    generator: list[None] = dataclasses.field(default_factory=list)


_OUTCOME_CASES = [
    pytest.param(
        _OutcomeCase(
            None,
            "127.0.0.1",
            "normal",
            IncomingIDOutcome.missing,
            SourceTrust.not_evaluated,
        ),
        id="missing",
    ),
    pytest.param(
        _OutcomeCase(
            " \t ",
            "127.0.0.1",
            "normal",
            IncomingIDOutcome.missing,
            SourceTrust.not_evaluated,
        ),
        id="blank",
    ),
    pytest.param(
        _OutcomeCase(
            "private-id",
            "192.0.2.8",
            "normal",
            IncomingIDOutcome.untrusted,
            SourceTrust.untrusted,
        ),
        id="untrusted",
    ),
    pytest.param(
        _OutcomeCase(
            "private-id",
            "127.0.0.1",
            "normal",
            IncomingIDOutcome.accepted,
            SourceTrust.trusted,
        ),
        id="accepted",
    ),
    pytest.param(
        _OutcomeCase(
            "private-id",
            "127.0.0.1",
            "false",
            IncomingIDOutcome.rejected_invalid,
            SourceTrust.trusted,
        ),
        id="invalid",
    ),
    pytest.param(
        _OutcomeCase(
            "private-id",
            "127.0.0.1",
            "raises",
            IncomingIDOutcome.rejected_validator_error,
            SourceTrust.trusted,
        ),
        id="validator-error",
    ),
]


def _validator_for_mode(
    mode: str,
    calls: _CallbackCalls,
) -> cabc.Callable[[str], bool]:
    """Build a validator that records calls and selects one test result."""

    def validator(value: str) -> bool:
        """Record the checked ID and return or raise the configured result."""
        calls.validator.append(value)
        if mode == "raises":
            msg = "validator failed"
            raise RuntimeError(msg)
        return mode != "false"

    return validator


def _assert_selection(
    events: list[CorrelationIDSelectionEvent],
    outcome: IncomingIDOutcome,
    trust: SourceTrust,
    calls: _CallbackCalls,
) -> str:
    """Assert one bounded selection event and the expected callback counts."""
    assert len(events) == 1, f"expected one selection event, got {events!r}"
    event = events[0]
    assert (event.outcome, event.trust, event.header_name) == (
        outcome,
        trust,
        "X-Correlation-ID",
    ), f"unexpected selection event: {event!r}"
    assert {field.name for field in dataclasses.fields(event)} == {
        "outcome",
        "trust",
        "header_name",
    }, "selection event must omit request ID and remote address"
    should_validate = trust is SourceTrust.trusted
    assert len(calls.validator) == int(should_validate), (
        f"expected validator calls={int(should_validate)}, got {calls.validator!r}"
    )
    should_generate = outcome is not IncomingIDOutcome.accepted
    assert len(calls.generator) == int(should_generate), (
        f"expected generator calls={int(should_generate)}, got {calls.generator!r}"
    )
    return "generated-id" if should_generate else "private-id"


@pytest.mark.parametrize(
    "case",
    _OUTCOME_CASES,
)
def test_wsgi_records_one_selection_event(
    request_response_factory: cabc.Callable[
        ..., tuple[falcon.Request, falcon.Response]
    ],
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    case: _OutcomeCase,
) -> None:
    """WSGI reports each outcome once without changing selected IDs or calls."""
    events = []
    recorder = events.append
    calls = _CallbackCalls()

    def generator() -> str:
        """Return a predictable fallback and count generator calls."""
        calls.generator.append(None)
        return "generated-id"

    middleware = CorrelationIDMiddleware(
        generator=generator,
        trusted_sources=["127.0.0.1"],
        validator=_validator_for_mode(case.validator_mode, calls),
        metrics_recorder=recorder,
    )
    req, resp = request_response_factory(
        correlation_id=case.header,
        remote_addr=case.remote_addr,
    )

    def exercise_request() -> None:
        """Check selection and cleanup within the same ContextVar context."""
        middleware.process_request(req, resp)
        expected_id = _assert_selection(
            events,
            case.outcome,
            case.trust,
            calls,
        )
        assert req.context.correlation_id == expected_id, (
            f"expected selected ID {expected_id!r}, got {req.context.correlation_id!r}"
        )
        middleware.process_response(req, resp, resource=None, req_succeeded=True)
        assert resp.get_header("X-Correlation-ID") == expected_id, (
            f"expected echoed ID {expected_id!r}, got "
            f"{resp.get_header('X-Correlation-ID')!r}"
        )
        assert getattr(req.context, CORRELATION_ID_RESET_TOKEN_ATTR) is None, (
            "expected WSGI request context token to be cleared"
        )
        assert correlation_id_var.get() is None, "expected ContextVar cleanup"

    isolated_context(exercise_request)


@pytest.mark.parametrize(
    "case",
    _OUTCOME_CASES,
)
@pytest.mark.asyncio
async def test_asgi_records_one_selection_event(
    case: _OutcomeCase,
) -> None:
    """ASGI reports the same outcomes and call counts as WSGI."""
    events = []
    recorder = events.append
    calls = _CallbackCalls()

    def generator() -> str:
        """Return a predictable fallback and count generator calls."""
        calls.generator.append(None)
        return "generated-id"

    headers = {} if case.header is None else {"X-Correlation-ID": case.header}
    middleware = CorrelationIDMiddlewareASGI(
        generator=generator,
        trusted_sources=["127.0.0.1"],
        validator=_validator_for_mode(case.validator_mode, calls),
        metrics_recorder=recorder,
    )
    req = _ASGIRequest(headers=headers, remote_addr=case.remote_addr)
    resp = _ASGIResponse()

    await _process_asgi_request(middleware, req, resp)

    expected_id = _assert_selection(
        events,
        case.outcome,
        case.trust,
        calls,
    )
    assert req.context.correlation_id == expected_id, (
        f"expected selected ID {expected_id!r}, got {req.context.correlation_id!r}"
    )

    await _process_asgi_response(middleware, req, resp)
    assert resp.get_header("X-Correlation-ID") == expected_id, (
        f"expected echoed ID {expected_id!r}, got "
        f"{resp.get_header('X-Correlation-ID')!r}"
    )
    assert getattr(req.context, CORRELATION_ID_RESET_TOKEN_ATTR) is None, (
        "expected ASGI request context token to be cleared"
    )
    assert correlation_id_var.get() is None, "expected ContextVar cleanup"


def test_metrics_recorder_failure_is_ignored_and_logged(
    request_response_factory: cabc.Callable[
        ..., tuple[falcon.Request, falcon.Response]
    ],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failing WSGI recorder logs once and leaves request processing intact."""
    failure = RuntimeError("backend unavailable")

    def recorder(event: CorrelationIDSelectionEvent) -> None:
        """Raise the configured metrics backend failure."""
        raise failure

    middleware = CorrelationIDMiddleware(
        generator=lambda: "generated-id",
        metrics_recorder=recorder,
    )
    req, resp = request_response_factory()
    with caplog.at_level(logging.WARNING, logger="falcon_correlate.middleware"):
        middleware.process_request(req, resp)

    records = [
        record
        for record in caplog.records
        if record.getMessage() == "Metrics recorder raised an exception, ignoring"
    ]
    assert len(records) == 1, f"expected one recorder warning, got {records!r}"
    record_exception = records[0].exc_info
    assert record_exception is not None, "expected recorder failure in warning exc_info"
    assert record_exception[1] is failure, "wrong exception logged for recorder failure"
    assert "correlation_id" not in records[0].__dict__, (
        "recorder warning must not include a correlation ID"
    )
    assert req.context.correlation_id == "generated-id", (
        "expected request to continue after recorder failure"
    )
    middleware.process_response(req, resp, resource=None, req_succeeded=True)


@pytest.mark.asyncio
async def test_asgi_metrics_recorder_failure_is_ignored_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failing ASGI recorder logs once and leaves request processing intact."""
    failure = RuntimeError("backend unavailable")

    def recorder(event: CorrelationIDSelectionEvent) -> None:
        """Raise the configured metrics backend failure."""
        raise failure

    middleware = CorrelationIDMiddlewareASGI(
        generator=lambda: "generated-id",
        metrics_recorder=recorder,
    )
    req = _ASGIRequest()
    resp = _ASGIResponse()
    with caplog.at_level(logging.WARNING, logger="falcon_correlate.middleware"):
        await _process_asgi_request(middleware, req, resp)

    records = [
        record
        for record in caplog.records
        if record.getMessage() == "Metrics recorder raised an exception, ignoring"
    ]
    assert len(records) == 1, f"expected one recorder warning, got {records!r}"
    record_exception = records[0].exc_info
    assert record_exception is not None, "expected recorder failure in warning exc_info"
    assert record_exception[1] is failure, "wrong exception logged for recorder failure"
    assert "correlation_id" not in records[0].__dict__, (
        "recorder warning must not include a correlation ID"
    )
    assert req.context.correlation_id == "generated-id", (
        "expected request to continue after recorder failure"
    )
    await _process_asgi_response(middleware, req, resp)


def test_selection_event_is_recorded_before_generator_failure(
    request_response_factory: cabc.Callable[
        ..., tuple[falcon.Request, falcon.Response]
    ],
) -> None:
    """Rejected selection metrics are retained when fallback generation fails."""
    events = []
    failure = RuntimeError("generator failed")

    def generator() -> str:
        """Raise after the rejected incoming ID event is recorded."""
        raise failure

    middleware = CorrelationIDMiddleware(
        generator=generator,
        trusted_sources=["127.0.0.1"],
        validator=lambda _: False,
        metrics_recorder=events.append,
    )
    req, resp = request_response_factory(correlation_id="private-id")

    with pytest.raises(RuntimeError) as exc_info:
        middleware.process_request(req, resp)

    assert exc_info.value is failure, "expected original generator exception"
    assert len(events) == 1, "expected selection event before generation"
    assert events[0].outcome is IncomingIDOutcome.rejected_invalid, (
        "expected rejected incoming ID event"
    )
    assert getattr(req.context, "correlation_id", None) is None, (
        "failed generation set request ID"
    )
    assert getattr(req.context, CORRELATION_ID_RESET_TOKEN_ATTR, None) is None, (
        "failed generation stored a reset token"
    )
