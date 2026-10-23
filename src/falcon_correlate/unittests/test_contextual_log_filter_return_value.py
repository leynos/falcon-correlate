"""Tests for the filter return value.

Tests
-----
TestContextualLogFilterReturnValue
    Verify filtering always accepts the record.
"""

from __future__ import annotations

import typing as typ

import pytest

if typ.TYPE_CHECKING:
    import collections.abc as cabc

from falcon_correlate import ContextualLogFilter, correlation_id_var, user_id_var
from falcon_correlate.unittests._contextual_log_filter_support import make_log_record


class TestContextualLogFilterReturnValue:
    """Tests for filter method return value."""

    @pytest.mark.parametrize(
        "populated",
        [
            False,
            True,
        ],
        ids=["empty_context", "populated_context"],
    )
    def test_filter_always_returns_true(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
        populated: bool,  # ruff: ignore[boolean-type-hint-positional-argument] -  bool param injected by pytest parametrize; remove when ruff supports parametrize-aware FBT001 exemption
    ) -> None:
        """Verify filter() always returns True regardless of context state."""
        f = ContextualLogFilter()
        record = make_log_record()

        def test_logic() -> None:
            """Exercise the isolated logging scenario."""
            if populated:
                correlation_id_var.set("cid")
                user_id_var.set("uid")
            result = f.filter(record)
            assert result is True, f"expected filter() to return True, got {result!r}"

        isolated_context(test_logic)
