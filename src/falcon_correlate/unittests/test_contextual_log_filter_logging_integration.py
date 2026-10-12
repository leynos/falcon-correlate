"""Tests for standard logging and dictConfig integration.

Tests
-----
TestContextualLogFilterLoggingIntegration
    Verify the filter works through configured loggers.
"""

from __future__ import annotations

import io
import logging
import logging.config
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc

from falcon_correlate import correlation_id_var, user_id_var


class TestContextualLogFilterLoggingIntegration:
    """Tests for integration with standard logging configuration."""

    def test_filter_works_with_logger(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
        logger_with_capture: cabc.Callable[[str], tuple[logging.Logger, io.StringIO]],
    ) -> None:
        """Verify filter enriches records emitted through a logger."""
        test_logger, stream = logger_with_capture(
            "test_contextual_log_filter_integration",
        )

        def test_logic() -> None:
            """Exercise the isolated logging scenario."""
            correlation_id_var.set("log-cid-001")
            user_id_var.set("log-uid-001")
            test_logger.info("hello from test")

        isolated_context(test_logic)

        output = stream.getvalue()
        expected_output = "[log-cid-001][log-uid-001] hello from test\n"
        failure_message = (
            f"expected complete formatted log {expected_output!r}, got {output!r}"
        )
        assert output == expected_output, failure_message

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
                """Exercise the isolated logging scenario."""
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
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
        logger_with_capture: cabc.Callable[[str], tuple[logging.Logger, io.StringIO]],
    ) -> None:
        """Verify extra= correlation_id is preserved when logging through a logger."""
        test_logger, stream = logger_with_capture(
            "test_contextual_extra_preserved",
        )

        def test_logic() -> None:
            """Exercise the isolated logging scenario."""
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
