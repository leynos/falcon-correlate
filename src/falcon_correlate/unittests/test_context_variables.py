"""Unit tests for context variable definitions."""

from __future__ import annotations

import contextvars

import pytest


class TestContextVariableDefinitions:
    """Tests for context variable existence, type, naming, and defaults."""

    def test_correlation_id_var_is_context_var(self) -> None:
        """Verify correlation_id_var is a ContextVar instance."""
        from falcon_correlate import correlation_id_var

        assert isinstance(correlation_id_var, contextvars.ContextVar)

    def test_user_id_var_is_context_var(self) -> None:
        """Verify user_id_var is a ContextVar instance."""
        from falcon_correlate import user_id_var

        assert isinstance(user_id_var, contextvars.ContextVar)

    def test_correlation_id_var_name(self) -> None:
        """Verify correlation_id_var has the expected name."""
        from falcon_correlate import correlation_id_var

        assert correlation_id_var.name == "correlation_id"

    def test_user_id_var_name(self) -> None:
        """Verify user_id_var has the expected name."""
        from falcon_correlate import user_id_var

        assert user_id_var.name == "user_id"

    def test_correlation_id_var_default_is_none(self) -> None:
        """Verify correlation_id_var defaults to None."""
        from falcon_correlate import correlation_id_var

        assert correlation_id_var.get() is None

    def test_user_id_var_default_is_none(self) -> None:
        """Verify user_id_var defaults to None."""
        from falcon_correlate import user_id_var

        assert user_id_var.get() is None


class TestContextVariableOperations:
    """Tests for context variable set, get, and reset operations."""

    @pytest.mark.parametrize(
        ("var_name", "test_value"),
        [
            ("correlation_id_var", "test-correlation-id"),
            ("user_id_var", "test-user-id"),
        ],
    )
    def test_context_var_set_and_get(self, var_name: str, test_value: str) -> None:
        """Verify context var set/get works and is context-isolated."""
        import falcon_correlate

        var: contextvars.ContextVar[str | None] = getattr(falcon_correlate, var_name)

        def _inner() -> None:
            token = var.set(test_value)
            assert var.get() == test_value
            var.reset(token)

        ctx = contextvars.copy_context()
        ctx.run(_inner)

        # Values set in the copied context must not leak into the outer context.
        assert var.get() is None

    @pytest.mark.parametrize(
        "var_name",
        ["correlation_id_var", "user_id_var"],
    )
    def test_context_var_reset_restores_default(self, var_name: str) -> None:
        """Verify resetting a context var restores None default."""
        import falcon_correlate

        var: contextvars.ContextVar[str | None] = getattr(falcon_correlate, var_name)

        def _inner() -> None:
            token = var.set("temporary-value")
            var.reset(token)
            assert var.get() is None

        ctx = contextvars.copy_context()
        ctx.run(_inner)


class TestContextVariableExports:
    """Tests for context variable public API exports."""

    def test_correlation_id_var_in_all(self) -> None:
        """Verify correlation_id_var is listed in __all__."""
        import falcon_correlate

        assert "correlation_id_var" in falcon_correlate.__all__

    def test_user_id_var_in_all(self) -> None:
        """Verify user_id_var is listed in __all__."""
        import falcon_correlate

        assert "user_id_var" in falcon_correlate.__all__

    def test_correlation_id_var_importable_from_root(self) -> None:
        """Verify correlation_id_var can be imported from package root."""
        from falcon_correlate import correlation_id_var

        assert isinstance(correlation_id_var, contextvars.ContextVar)

    def test_user_id_var_importable_from_root(self) -> None:
        """Verify user_id_var can be imported from package root."""
        from falcon_correlate import user_id_var

        assert isinstance(user_id_var, contextvars.ContextVar)
