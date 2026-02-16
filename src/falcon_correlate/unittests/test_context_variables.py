"""Unit tests for context variable definitions."""

from __future__ import annotations

import contextvars


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

    def test_correlation_id_var_set_and_get(self) -> None:
        """Verify correlation_id_var can be set and retrieved."""
        from falcon_correlate import correlation_id_var

        def _inner() -> None:
            token = correlation_id_var.set("test-correlation-id")
            assert correlation_id_var.get() == "test-correlation-id"
            correlation_id_var.reset(token)

        ctx = contextvars.copy_context()
        ctx.run(_inner)

    def test_user_id_var_set_and_get(self) -> None:
        """Verify user_id_var can be set and retrieved."""
        from falcon_correlate import user_id_var

        def _inner() -> None:
            token = user_id_var.set("test-user-id")
            assert user_id_var.get() == "test-user-id"
            user_id_var.reset(token)

        ctx = contextvars.copy_context()
        ctx.run(_inner)

    def test_correlation_id_var_reset_restores_default(self) -> None:
        """Verify resetting correlation_id_var restores None default."""
        from falcon_correlate import correlation_id_var

        def _inner() -> None:
            token = correlation_id_var.set("temporary-value")
            correlation_id_var.reset(token)
            assert correlation_id_var.get() is None

        ctx = contextvars.copy_context()
        ctx.run(_inner)

    def test_user_id_var_reset_restores_default(self) -> None:
        """Verify resetting user_id_var restores None default."""
        from falcon_correlate import user_id_var

        def _inner() -> None:
            token = user_id_var.set("temporary-value")
            user_id_var.reset(token)
            assert user_id_var.get() is None

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
