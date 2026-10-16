"""Tests for the recommended logging format constant.

Tests
-----
TestRecommendedLogFormat
    Verify the constant is exported and works with logging.
"""

from __future__ import annotations

import io
import logging
import logging.config
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc

from falcon_correlate import (
    RECOMMENDED_LOG_FORMAT,
    ContextualLogFilter,
    correlation_id_var,
    user_id_var,
)


class TestRecommendedLogFormat:
    """Tests for RECOMMENDED_LOG_FORMAT constant."""

    def test_recommended_log_format_in_all(self) -> None:
        """Verify RECOMMENDED_LOG_FORMAT is listed in __all__."""
        import falcon_correlate

        assert "RECOMMENDED_LOG_FORMAT" in falcon_correlate.__all__, (
            "RECOMMENDED_LOG_FORMAT missing from falcon_correlate.__all__"
        )

    def test_recommended_log_format_importable_from_root(self) -> None:
        """Verify RECOMMENDED_LOG_FORMAT can be imported from package root."""
        from falcon_correlate import RECOMMENDED_LOG_FORMAT as IMPORTED_FMT

        assert isinstance(IMPORTED_FMT, str), (
            f"expected str, got {type(IMPORTED_FMT).__name__}"
        )

    def test_recommended_log_format_contains_required_placeholders(
        self,
    ) -> None:
        """Verify format string contains correlation_id and user_id."""
        assert "%(correlation_id)s" in RECOMMENDED_LOG_FORMAT, (
            "RECOMMENDED_LOG_FORMAT must contain %(correlation_id)s"
        )
        assert "%(user_id)s" in RECOMMENDED_LOG_FORMAT, (
            "RECOMMENDED_LOG_FORMAT must contain %(user_id)s"
        )

    def test_recommended_log_format_usable_with_formatter(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify the constant works with Formatter and ContextualLogFilter."""
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(
            logging.Formatter(RECOMMENDED_LOG_FORMAT),
        )
        handler.addFilter(ContextualLogFilter())

        test_logger = logging.getLogger("test_recommended_fmt")
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.INFO)
        test_logger.propagate = False

        try:

            def test_logic() -> None:
                """Exercise the isolated logging scenario."""
                correlation_id_var.set("rec-cid-001")
                user_id_var.set("rec-uid-001")
                test_logger.info("recommended format test")

            isolated_context(test_logic)

            output = stream.getvalue()
            expected_suffix = (
                " - [INFO] - [rec-cid-001] - [rec-uid-001] - "
                "test_recommended_fmt - recommended format test\n"
            )
            failure_message = (
                f"expected formatted log suffix {expected_suffix!r}, got {output!r}"
            )
            assert output.endswith(expected_suffix), failure_message
        finally:
            test_logger.removeHandler(handler)
            handler.close()

    def test_recommended_log_format_works_in_dictconfig(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify the constant works in a dictConfig format value."""
        config = {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {
                "contextual": {
                    "()": "falcon_correlate.ContextualLogFilter",
                },
            },
            "formatters": {
                "recommended": {
                    "format": RECOMMENDED_LOG_FORMAT,
                },
            },
            "handlers": {
                "test_stream": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                    "formatter": "recommended",
                    "filters": ["contextual"],
                },
            },
            "loggers": {
                "test_recommended_dictconfig": {
                    "handlers": ["test_stream"],
                    "level": "INFO",
                },
            },
        }
        logging.config.dictConfig(config)
        test_logger = logging.getLogger(
            "test_recommended_dictconfig",
        )

        stream = io.StringIO()
        for h in test_logger.handlers:
            if isinstance(h, logging.StreamHandler):
                h.stream = stream

        try:

            def test_logic() -> None:
                """Exercise the isolated logging scenario."""
                correlation_id_var.set("recdcfg-cid")
                user_id_var.set("recdcfg-uid")
                test_logger.info("recommended dictconfig test")

            isolated_context(test_logic)

            output = stream.getvalue()
            assert "[recdcfg-cid]" in output, (
                f"expected '[recdcfg-cid]', got {output!r}"
            )
            assert "[recdcfg-uid]" in output, (
                f"expected '[recdcfg-uid]', got {output!r}"
            )
        finally:
            for h in list(test_logger.handlers):
                test_logger.removeHandler(h)
