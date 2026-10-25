"""Bounded selection events for pluggable correlation ID metrics.

The middleware reports the outcome and source trust classification to a
caller-provided recorder. Event fields are bounded labels and exclude request
values.
"""

from __future__ import annotations

import collections.abc as cabc
import dataclasses
import enum


def _bounded_header_name(header_name: str) -> str:
    """Map configured headers into a finite label set."""
    match header_name.casefold():
        case "x-correlation-id":
            return "X-Correlation-ID"
        case "x-request-id":
            return "X-Request-ID"
        case _:
            return "other"


class IncomingIDOutcome(enum.StrEnum):
    """Selection outcome for an incoming correlation ID header."""

    missing = "missing"
    """No non-blank incoming correlation ID was supplied."""

    untrusted = "untrusted"
    """An incoming ID was supplied by a source outside configured trust."""

    accepted = "accepted"
    """The incoming ID came from a trusted source and passed validation."""

    rejected_invalid = "rejected_invalid"
    """The incoming ID failed the configured validator."""

    rejected_validator_error = "rejected_validator_error"
    """The validator or its result raised during validation."""


class SourceTrust(enum.StrEnum):
    """Trust evaluation associated with an incoming ID selection."""

    trusted = "trusted"
    """The request source matched a configured trusted network."""

    untrusted = "untrusted"
    """The request source did not match a configured trusted network."""

    not_evaluated = "not_evaluated"
    """No non-blank incoming ID was present to evaluate."""


@dataclasses.dataclass(frozen=True, slots=True)
class CorrelationIDSelectionEvent:
    """Immutable, low-cardinality result of selecting a request correlation ID.

    Attributes
    ----------
    outcome : IncomingIDOutcome
        The outcome of processing the incoming header.
    trust : SourceTrust
        The request source's trust classification.
    header_name : str
        The configured header name mapped to an allowlisted label. Unlisted
        names map to ``"other"``.

    Notes
    -----
    The event omits the incoming ID and remote address. ``header_name`` is
    canonicalized to ``"X-Correlation-ID"`` or ``"X-Request-ID"``; all other
    configured names map to ``"other"``. Together with the enums, the event
    therefore provides finite metric labels.
    """

    outcome: IncomingIDOutcome
    trust: SourceTrust
    header_name: str


type MetricsRecorder = cabc.Callable[[CorrelationIDSelectionEvent], None]
"""Synchronous callback that records one correlation ID selection event.

The callback must be quick and non-blocking because ASGI invokes it on the
event loop. Exceptions are logged and ignored so metrics cannot change request
behaviour.
"""


__all__ = [
    "CorrelationIDSelectionEvent",
    "IncomingIDOutcome",
    "MetricsRecorder",
    "SourceTrust",
]
