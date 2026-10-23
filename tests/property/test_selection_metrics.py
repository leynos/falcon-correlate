"""Property checks for metrics classification across header and trust inputs."""

from __future__ import annotations

import contextvars
import dataclasses

import falcon
import falcon.testing
from hypothesis import given, settings
from hypothesis import strategies as st

from falcon_correlate import (
    CorrelationIDMiddleware,
    CorrelationIDSelectionEvent,
    IncomingIDOutcome,
    SourceTrust,
)
from falcon_correlate.middleware_utils import CORRELATION_ID_RESET_TOKEN_ATTR

_header_values = st.one_of(
    st.none(),
    st.text(alphabet=" abcdefghijklmnopqrstuvwxyz0123456789-_", max_size=24),
)
_scenario_values = st.tuples(
    _header_values,
    st.sampled_from([SourceTrust.trusted, SourceTrust.untrusted]),
    st.sampled_from(["accept", "reject", "raise"]),
)
type _ExpectedSelection = tuple[IncomingIDOutcome, SourceTrust, int, str]


class _CountingValidator:
    """A validator that records calls and follows one generated result."""

    __slots__ = ("calls", "mode")

    def __init__(self, mode: str) -> None:
        """Store the generated validator outcome and initialize call tracking."""
        self.mode = mode
        self.calls: list[str] = []

    def __call__(self, value: str) -> bool:
        """Record the candidate ID and return or raise the generated result."""
        self.calls.append(value)
        if self.mode == "raise":
            msg = "generated validator failure"
            raise RuntimeError(msg)
        return self.mode == "accept"


@dataclasses.dataclass(slots=True)
class _SelectionRun:
    """State for one generated request and its expected metric classification."""

    middleware: CorrelationIDMiddleware
    req: falcon.Request
    resp: falcon.Response
    events: list[CorrelationIDSelectionEvent]
    validator: _CountingValidator
    expected: _ExpectedSelection

    def exercise(self) -> None:
        """Check event classification, callback count, selected ID, and cleanup."""
        self.middleware.process_request(self.req, self.resp)
        assert len(self.events) == 1, f"expected one event, got {self.events!r}"
        event = self.events[0]
        outcome, trust, validator_calls, selected_id = self.expected
        assert (event.outcome, event.trust, event.header_name) == (
            outcome,
            trust,
            "X-Correlation-ID",
        ), f"unexpected event {event!r}"
        assert len(self.validator.calls) == validator_calls, (
            f"expected {validator_calls} validator calls, got {self.validator.calls!r}"
        )
        assert self.req.context.correlation_id == selected_id, (
            f"expected selected ID {selected_id!r}, got "
            f"{self.req.context.correlation_id!r}"
        )
        self.middleware.process_response(
            self.req,
            self.resp,
            resource=None,
            req_succeeded=True,
        )
        assert getattr(self.req.context, CORRELATION_ID_RESET_TOKEN_ATTR) is None, (
            "expected reset token cleanup"
        )


def _make_request(header: str | None) -> tuple[falcon.Request, falcon.Response]:
    """Build Falcon request and response objects for one generated header."""
    headers = None if header is None else {"X-Correlation-ID": header}
    environ = falcon.testing.create_environ(
        path="/test",
        headers=headers,
        remote_addr="127.0.0.1",
    )
    return falcon.Request(environ), falcon.Response()


def _expected_selection(
    incoming_header: str | None,
    source_trust: SourceTrust,
    validator_mode: str,
) -> _ExpectedSelection:
    """Return expected metrics and selected ID for one generated case."""
    if incoming_header is None or not incoming_header.strip():
        return (
            IncomingIDOutcome.missing,
            SourceTrust.not_evaluated,
            0,
            "generated-id",
        )
    if source_trust is SourceTrust.untrusted:
        return (
            IncomingIDOutcome.untrusted,
            SourceTrust.untrusted,
            0,
            "generated-id",
        )
    match validator_mode:
        case "raise":
            outcome = IncomingIDOutcome.rejected_validator_error
            selected_id = "generated-id"
        case "reject":
            outcome = IncomingIDOutcome.rejected_invalid
            selected_id = "generated-id"
        case _:
            outcome = IncomingIDOutcome.accepted
            selected_id = incoming_header.strip()
    return outcome, SourceTrust.trusted, 1, selected_id


def _make_selection_run(
    header: str | None,
    source_trust: SourceTrust,
    validator_mode: str,
) -> _SelectionRun:
    """Build middleware, request state, and expected result for a property case."""
    events: list[CorrelationIDSelectionEvent] = []
    validator = _CountingValidator(validator_mode)
    middleware = CorrelationIDMiddleware(
        generator=lambda: "generated-id",
        trusted_sources=(
            ["127.0.0.1"] if source_trust is SourceTrust.trusted else ["192.0.2.1"]
        ),
        validator=validator,
        metrics_recorder=events.append,
        echo_header_in_response=False,
    )
    req, resp = _make_request(header)
    expected = _expected_selection(
        req.get_header("X-Correlation-ID"),
        source_trust,
        validator_mode,
    )
    return _SelectionRun(middleware, req, resp, events, validator, expected)


@given(scenario=_scenario_values)
@settings(max_examples=60)
def test_selection_metrics_follow_header_trust_and_validator_inputs(
    scenario: tuple[str | None, SourceTrust, str],
) -> None:
    """Generated header, trust, and validator inputs produce matching events."""
    contextvars.copy_context().run(_make_selection_run(*scenario).exercise)
