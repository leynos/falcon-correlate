"""Shared structlog test helpers for unit and BDD test suites.

This module provides the ``inject_correlation_context`` processor
function used by both the colocated unit tests and the BDD step
definitions.  Centralising the implementation here avoids coupling
the BDD suite to the unit-test module and prevents divergence.

The processor mirrors the example documented in the users' guide.
"""

from __future__ import annotations

from falcon_correlate import correlation_id_var, user_id_var


def inject_correlation_context(
    logger: object,
    method_name: str,
    event_dict: dict[str, object],
) -> dict[str, object]:
    """Inject correlation ID and user ID into structlog event dict.

    This is the same processor function documented in the users' guide.
    It reads from ``falcon-correlate``'s context variables and injects
    them into the event dictionary using ``setdefault`` so that
    explicitly bound values are preserved.
    """
    event_dict.setdefault("correlation_id", correlation_id_var.get() or "-")
    event_dict.setdefault("user_id", user_id_var.get() or "-")
    return event_dict
