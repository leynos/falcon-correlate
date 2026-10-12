"""Tests for injecting context variable values into records.

Tests
-----
TestContextualLogFilterAttributeInjection
    Verify that context IDs reach log records.
"""

from __future__ import annotations

import typing as typ

import pytest

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import contextvars

    from falcon_correlate.unittests._contextual_log_filter_support import HasContextIDs

from falcon_correlate import ContextualLogFilter, correlation_id_var, user_id_var
from falcon_correlate.unittests._contextual_log_filter_support import make_log_record


class TestContextualLogFilterAttributeInjection:
    """Tests for attribute injection from context variables."""

    @pytest.mark.parametrize(
        ("context_var", "context_value", "attr_name"),
        [
            (correlation_id_var, "test-cid-123", "correlation_id"),
            (user_id_var, "test-uid-456", "user_id"),
        ],
    )
    def test_injects_attribute_from_context(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
        context_var: contextvars.ContextVar[str | None],
        context_value: str,
        attr_name: str,
    ) -> None:
        """Verify filter injects attributes from context variables."""
        f = ContextualLogFilter()
        record = make_log_record()

        def test_logic() -> None:
            """Exercise the isolated logging scenario."""
            context_var.set(context_value)
            f.filter(record)
            actual = getattr(record, attr_name)
            assert actual == context_value, (
                f"expected {attr_name}={context_value!r}, got {actual!r}"
            )

        isolated_context(test_logic)

    def test_injects_both_attributes_simultaneously(
        self, isolated_context: cabc.Callable[[cabc.Callable[[], None]], None]
    ) -> None:
        """Verify filter injects both attributes in a single call."""
        f = ContextualLogFilter()
        record = make_log_record()

        def test_logic() -> None:
            """Exercise the isolated logging scenario."""
            correlation_id_var.set("both-cid")
            user_id_var.set("both-uid")
            f.filter(record)
            rec = typ.cast("HasContextIDs", record)
            assert rec.correlation_id == "both-cid", (
                f"expected correlation_id='both-cid', got {rec.correlation_id!r}"
            )
            assert rec.user_id == "both-uid", (
                f"expected user_id='both-uid', got {rec.user_id!r}"
            )

        isolated_context(test_logic)
