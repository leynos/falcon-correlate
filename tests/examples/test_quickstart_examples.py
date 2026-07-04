"""Tests for the quickstart example modules."""

from __future__ import annotations

import importlib
import io
import itertools
import logging
import re
import typing as typ
from http import HTTPStatus

import falcon
import falcon.testing

from falcon_correlate import (
    RECOMMENDED_LOG_FORMAT,
    ContextualLogFilter,
    CorrelationIDConfig,
    correlation_id_var,
    default_uuid_validator,
    user_id_var,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import types

    from syrupy.assertion import SnapshotAssertion


_ASCTIME_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}",
)
_LOG_FORMAT_VARIANTS = (
    ("cid-snapshot-1", "uid-snapshot-1"),
    ("cid-snapshot-1", None),
    (None, "uid-snapshot-1"),
    (None, None),
)


def _load_quickstart_module(module_name: str) -> types.ModuleType:
    """Import a quickstart example module by short name."""
    return importlib.import_module(f"examples.quickstart.{module_name}")


def _example_app(module: types.ModuleType) -> falcon.App:
    """Return the Falcon app exported by an example module."""
    return typ.cast("falcon.App", vars(module)["app"])


class TestQuickstartMinimalApp:
    """Tests for the minimal quickstart Falcon application."""

    def test_minimal_app_returns_a_generated_correlation_id(self) -> None:
        """Verify the minimal app returns a generated correlation ID header."""
        module = _load_quickstart_module("minimal_app")
        client = falcon.testing.TestClient(_example_app(module))

        result = client.simulate_get("/hello")

        assert result.status_code == HTTPStatus.OK
        assert result.json == {"message": "hello"}
        correlation_id = result.headers["X-Correlation-ID"]
        assert default_uuid_validator(correlation_id)


class TestQuickstartConfiguredApp:
    """Tests for the configured quickstart Falcon application."""

    def test_configured_app_echoes_trusted_incoming_correlation_id(self) -> None:
        """Verify trusted incoming IDs are echoed unchanged."""
        module = _load_quickstart_module("configured_app")
        client = falcon.testing.TestClient(_example_app(module))

        result = client.simulate_get(
            "/hello",
            headers={"X-Correlation-ID": "cid-quickstart-1"},
        )

        assert result.status_code == HTTPStatus.OK
        assert result.headers["X-Correlation-ID"] == "cid-quickstart-1"

    def test_configured_app_exports_the_documented_config(self) -> None:
        """Verify the configured example exposes the documented options."""
        module = _load_quickstart_module("configured_app")
        config = typ.cast("CorrelationIDConfig", vars(module)["config"])

        assert config.header_name == "X-Correlation-ID"
        assert config.trusted_sources == frozenset({"127.0.0.1"})
        assert config.echo_header_in_response is True


class TestQuickstartLoggingSetup:
    """Tests for the quickstart logging configuration."""

    def test_logging_setup_includes_context_values(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify the logging example emits correlation and user IDs."""
        module = _load_quickstart_module("logging_setup")
        configure_logging = typ.cast(
            "cabc.Callable[[], logging.Logger]",
            vars(module)["configure_logging"],
        )
        stream = io.StringIO()
        logger = configure_logging()
        handlers = list(logger.handlers)
        for handler in handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.stream = stream

        try:

            def test_logic() -> None:
                correlation_id_var.set("cid-log-1")
                user_id_var.set("uid-log-1")
                logger.info("hello from quickstart")

            isolated_context(test_logic)
        finally:
            for handler in handlers:
                logger.removeHandler(handler)
                handler.close()

        output = stream.getvalue()
        assert "cid-log-1" in output
        assert "uid-log-1" in output
        assert "hello from quickstart" in output

    def test_log_format_variants(self, snapshot: SnapshotAssertion) -> None:
        """Verify contextual placeholder variants keep a stable text shape."""
        rendered = list(itertools.starmap(_render_log_line, _LOG_FORMAT_VARIANTS))

        assert "\n".join(rendered) == snapshot


def _render_log_line(correlation_id: str | None, user_id: str | None) -> str:
    """Render one recommended-format log line with fixed context values."""
    correlation_token = correlation_id_var.set(correlation_id)
    user_token = user_id_var.set(user_id)
    try:
        record = logging.LogRecord(
            name="quickstart.snapshot",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="snapshot message",
            args=(),
            exc_info=None,
        )
        ContextualLogFilter().filter(record)
        formatted = logging.Formatter(RECOMMENDED_LOG_FORMAT).format(record)
    finally:
        user_id_var.reset(user_token)
        correlation_id_var.reset(correlation_token)
    return _ASCTIME_PATTERN.sub("<asctime>", formatted)
