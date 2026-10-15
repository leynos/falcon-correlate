"""Private, dependency-free outcomes for explicit Celery configuration."""

from __future__ import annotations

import logging
import threading
import typing as typ
import weakref

if typ.TYPE_CHECKING:
    import collections.abc as cabc

type _SignalState = typ.Literal[
    "connected",
    "celery_signals_unavailable",
    "signal_missing",
    "connect_not_callable",
    "receiver_rejected",
]
type _PublisherContextState = typ.Literal[
    "configured", "send_task_unavailable", "assignment_rejected"
]
type _BackendRpcVerdict = typ.Literal["rpc", "non_rpc", "unknown"]
type _ConfigurationOutcome = tuple[
    _SignalState, _SignalState, _SignalState, _PublisherContextState, _BackendRpcVerdict
]

_logger = logging.getLogger("falcon_correlate.celery")
_reported_outcomes: weakref.WeakKeyDictionary[object, set[_ConfigurationOutcome]] = (
    weakref.WeakKeyDictionary()
)
_reported_outcomes_lock = threading.Lock()


def _safe_connect_signal(
    signal_module: object,
    signal_name: str,
    handler: cabc.Callable[..., object],
    dispatch_uid: str,
) -> _SignalState:
    """Return a bounded outcome without logging optional connection failures."""
    signal = getattr(signal_module, signal_name, None)
    if signal is None:
        return "signal_missing"

    connect = getattr(signal, "connect", None)
    if not callable(connect):
        return "connect_not_callable"

    try:
        # Celery returns the receiver, rather than a success flag. Stable UIDs
        # make an already-connected receiver a successful outcome as well.
        connect(handler, dispatch_uid=dispatch_uid, weak=False)
    except ValueError:
        return "receiver_rejected"
    return "connected"


def _report_configuration_outcome(
    app: object,
    signal_states: tuple[_SignalState, _SignalState, _SignalState],
    publisher_context_state: _PublisherContextState,
    *,
    backend_uses_rpc: bool | None,
) -> None:
    """Report each bounded configuration outcome once during an app's lifetime."""
    backend_rpc_verdict: _BackendRpcVerdict
    if backend_uses_rpc is None:
        backend_rpc_verdict = "unknown"
    elif backend_uses_rpc:
        backend_rpc_verdict = "rpc"
    else:
        backend_rpc_verdict = "non_rpc"
    outcome: _ConfigurationOutcome = (
        *signal_states,
        publisher_context_state,
        backend_rpc_verdict,
    )
    with _reported_outcomes_lock:
        reported = _reported_outcomes.setdefault(app, set())
        if outcome in reported:
            return
        reported.add(outcome)

    # Release the state lock before application-owned logging handlers run.
    is_active = (
        all(state == "connected" for state in signal_states)
        and publisher_context_state == "configured"
    )
    _logger.log(
        logging.INFO if is_active else logging.WARNING,
        "Celery correlation configuration active."
        if is_active
        else "Celery correlation configuration incomplete.",
        extra={
            "operation": "configure_celery_correlation",
            "registration_state": "active" if is_active else "incomplete",
            "before_task_publish_state": signal_states[0],
            "task_prerun_state": signal_states[1],
            "task_postrun_state": signal_states[2],
            "publisher_context_state": publisher_context_state,
            "backend_rpc_verdict": backend_rpc_verdict,
        },
    )
