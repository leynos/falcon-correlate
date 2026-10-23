"""Tests for placeholder values when context variables are unset.

Tests
-----
TestContextualLogFilterPlaceholder
    Verify the filter placeholder cases.
"""

from __future__ import annotations

import typing as typ

import pytest

if typ.TYPE_CHECKING:
    import collections.abc as cabc

from falcon_correlate import ContextualLogFilter, correlation_id_var, user_id_var
from falcon_correlate.unittests._contextual_log_filter_support import make_log_record


class TestContextualLogFilterPlaceholder:
    """Tests for placeholder values when context is empty."""

    @pytest.mark.parametrize(
        "check_attrs",
        [
            ("correlation_id",),
            ("user_id",),
            ("correlation_id", "user_id"),
        ],
        ids=["correlation_id_only", "user_id_only", "both_attrs"],
    )
    def test_placeholder_when_context_not_set(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
        check_attrs: tuple[str, ...],
    ) -> None:
        """Verify placeholder used for attributes when context not set."""
        f = ContextualLogFilter()
        record = make_log_record()

        def test_logic() -> None:
            """Exercise the isolated logging scenario."""
            f.filter(record)
            for attr in check_attrs:
                actual = getattr(record, attr)
                assert actual == "-", f"expected {attr}='-', got {actual!r}"

        isolated_context(test_logic)

    @pytest.mark.parametrize(
        ("set_correlation", "set_user", "check_attrs"),
        [
            (True, False, ("correlation_id",)),
            (False, True, ("user_id",)),
            (True, True, ("correlation_id", "user_id")),
        ],
        ids=["correlation_id_none", "user_id_none", "both_none"],
    )
    def test_placeholder_when_context_explicit_none(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
        set_correlation: bool,  # ruff: ignore[boolean-type-hint-positional-argument] -  bool param injected by pytest parametrize; remove when ruff supports parametrize-aware FBT001 exemption
        set_user: bool,  # ruff: ignore[boolean-type-hint-positional-argument] -  bool param injected by pytest parametrize; remove when ruff supports parametrize-aware FBT001 exemption
        check_attrs: tuple[str, ...],
    ) -> None:
        """Verify placeholder used when context vars are explicitly set to None."""
        f = ContextualLogFilter()
        record = make_log_record()

        def test_logic() -> None:
            """Exercise the isolated logging scenario."""
            if set_correlation:
                correlation_id_var.set(None)
            if set_user:
                user_id_var.set(None)

            f.filter(record)
            for attr in check_attrs:
                actual = getattr(record, attr)
                assert actual == "-", f"expected {attr}='-', got {actual!r}"

        isolated_context(test_logic)
