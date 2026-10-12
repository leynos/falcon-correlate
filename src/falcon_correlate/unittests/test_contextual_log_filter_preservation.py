"""Tests for preserving existing log record attributes.

Tests
-----
PreservationTestCase
    Hold an attribute preservation scenario.
TestContextualLogFilterPreservesExistingAttributes
    Verify caller-supplied attributes survive filtering.
"""

from __future__ import annotations

import dataclasses
import typing as typ

import pytest

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import contextvars

    from falcon_correlate.unittests._contextual_log_filter_support import HasContextIDs

from falcon_correlate import ContextualLogFilter, correlation_id_var, user_id_var
from falcon_correlate.unittests._contextual_log_filter_support import (
    make_log_record,
)


@dataclasses.dataclass(slots=True, frozen=True)
class PreservationTestCase:
    """Encapsulates parameters for attribute preservation tests."""

    context_var: contextvars.ContextVar[str | None]
    attr_name: str
    existing_value: str
    contextvar_value: str


@pytest.fixture
def preservation_case(request: pytest.FixtureRequest) -> PreservationTestCase:
    """Fixture to receive parameterized PreservationTestCase instances.

    Parameters
    ----------
    request : pytest.FixtureRequest
        Fixture request supplying the parameterised ``PreservationTestCase``
        through ``request.param``.

    Returns
    -------
    PreservationTestCase
        The parameterized case for the current attribute-preservation scenario.

    """
    return request.param


class TestContextualLogFilterPreservesExistingAttributes:
    """Tests for preserving pre-existing record attributes."""

    @pytest.mark.parametrize(
        "preservation_case",
        [
            PreservationTestCase(
                context_var=correlation_id_var,
                attr_name="correlation_id",
                existing_value="caller-cid",
                contextvar_value="contextvar-cid",
            ),
            PreservationTestCase(
                context_var=user_id_var,
                attr_name="user_id",
                existing_value="caller-uid",
                contextvar_value="contextvar-uid",
            ),
        ],
        ids=["correlation_id", "user_id"],
        indirect=True,
    )
    def test_preserves_existing_attribute(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
        preservation_case: PreservationTestCase,
    ) -> None:
        """Verify filter does not overwrite a pre-existing attribute."""
        f = ContextualLogFilter()
        record = make_log_record()
        setattr(record, preservation_case.attr_name, preservation_case.existing_value)

        def test_logic() -> None:
            """Exercise the isolated logging scenario."""
            preservation_case.context_var.set(preservation_case.contextvar_value)
            f.filter(record)
            actual = getattr(record, preservation_case.attr_name)
            expected = preservation_case.existing_value
            assert actual == expected, (
                f"expected {preservation_case.attr_name}={expected!r}, got {actual!r}"
            )

        isolated_context(test_logic)

    def test_preserves_when_contextvar_unset(
        self, isolated_context: cabc.Callable[[cabc.Callable[[], None]], None]
    ) -> None:
        """Verify caller-provided ID survives even when contextvar is unset."""
        f = ContextualLogFilter()
        record = make_log_record()
        record.correlation_id = "explicit-cid"
        record.user_id = "explicit-uid"

        def test_logic() -> None:
            """Exercise the isolated logging scenario."""
            f.filter(record)
            rec = typ.cast("HasContextIDs", record)
            assert rec.correlation_id == "explicit-cid", (
                f"expected correlation_id='explicit-cid', got {rec.correlation_id!r}"
            )
            assert rec.user_id == "explicit-uid", (
                f"expected user_id='explicit-uid', got {rec.user_id!r}"
            )

        isolated_context(test_logic)

    def test_fills_missing_attribute_alongside_existing(
        self, isolated_context: cabc.Callable[[cabc.Callable[[], None]], None]
    ) -> None:
        """Verify filter fills one attr from contextvar while preserving the other."""
        f = ContextualLogFilter()
        record = make_log_record()
        record.correlation_id = "caller-cid"

        def test_logic() -> None:
            """Exercise the isolated logging scenario."""
            user_id_var.set("contextvar-uid")
            f.filter(record)
            rec = typ.cast("HasContextIDs", record)
            assert rec.correlation_id == "caller-cid", (
                f"expected correlation_id='caller-cid', got {rec.correlation_id!r}"
            )
            assert rec.user_id == "contextvar-uid", (
                f"expected user_id='contextvar-uid', got {rec.user_id!r}"
            )

        isolated_context(test_logic)
