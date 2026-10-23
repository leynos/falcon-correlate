"""Tests for ContextualLogFilter public API exports.

Tests
-----
TestContextualLogFilterExports
    Verify the filter is available from the package root.
"""

from __future__ import annotations

import logging


class TestContextualLogFilterExports:
    """Tests for ContextualLogFilter public API exports."""

    def test_contextual_log_filter_in_all(self) -> None:
        """Verify ContextualLogFilter is listed in __all__."""
        import falcon_correlate

        assert "ContextualLogFilter" in falcon_correlate.__all__, (
            "ContextualLogFilter is missing from falcon_correlate.__all__"
        )

    def test_contextual_log_filter_importable_from_root(self) -> None:
        """Verify ContextualLogFilter can be imported from package root."""
        from falcon_correlate import ContextualLogFilter as Clf

        assert issubclass(Clf, logging.Filter), (
            "ContextualLogFilter is not a subclass of logging.Filter"
        )
