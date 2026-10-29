"""Direct tests for the shared BDD context isolation contract.

The ``_reset_context_variables`` fixture discovered here is the same one every
BDD scenario uses, so these tests prove the shared behaviour rather than a
per-step-module copy.
"""

from __future__ import annotations

import typing as typ

import pytest

if typ.TYPE_CHECKING:
    import collections.abc as cabc

from falcon_correlate import correlation_id_var, user_id_var
from tests.bdd.conftest import isolated_context_variables


class _ScenarioFailedError(RuntimeError):
    """Raised by the isolation test to exercise the exception path."""


def _seed_user_id_and_fail() -> None:
    """Seed a scenario user ID, then fail the enclosing block."""
    user_id_var.set("scenario-user-id")
    raise _ScenarioFailedError


def test_scenario_starts_with_clean_context() -> None:
    """The autouse fixture clears both public context variables on entry."""
    correlation_failure = "expected correlation_id_var to be None on entry"
    user_failure = "expected user_id_var to be None on entry"
    assert correlation_id_var.get() is None, correlation_failure
    assert user_id_var.get() is None, user_failure


def test_isolated_context_variables_binds_none_on_entry(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
) -> None:
    """Ambient values are replaced by ``None`` for the duration of the block."""

    def scenario() -> None:
        correlation_id_var.set("ambient-correlation-id")
        user_id_var.set("ambient-user-id")

        with isolated_context_variables():
            correlation_failure = "expected the block to start without a correlation ID"
            user_failure = "expected the block to start without a user ID"
            assert correlation_id_var.get() is None, correlation_failure
            assert user_id_var.get() is None, user_failure

    isolated_context(scenario)


def test_isolated_context_variables_discards_values_set_inside(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
) -> None:
    """Values written inside the block do not outlive it."""

    def scenario() -> None:
        with isolated_context_variables():
            correlation_id_var.set("scenario-correlation-id")
            user_id_var.set("scenario-user-id")

        correlation_failure = "expected the scenario correlation ID to be discarded"
        user_failure = "expected the scenario user ID to be discarded"
        assert correlation_id_var.get() is None, correlation_failure
        assert user_id_var.get() is None, user_failure

    isolated_context(scenario)


def test_isolated_context_variables_restores_ambient_values(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
) -> None:
    """Ambient values return once the block exits normally."""

    def scenario() -> None:
        correlation_id_var.set("ambient-correlation-id")
        user_id_var.set("ambient-user-id")

        with isolated_context_variables():
            correlation_id_var.set("scenario-correlation-id")

        correlation_failure = "expected the ambient correlation ID to be restored"
        user_failure = "expected the ambient user ID to be restored"
        assert correlation_id_var.get() == "ambient-correlation-id", correlation_failure
        assert user_id_var.get() == "ambient-user-id", user_failure

    isolated_context(scenario)


def test_isolated_context_variables_restores_ambient_values_after_exception(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
) -> None:
    """Ambient values return and the block's exception still propagates."""

    def scenario() -> None:
        correlation_id_var.set("ambient-correlation-id")
        user_id_var.set("ambient-user-id")

        with pytest.raises(_ScenarioFailedError), isolated_context_variables():
            _seed_user_id_and_fail()

        correlation_failure = "expected the ambient correlation ID to be restored"
        user_failure = "expected the ambient user ID to be restored"
        assert correlation_id_var.get() == "ambient-correlation-id", correlation_failure
        assert user_id_var.get() == "ambient-user-id", user_failure

    isolated_context(scenario)
