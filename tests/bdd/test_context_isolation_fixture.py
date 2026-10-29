"""Direct tests for the shared BDD context isolation contract.

The ``_reset_context_variables`` fixture discovered here is the same one every
BDD scenario uses, so these tests prove the shared behaviour rather than a
per-step-module copy.

Both the context manager and pytest's execution of the autouse fixture are
covered. The context manager tests describe the contract, and the ``pytester``
tests prove pytest actually applies it: they re-register the shared fixture in
a nested session, seed ambient values before fixture setup, and inspect the
values after fixture teardown for both normal and failing inner tests.
"""

from __future__ import annotations

import typing as typ

import pytest

if typ.TYPE_CHECKING:
    import collections.abc as cabc

from falcon_correlate import correlation_id_var, user_id_var
from tests.bdd.conftest import isolated_context_variables

pytest_plugins = ("pytester",)

# Re-registering the shared fixture under its own name is what makes the nested
# session apply it. The fixture is autouse, so importing it is enough; the
# explicit ``__all__`` entry documents the intent and keeps linters quiet.
_INNER_CONFTEST = """
from tests.bdd.conftest import _reset_context_variables

__all__ = ["_reset_context_variables"]
"""

_INNER_CLEAN_BODY = """
from falcon_correlate import correlation_id_var, user_id_var


def test_body():
    assert correlation_id_var.get() is None
    assert user_id_var.get() is None
"""

_INNER_FAILING_SCENARIO = """
from falcon_correlate import correlation_id_var, user_id_var


def test_seeds_context_then_fails():
    correlation_id_var.set("leaked-correlation-id")
    user_id_var.set("leaked-user-id")
    raise AssertionError("deliberate scenario failure")


def test_next_test_starts_clean():
    assert correlation_id_var.get() is None
    assert user_id_var.get() is None
"""


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


def test_autouse_fixture_clears_then_restores_context(
    pytester: pytest.Pytester,
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
) -> None:
    """Setup clears ambient values for the inner test; teardown restores them.

    The inner test body asserts both variables read as ``None`` even though the
    outer scope seeded non-``None`` ambient values before pytest ran the
    fixture, which is what proves setup clearing rather than outer leakage.
    """
    pytester.makeconftest(_INNER_CONFTEST)
    pytester.makepyfile(test_inner=_INNER_CLEAN_BODY)

    def scenario() -> None:
        correlation_id_var.set("ambient-correlation-id")
        user_id_var.set("ambient-user-id")

        result = pytester.runpytest("-p", "no:cacheprovider", "-q")

        result.assert_outcomes(passed=1)
        correlation_failure = "expected teardown to restore the ambient correlation ID"
        user_failure = "expected teardown to restore the ambient user ID"
        assert correlation_id_var.get() == "ambient-correlation-id", correlation_failure
        assert user_id_var.get() == "ambient-user-id", user_failure

    isolated_context(scenario)


def test_autouse_fixture_restores_context_after_failing_scenario_exit(
    pytester: pytest.Pytester,
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
) -> None:
    """Teardown runs after a failing inner test, so the next one is clean."""
    pytester.makeconftest(_INNER_CONFTEST)
    pytester.makepyfile(test_inner=_INNER_FAILING_SCENARIO)

    def scenario() -> None:
        correlation_id_var.set("ambient-correlation-id")
        user_id_var.set("ambient-user-id")

        result = pytester.runpytest("-p", "no:cacheprovider", "-q")

        # The failing test is followed by a clean one, which proves teardown ran.
        result.assert_outcomes(passed=1, failed=1)
        correlation_failure = "expected teardown to restore the ambient correlation ID"
        user_failure = "expected teardown to restore the ambient user ID"
        assert correlation_id_var.get() == "ambient-correlation-id", correlation_failure
        assert user_id_var.get() == "ambient-user-id", user_failure

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
