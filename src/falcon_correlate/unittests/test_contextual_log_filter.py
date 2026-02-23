"""Unit tests for ContextualLogFilter."""

from __future__ import annotations

import contextvars
import io
import logging
import logging.config

from falcon_correlate import (
    ContextualLogFilter,
    correlation_id_var,
    user_id_var,
)


def _make_log_record(msg: str = "test message") -> logging.LogRecord:
    """Create a minimal LogRecord for testing."""
    return logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg=msg,
        args=None,
        exc_info=None,
    )


class TestContextualLogFilterIsLoggingFilter:
    """Tests for ContextualLogFilter class identity."""

    def test_is_logging_filter_subclass(self) -> None:
        """Verify ContextualLogFilter is a subclass of logging.Filter."""
        assert issubclass(ContextualLogFilter, logging.Filter)

    def test_can_be_instantiated(self) -> None:
        """Verify the filter can be instantiated with no arguments."""
        f = ContextualLogFilter()
        assert isinstance(f, logging.Filter)


class TestContextualLogFilterAttributeInjection:
    """Tests for attribute injection from context variables."""

    def test_injects_correlation_id_from_context(
        self, isolated_context: object
    ) -> None:
        """Verify filter injects correlation_id from context variable."""
        f = ContextualLogFilter()
        record = _make_log_record()

        def _inner() -> None:
            correlation_id_var.set("test-cid-123")
            f.filter(record)
            assert record.correlation_id == "test-cid-123"  # type: ignore[attr-defined]

        contextvars.copy_context().run(_inner)

    def test_injects_user_id_from_context(self, isolated_context: object) -> None:
        """Verify filter injects user_id from context variable."""
        f = ContextualLogFilter()
        record = _make_log_record()

        def _inner() -> None:
            user_id_var.set("test-uid-456")
            f.filter(record)
            assert record.user_id == "test-uid-456"  # type: ignore[attr-defined]

        contextvars.copy_context().run(_inner)

    def test_injects_both_attributes_simultaneously(
        self, isolated_context: object
    ) -> None:
        """Verify filter injects both attributes in a single call."""
        f = ContextualLogFilter()
        record = _make_log_record()

        def _inner() -> None:
            correlation_id_var.set("both-cid")
            user_id_var.set("both-uid")
            f.filter(record)
            assert record.correlation_id == "both-cid"  # type: ignore[attr-defined]
            assert record.user_id == "both-uid"  # type: ignore[attr-defined]

        contextvars.copy_context().run(_inner)


class TestContextualLogFilterPlaceholder:
    """Tests for placeholder values when context is empty."""

    def test_placeholder_for_correlation_id_when_not_set(self) -> None:
        """Verify placeholder used for correlation_id when not set."""
        f = ContextualLogFilter()
        record = _make_log_record()

        def _inner() -> None:
            f.filter(record)
            assert record.correlation_id == "-"  # type: ignore[attr-defined]

        contextvars.copy_context().run(_inner)

    def test_placeholder_for_user_id_when_not_set(self) -> None:
        """Verify placeholder used for user_id when not set."""
        f = ContextualLogFilter()
        record = _make_log_record()

        def _inner() -> None:
            f.filter(record)
            assert record.user_id == "-"  # type: ignore[attr-defined]

        contextvars.copy_context().run(_inner)

    def test_placeholder_for_both_when_not_set(self) -> None:
        """Verify placeholder used for both attributes when not set."""
        f = ContextualLogFilter()
        record = _make_log_record()

        def _inner() -> None:
            f.filter(record)
            assert record.correlation_id == "-"  # type: ignore[attr-defined]
            assert record.user_id == "-"  # type: ignore[attr-defined]

        contextvars.copy_context().run(_inner)


class TestContextualLogFilterReturnValue:
    """Tests for filter method return value."""

    def test_filter_returns_true(self) -> None:
        """Verify filter() returns True when context is empty."""
        f = ContextualLogFilter()
        record = _make_log_record()

        def _inner() -> None:
            result = f.filter(record)
            assert result is True

        contextvars.copy_context().run(_inner)

    def test_filter_returns_true_when_context_set(self) -> None:
        """Verify filter() returns True when context variables are set."""
        f = ContextualLogFilter()
        record = _make_log_record()

        def _inner() -> None:
            correlation_id_var.set("cid")
            user_id_var.set("uid")
            result = f.filter(record)
            assert result is True

        contextvars.copy_context().run(_inner)


class TestContextualLogFilterLoggingIntegration:
    """Tests for integration with standard logging configuration."""

    def test_filter_works_with_logger(self) -> None:
        """Verify filter enriches records emitted through a logger."""
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(
            logging.Formatter("[%(correlation_id)s][%(user_id)s] %(message)s")
        )
        handler.addFilter(ContextualLogFilter())

        test_logger = logging.getLogger("test_contextual_log_filter_integration")
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.INFO)

        def _inner() -> None:
            correlation_id_var.set("log-cid-001")
            user_id_var.set("log-uid-001")
            test_logger.info("hello from test")

        contextvars.copy_context().run(_inner)

        output = stream.getvalue()
        assert "[log-cid-001]" in output
        assert "[log-uid-001]" in output
        assert "hello from test" in output

        # Clean up to avoid polluting other tests.
        test_logger.removeHandler(handler)

    def test_filter_works_with_dict_config(self) -> None:
        """Verify filter works when configured via dictConfig."""
        config = {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {
                "contextual": {
                    "()": "falcon_correlate.ContextualLogFilter",
                },
            },
            "formatters": {
                "ctx": {
                    "format": ("[%(correlation_id)s][%(user_id)s] %(message)s"),
                },
            },
            "handlers": {
                "test_stream": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                    "formatter": "ctx",
                    "filters": ["contextual"],
                },
            },
            "loggers": {
                "test_dictconfig_logger": {
                    "handlers": ["test_stream"],
                    "level": "INFO",
                },
            },
        }
        logging.config.dictConfig(config)
        test_logger = logging.getLogger("test_dictconfig_logger")

        stream = io.StringIO()
        # Replace the stdout handler with our string stream for capture.
        for h in test_logger.handlers:
            h.stream = stream  # type: ignore[attr-defined]

        def _inner() -> None:
            correlation_id_var.set("dictcfg-cid")
            user_id_var.set("dictcfg-uid")
            test_logger.info("dictconfig test")

        contextvars.copy_context().run(_inner)

        output = stream.getvalue()
        assert "[dictcfg-cid]" in output
        assert "[dictcfg-uid]" in output

        # Clean up handlers to avoid polluting other tests.
        for h in list(test_logger.handlers):
            test_logger.removeHandler(h)


class TestContextualLogFilterExports:
    """Tests for ContextualLogFilter public API exports."""

    def test_contextual_log_filter_in_all(self) -> None:
        """Verify ContextualLogFilter is listed in __all__."""
        import falcon_correlate

        assert "ContextualLogFilter" in falcon_correlate.__all__

    def test_contextual_log_filter_importable_from_root(self) -> None:
        """Verify ContextualLogFilter can be imported from package root."""
        from falcon_correlate import ContextualLogFilter as Clf

        assert issubclass(Clf, logging.Filter)
