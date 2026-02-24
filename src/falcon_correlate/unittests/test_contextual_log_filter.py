"""Unit tests for ContextualLogFilter."""

from __future__ import annotations

import dataclasses
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


class _HasCorrelationID(typ.Protocol):
    correlation_id: str


class _HasUserID(typ.Protocol):
    user_id: str


class _HasContextIDs(_HasCorrelationID, _HasUserID, typ.Protocol):
    """LogRecord enriched by ContextualLogFilter with both IDs."""


@dataclasses.dataclass(frozen=True)
class PreservationTestCase:
    """Encapsulates parameters for attribute preservation tests."""

    context_var: contextvars.ContextVar[str | None]
    attr_name: str
    existing_value: str
    contextvar_value: str


@pytest.fixture
def preservation_case(request: pytest.FixtureRequest) -> PreservationTestCase:
    """Fixture to receive parametrised PreservationTestCase instances."""
    return request.param


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
        assert issubclass(ContextualLogFilter, logging.Filter), (
            "ContextualLogFilter should be a subclass of logging.Filter"
        )

    def test_can_be_instantiated(self) -> None:
        """Verify the filter can be instantiated with no arguments."""
        f = ContextualLogFilter()
        assert isinstance(f, logging.Filter), (
            "instantiated object should be an instance of logging.Filter"
        )


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
        record = _make_log_record()

        def test_logic() -> None:
            correlation_id_var.set("both-cid")
            user_id_var.set("both-uid")
            f.filter(record)
            rec = typ.cast("_HasContextIDs", record)
            assert rec.correlation_id == "both-cid", (
                f"expected correlation_id='both-cid', got {rec.correlation_id!r}"
            )
            assert rec.user_id == "both-uid", (
                f"expected user_id='both-uid', got {rec.user_id!r}"
            )

        isolated_context(test_logic)


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
        record = _make_log_record()

        def test_logic() -> None:
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
        set_correlation: bool,  # noqa: FBT001 — pytest parametrize injection
        set_user: bool,  # noqa: FBT001 — pytest parametrize injection
        check_attrs: tuple[str, ...],
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
                actual = getattr(record, attr)
                assert actual == "-", f"expected {attr}='-', got {actual!r}"

        isolated_context(test_logic)


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
        populated: bool,  # noqa: FBT001 — pytest parametrize injection
    ) -> None:
        """Verify filter() always returns True regardless of context state."""
        f = ContextualLogFilter()
        record = _make_log_record()

        def test_logic() -> None:
            if populated:
                correlation_id_var.set("cid")
                user_id_var.set("uid")
            result = f.filter(record)
            assert result is True, f"expected filter() to return True, got {result!r}"

        isolated_context(test_logic)


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
        record = _make_log_record()
        setattr(record, preservation_case.attr_name, preservation_case.existing_value)

        def test_logic() -> None:
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
        record = _make_log_record()
        record.correlation_id = "explicit-cid"
        record.user_id = "explicit-uid"

        def test_logic() -> None:
            f.filter(record)
            rec = typ.cast("_HasContextIDs", record)
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
        record = _make_log_record()
        record.correlation_id = "caller-cid"

        def test_logic() -> None:
            user_id_var.set("contextvar-uid")
            f.filter(record)
            rec = typ.cast("_HasContextIDs", record)
            assert rec.correlation_id == "caller-cid", (
                f"expected correlation_id='caller-cid', got {rec.correlation_id!r}"
            )
            assert rec.user_id == "contextvar-uid", (
                f"expected user_id='contextvar-uid', got {rec.user_id!r}"
            )

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

        try:

            def test_logic() -> None:
                correlation_id_var.set("log-cid-001")
                user_id_var.set("log-uid-001")
                test_logger.info("hello from test")

            isolated_context(test_logic)

            output = stream.getvalue()
            assert "[log-cid-001]" in output, (
                f"expected '[log-cid-001]' in output, got {output!r}"
            )
            assert "[log-uid-001]" in output, (
                f"expected '[log-uid-001]' in output, got {output!r}"
            )
            assert "hello from test" in output, (
                f"expected 'hello from test' in output, got {output!r}"
            )
        finally:
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
            if isinstance(h, logging.StreamHandler):
                h.stream = stream

        try:

            def test_logic() -> None:
                correlation_id_var.set("dictcfg-cid")
                user_id_var.set("dictcfg-uid")
                test_logger.info("dictconfig test")

            isolated_context(test_logic)

            output = stream.getvalue()
            assert "[dictcfg-cid]" in output, (
                f"expected '[dictcfg-cid]' in output, got {output!r}"
            )
            assert "[dictcfg-uid]" in output, (
                f"expected '[dictcfg-uid]' in output, got {output!r}"
            )
        finally:
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

        try:

            def test_logic() -> None:
                correlation_id_var.set("contextvar-cid")
                user_id_var.set("contextvar-uid")
                test_logger.info(
                    "background job",
                    extra={"correlation_id": "explicit-cid"},
                )

            isolated_context(test_logic)

            output = stream.getvalue()
            assert "[explicit-cid]" in output, (
                f"expected '[explicit-cid]' in output, got {output!r}"
            )
            assert "[contextvar-uid]" in output, (
                f"expected '[contextvar-uid]' in output, got {output!r}"
            )
        finally:
            test_logger.removeHandler(handler)


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
