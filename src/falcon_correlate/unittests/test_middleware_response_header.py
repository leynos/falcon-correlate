"""Unit tests for CorrelationIDMiddleware response header echoing."""

from __future__ import annotations

import logging
import typing as typ

import pytest

from falcon_correlate import CorrelationIDMiddleware
from falcon_correlate.middleware import correlation_id_var

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    import falcon

_LOGGER_NAME = "falcon_correlate.middleware"


class EchoScenario(typ.NamedTuple):
    """Scenario for response-header echoing with a generated final ID."""

    middleware: CorrelationIDMiddleware
    request_kwargs: dict[str, str]
    expected_header: str


class MissingCorrelationIDScenario(typ.NamedTuple):
    """Scenario for missing request correlation ID echo checks."""

    has_context_value: bool
    context_value: str | None


class TestCorrelationIDResponseHeader:
    """Tests for response-header echoing in the WSGI middleware."""

    def test_process_response_echoes_trusted_correlation_id_when_enabled(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
        request_response_factory: cabc.Callable[
            ..., tuple[falcon.Request, falcon.Response]
        ],
    ) -> None:
        """Verify response processing echoes the active correlation ID by default."""
        middleware = CorrelationIDMiddleware(trusted_sources=["127.0.0.1"])

        def _inner() -> None:
            req, resp = request_response_factory(correlation_id="trusted-id")

            middleware.process_request(req, resp)
            middleware.process_response(
                req,
                resp,
                resource=None,
                req_succeeded=True,
            )

            assert resp.get_header("X-Correlation-ID") == "trusted-id"

        isolated_context(_inner)

    @pytest.mark.parametrize(
        "scenario",
        [
            EchoScenario(
                middleware=CorrelationIDMiddleware(generator=lambda: "generated-id"),
                request_kwargs={},
                expected_header="generated-id",
            ),
            EchoScenario(
                middleware=CorrelationIDMiddleware(
                    trusted_sources=["127.0.0.1"],
                    generator=lambda: "generated-invalid",
                    validator=lambda _: False,
                ),
                request_kwargs={"correlation_id": "invalid-id"},
                expected_header="generated-invalid",
            ),
            EchoScenario(
                middleware=CorrelationIDMiddleware(
                    trusted_sources=["10.0.0.1"],
                    generator=lambda: "generated-untrusted",
                ),
                request_kwargs={"correlation_id": "untrusted-id"},
                expected_header="generated-untrusted",
            ),
        ],
        ids=["generated", "validation_failure", "untrusted_source"],
    )
    def test_process_response_echoes_final_generated_correlation_id(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
        request_response_factory: cabc.Callable[
            ..., tuple[falcon.Request, falcon.Response]
        ],
        scenario: EchoScenario,
    ) -> None:
        """Verify response echo uses the final request correlation ID."""

        def _inner() -> None:
            req, resp = request_response_factory(**scenario.request_kwargs)

            scenario.middleware.process_request(req, resp)
            scenario.middleware.process_response(
                req,
                resp,
                resource=None,
                req_succeeded=True,
            )

            assert resp.get_header("X-Correlation-ID") == scenario.expected_header

        isolated_context(_inner)

    @pytest.mark.parametrize(
        "scenario",
        [
            MissingCorrelationIDScenario(
                has_context_value=False,
                context_value=None,
            ),
            MissingCorrelationIDScenario(
                has_context_value=True,
                context_value=None,
            ),
        ],
        ids=["attribute_absent", "attribute_none"],
    )
    def test_process_response_skips_echo_when_correlation_id_absent(
        self,
        caplog: pytest.LogCaptureFixture,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
        request_response_factory: cabc.Callable[
            ..., tuple[falcon.Request, falcon.Response]
        ],
        scenario: MissingCorrelationIDScenario,
    ) -> None:
        """Verify missing request correlation IDs are not echoed."""
        middleware = CorrelationIDMiddleware()
        caplog.set_level(logging.DEBUG, logger=_LOGGER_NAME)

        def _inner() -> None:
            req, resp = request_response_factory()
            if scenario.has_context_value:
                req.context.correlation_id = scenario.context_value

            middleware.process_response(
                req,
                resp,
                resource=None,
                req_succeeded=True,
            )

            assert resp.get_header("X-Correlation-ID") is None

        isolated_context(_inner)
        assert "Correlation ID response header echo skipped; ID absent" in caplog.text

    @pytest.mark.parametrize(
        "correlation_id",
        ["trusted-id", "generated-id"],
        ids=["trusted", "generated"],
    )
    def test_process_response_omits_correlation_id_when_echo_disabled(
        self,
        caplog: pytest.LogCaptureFixture,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
        request_response_factory: cabc.Callable[
            ..., tuple[falcon.Request, falcon.Response]
        ],
        correlation_id: str,
    ) -> None:
        """Verify response processing honours disabled response-header echoing."""
        middleware = CorrelationIDMiddleware(
            trusted_sources=["127.0.0.1"],
            echo_header_in_response=False,
        )
        caplog.set_level(logging.DEBUG, logger=_LOGGER_NAME)

        def _inner() -> None:
            req, resp = request_response_factory(correlation_id=correlation_id)

            middleware.process_request(req, resp)
            middleware.process_response(
                req,
                resp,
                resource=None,
                req_succeeded=True,
            )

            assert resp.get_header("X-Correlation-ID") is None

        isolated_context(_inner)
        assert "Correlation ID response header echo disabled" in caplog.text

    def test_process_response_echoes_header_before_contextvar_cleanup(
        self,
        caplog: pytest.LogCaptureFixture,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
        request_response_factory: cabc.Callable[
            ..., tuple[falcon.Request, falcon.Response]
        ],
    ) -> None:
        """Verify response echo happens before request context cleanup."""
        middleware = CorrelationIDMiddleware(trusted_sources=["127.0.0.1"])
        caplog.set_level(logging.DEBUG, logger=_LOGGER_NAME)

        def _inner() -> None:
            req, resp = request_response_factory(correlation_id="trusted-id")

            middleware.process_request(req, resp)
            assert correlation_id_var.get() == "trusted-id"

            middleware.process_response(
                req,
                resp,
                resource=None,
                req_succeeded=True,
            )

            assert resp.get_header("X-Correlation-ID") == "trusted-id"
            assert correlation_id_var.get() is None

        isolated_context(_inner)
        assert "Correlation ID response header echoed" in caplog.text
