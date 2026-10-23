"""Regression tests for selection metric validation classification."""

from __future__ import annotations

import typing as typ

from falcon_correlate import (
    CorrelationIDMiddleware,
    IncomingIDOutcome,
    SourceTrust,
    correlation_id_var,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    import falcon


class _FalseResult:
    """A falsey validator result that rejects repeated truthiness checks."""

    def __init__(self) -> None:
        """Initialise the truthiness call counter."""
        self.calls = 0

    def __bool__(self) -> bool:
        """Return false once, then fail if classification coerces twice."""
        self.calls += 1
        if self.calls > 1:
            msg = "validator result was coerced more than once"
            raise AssertionError(msg)
        return False


def test_rejected_result_is_coerced_once(
    request_response_factory: cabc.Callable[
        ..., tuple[falcon.Request, falcon.Response]
    ],
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
) -> None:
    """Classify one falsey validator result without repeating its coercion."""
    result = _FalseResult()
    events = []

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
