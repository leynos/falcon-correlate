"""Tests for ContextualLogFilter class identity.

Tests
-----
TestContextualLogFilterIsLoggingFilter
    Verify the filter class relationship and construction.
"""

from __future__ import annotations

import logging

from falcon_correlate import ContextualLogFilter


class TestContextualLogFilterIsLoggingFilter:
    """Tests for ContextualLogFilter class identity."""

    def test_is_logging_filter_subclass(self) -> None:
        """Verify ContextualLogFilter is a subclass of logging.Filter."""
        assert issubclass(ContextualLogFilter, logging.Filter), (
            "ContextualLogFilter should be a subclass of logging.Filter"
        )

    def test_can_be_instantiated(self) -> None:
        """Verify the filter can be instantiated with no arguments."""
        f = ContextualLogFilter()
        assert isinstance(f, logging.Filter), (
            "instantiated object should be an instance of logging.Filter"
        )
