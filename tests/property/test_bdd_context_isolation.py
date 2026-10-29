"""Property coverage for the shared BDD context isolation contract."""

from __future__ import annotations

import contextvars
from contextlib import nullcontext

import pytest
from hypothesis import given
from hypothesis import strategies as st

from falcon_correlate import correlation_id_var, user_id_var
from tests.bdd.conftest import isolated_context_variables


class _ScenarioError(Exception):
    """Represent a failing scenario."""


@given(
    ambient=st.tuples(st.one_of(st.none(), st.text()), st.one_of(st.none(), st.text())),
    writes=st.lists(
        st.tuples(st.one_of(st.none(), st.text()), st.one_of(st.none(), st.text())),
        max_size=10,
    ),
    fails=st.booleans(),
)
def test_bdd_context_restores_arbitrary_ambient_values(
    ambient: tuple[str | None, str | None],
    writes: list[tuple[str | None, str | None]],
    *,
    fails: bool,
) -> None:
    """Restore both ambient values after arbitrary writes and either exit path."""

    def run_scenario() -> None:
        """Exercise one generated scenario in its own context."""
        correlation_id_var.set(ambient[0])
        user_id_var.set(ambient[1])
        expected = pytest.raises(_ScenarioError) if fails else nullcontext()
        with expected, isolated_context_variables():
            assert correlation_id_var.get() is None, "correlation ID was not cleared"
            assert user_id_var.get() is None, "user ID was not cleared"
            for correlation_id, user_id in writes:
                correlation_id_var.set(correlation_id)
                user_id_var.set(user_id)
            if fails:
                raise _ScenarioError
        assert correlation_id_var.get() == ambient[0], "correlation ID was not restored"
        assert user_id_var.get() == ambient[1], "user ID was not restored"

    contextvars.copy_context().run(run_scenario)
