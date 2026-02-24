"""Unit tests for ContextualLogFilter."""

from __future__ import annotations

import io
import logging
import logging.config
import typing as typ

import pytest

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import contextvars

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
        record = _make_log_record()

        def test_logic() -> None:
            context_var.set(context_value)
            f.filter(record)
            assert getattr(record, attr_name) == context_value

        isolated_context(test_logic)

    def test_injects_both_attributes_simultaneously(
        self, isolated_context: cabc.Callable[[cabc.Callable[[], None]], None]
    ) -> None:
        """Verify filter injects both attributes in a single call."""
        f = ContextualLogFilter()
        record = _make_log_record()

        def test_logic() -> None:
            correlation_id_var.set("both-cid")
            user_id_var.set("both-uid")
            f.filter(record)
            assert record.correlation_id == "both-cid"  # type: ignore[attr-defined]
            assert record.user_id == "both-uid"  # type: ignore[attr-defined]

        isolated_context(test_logic)


class TestContextualLogFilterPlaceholder:
    """Tests for placeholder values when context is empty."""

    @pytest.mark.parametrize(
        "check_attrs",
        [
            ["correlation_id"],
            ["user_id"],
            ["correlation_id", "user_id"],
        ],
        ids=["correlation_id_only", "user_id_only", "both_attrs"],
    )
    def test_placeholder_when_context_not_set(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
        check_attrs: list[str],
    ) -> None:
        """Verify placeholder used for attributes when context not set."""
        f = ContextualLogFilter()
        record = _make_log_record()

        def test_logic() -> None:
            f.filter(record)
            for attr in check_attrs:
                assert getattr(record, attr) == "-"

        isolated_context(test_logic)

    @pytest.mark.parametrize(
        ("set_correlation", "set_user", "check_attrs"),
        [
            ("correlation_id", "", ["correlation_id"]),
            ("", "user_id", ["user_id"]),
            ("correlation_id", "user_id", ["correlation_id", "user_id"]),
        ],
        ids=["correlation_id_none", "user_id_none", "both_none"],
    )
    def test_placeholder_when_context_explicit_none(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
        set_correlation: str,
        set_user: str,
        check_attrs: list[str],
    ) -> None:
        """Verify placeholder used when context vars are explicitly set to None."""
        f = ContextualLogFilter()
        record = _make_log_record()

        def test_logic() -> None:
            if set_correlation:
                correlation_id_var.set(None)
            if set_user:
                user_id_var.set(None)

            f.filter(record)
            for attr in check_attrs:
                assert getattr(record, attr) == "-"

        isolated_context(test_logic)


class TestContextualLogFilterReturnValue:
    """Tests for filter method return value."""

    @pytest.mark.parametrize(
        "setup_context",
        [
            "empty",
            "populated",
        ],
        ids=["empty_context", "populated_context"],
    )
    def test_filter_always_returns_true(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
        setup_context: str,
    ) -> None:
        """Verify filter() always returns True regardless of context state."""
        f = ContextualLogFilter()
        record = _make_log_record()

        def test_logic() -> None:
            if setup_context == "populated":
                correlation_id_var.set("cid")
                user_id_var.set("uid")
            result = f.filter(record)
            assert result is True

        isolated_context(test_logic)


class TestContextualLogFilterPreservesExistingAttributes:
    """Tests for preserving pre-existing record attributes."""

    def test_preserves_existing_correlation_id(
        self, isolated_context: cabc.Callable[[cabc.Callable[[], None]], None]
    ) -> None:
        """Verify filter does not overwrite a pre-existing correlation_id."""
        f = ContextualLogFilter()
        record = _make_log_record()
        record.correlation_id = "caller-cid"

        def test_logic() -> None:
            correlation_id_var.set("contextvar-cid")
            f.filter(record)
            assert record.correlation_id == "caller-cid"  # type: ignore[attr-defined]

        isolated_context(test_logic)

    def test_preserves_existing_user_id(
        self, isolated_context: cabc.Callable[[cabc.Callable[[], None]], None]
    ) -> None:
        """Verify filter does not overwrite a pre-existing user_id."""
        f = ContextualLogFilter()
        record = _make_log_record()
        record.user_id = "caller-uid"

        def test_logic() -> None:
            user_id_var.set("contextvar-uid")
            f.filter(record)
            assert record.user_id == "caller-uid"  # type: ignore[attr-defined]

        isolated_context(test_logic)

    def test_preserves_when_contextvar_unset(
        self, isolated_context: cabc.Callable[[cabc.Callable[[], None]], None]
    ) -> None:
        """Verify caller-provided ID survives even when contextvar is unset."""
        f = ContextualLogFilter()
        record = _make_log_record()
        record.correlation_id = "explicit-cid"
        record.user_id = "explicit-uid"

        def test_logic() -> None:
            f.filter(record)
            assert record.correlation_id == "explicit-cid"  # type: ignore[attr-defined]
            assert record.user_id == "explicit-uid"  # type: ignore[attr-defined]

        isolated_context(test_logic)

    def test_fills_missing_attribute_alongside_existing(
        self, isolated_context: cabc.Callable[[cabc.Callable[[], None]], None]
    ) -> None:
        """Verify filter fills one attr from contextvar while preserving the other."""
        f = ContextualLogFilter()
        record = _make_log_record()
        record.correlation_id = "caller-cid"

        def test_logic() -> None:
            user_id_var.set("contextvar-uid")
            f.filter(record)
            assert record.correlation_id == "caller-cid"  # type: ignore[attr-defined]
            assert record.user_id == "contextvar-uid"  # type: ignore[attr-defined]

        isolated_context(test_logic)


class TestContextualLogFilterLoggingIntegration:
    """Tests for integration with standard logging configuration."""

    def test_filter_works_with_logger(
        self, isolated_context: cabc.Callable[[cabc.Callable[[], None]], None]
    ) -> None:
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

        def test_logic() -> None:
            correlation_id_var.set("log-cid-001")
            user_id_var.set("log-uid-001")
            test_logger.info("hello from test")

        isolated_context(test_logic)

        output = stream.getvalue()
        assert "[log-cid-001]" in output
        assert "[log-uid-001]" in output
        assert "hello from test" in output

        # Clean up to avoid polluting other tests.
        test_logger.removeHandler(handler)

    def test_filter_works_with_dict_config(
        self, isolated_context: cabc.Callable[[cabc.Callable[[], None]], None]
    ) -> None:
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

        def test_logic() -> None:
            correlation_id_var.set("dictcfg-cid")
            user_id_var.set("dictcfg-uid")
            test_logger.info("dictconfig test")

        isolated_context(test_logic)

        output = stream.getvalue()
        assert "[dictcfg-cid]" in output
        assert "[dictcfg-uid]" in output

        # Clean up handlers to avoid polluting other tests.
        for h in list(test_logger.handlers):
            test_logger.removeHandler(h)

    def test_extra_kwarg_preserved_over_contextvar(
        self, isolated_context: cabc.Callable[[cabc.Callable[[], None]], None]
    ) -> None:
        """Verify extra= correlation_id is preserved when logging through a logger."""
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(
            logging.Formatter("[%(correlation_id)s][%(user_id)s] %(message)s")
        )
        handler.addFilter(ContextualLogFilter())

        test_logger = logging.getLogger("test_contextual_extra_preserved")
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.INFO)

        def test_logic() -> None:
            correlation_id_var.set("contextvar-cid")
            user_id_var.set("contextvar-uid")
            test_logger.info(
                "background job",
                extra={"correlation_id": "explicit-cid"},
            )

        isolated_context(test_logic)

        output = stream.getvalue()
        assert "[explicit-cid]" in output
        assert "[contextvar-uid]" in output

        test_logger.removeHandler(handler)


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
