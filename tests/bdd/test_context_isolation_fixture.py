"""Direct tests for the shared BDD context isolation contract.

The ``_reset_context_variables`` fixture discovered here is the same one every
BDD scenario uses, so these tests prove the shared behaviour rather than a
per-step-module copy.

Two surfaces are covered. The ``isolated_context_variables`` tests pin the
contract the fixture delegates to. The ``pytester`` tests prove pytest really
applies that fixture: they run a nested session that re-registers it, seed
ambient values first, and inspect the values after fixture teardown for both a
passing and a failing scenario. Coverage that only calls the context manager
cannot detect a removed ``autouse=True`` or a bypassed teardown.
"""

from __future__ import annotations

import pytest

from falcon_correlate import correlation_id_var, user_id_var
from tests.bdd.conftest import isolated_context_variables

pytest_plugins = ("pytester",)

_AMBIENT_CORRELATION_ID = "ambient-correlation-id"
_AMBIENT_USER_ID = "ambient-user-id"

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

_INNER_FAILING_BODY = """
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


def _seed_ambient_values() -> None:
    """Bind both public context variables to non-``None`` ambient values."""
    correlation_id_var.set(_AMBIENT_CORRELATION_ID)
    user_id_var.set(_AMBIENT_USER_ID)


def _assert_context_cleared() -> None:
    """Assert both public context variables read as ``None``."""
    correlation_failure = "expected the correlation ID context to be clear"
    user_failure = "expected the user ID context to be clear"
    assert correlation_id_var.get() is None, correlation_failure
    assert user_id_var.get() is None, user_failure


def _assert_ambient_values_restored() -> None:
    """Assert the values seeded by ``_seed_ambient_values`` came back."""
    correlation_failure = "expected the ambient correlation ID to be restored"
    user_failure = "expected the ambient user ID to be restored"
    assert correlation_id_var.get() == _AMBIENT_CORRELATION_ID, correlation_failure
    assert user_id_var.get() == _AMBIENT_USER_ID, user_failure


def _assert_fixture_applies_to_nested_session(
    pytester: pytest.Pytester,
    module_body: str,
    *,
    passed: int,
    failed: int = 0,
) -> None:
    """Seed ambient values, run a nested session, then check the aftermath."""
    _seed_ambient_values()
    pytester.makeconftest(_INNER_CONFTEST)
    pytester.makepyfile(test_inner=module_body)

    result = pytester.runpytest("-p", "no:cacheprovider", "-q")

    result.assert_outcomes(passed=passed, failed=failed)
    _assert_ambient_values_restored()


def test_scenario_starts_with_clean_context() -> None:
    """The autouse fixture clears both public context variables on entry."""
    correlation_failure = "expected correlation_id_var to be None on entry"
    user_failure = "expected user_id_var to be None on entry"
    assert correlation_id_var.get() is None, correlation_failure
    assert user_id_var.get() is None, user_failure


def test_isolated_context_variables_clears_entry_and_restores_ambient_values() -> None:
    """Values read as ``None`` inside the block; ambient values return after."""
    _seed_ambient_values()

    with isolated_context_variables():
        _assert_context_cleared()
        correlation_id_var.set("scenario-correlation-id")
        user_id_var.set("scenario-user-id")

    # Neither the in-block values nor a stale ambient value survives.
    _assert_ambient_values_restored()


def test_autouse_fixture_clears_then_restores_context(
    pytester: pytest.Pytester,
) -> None:
    """Fixture setup clears ambient values; teardown restores them.

    The inner body asserts ``None`` despite the outer scope seeding non-``None``
    ambient values before pytest ran the fixture, which proves setup cleared
    them rather than the outer values leaking through.
    """
    _assert_fixture_applies_to_nested_session(pytester, _INNER_CLEAN_BODY, passed=1)


def test_autouse_fixture_restores_context_after_failing_scenario_exit(
    pytester: pytest.Pytester,
) -> None:
    """Teardown runs after a failing scenario, so the next one starts clean."""
    _assert_fixture_applies_to_nested_session(
        pytester, _INNER_FAILING_BODY, passed=1, failed=1
    )


def test_isolated_context_variables_restores_ambient_values_after_exception() -> None:
    """Ambient values return and the block's exception still propagates."""
    _seed_ambient_values()

    with pytest.raises(_ScenarioFailedError), isolated_context_variables():
        _seed_user_id_and_fail()

    _assert_ambient_values_restored()
