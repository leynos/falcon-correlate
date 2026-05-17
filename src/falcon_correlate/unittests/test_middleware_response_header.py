"""Unit tests for CorrelationIDMiddleware response header echoing."""

from __future__ import annotations

import logging
import typing as typ

import falcon
import falcon.testing
import pytest

from falcon_correlate import CorrelationIDMiddleware
from falcon_correlate.middleware import correlation_id_var

if typ.TYPE_CHECKING:
    import collections.abc as cabc

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

    @pytest.mark.parametrize(
        ("echo_header_in_response", "expected_header"),
        [
            (True, "trusted-id"),
            (False, None),
        ],
        ids=["enabled", "disabled"],
    )
    def test_process_response_echoes_correlation_id_according_to_config(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
        request_response_factory: cabc.Callable[
            ..., tuple[falcon.Request, falcon.Response]
        ],
        echo_header_in_response: typ.Literal[True, False],
        expected_header: str | None,
    ) -> None:
        """Verify response processing honours response-header echo config."""
        middleware = CorrelationIDMiddleware(
            trusted_sources=["127.0.0.1"],
            echo_header_in_response=echo_header_in_response,
        )

        def _inner() -> None:
            req, resp = request_response_factory(correlation_id="trusted-id")

            middleware.process_request(req, resp)
            middleware.process_response(
                req,
                resp,
                resource=None,
                req_succeeded=True,
            )

            assert resp.get_header("X-Correlation-ID") == expected_header

        isolated_context(_inner)

    def test_process_response_uses_custom_header_name(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify response processing echoes the configured header name."""
        custom_header = "X-Request-ID"
        header_value = "custom-request-id"
        middleware = CorrelationIDMiddleware(
            trusted_sources=["127.0.0.1"],
            header_name=custom_header,
        )

        def _inner() -> None:
            environ = falcon.testing.create_environ(
                path="/test",
                headers={custom_header: header_value},
                remote_addr="127.0.0.1",
            )
            req = falcon.Request(environ)
            resp = falcon.Response()

            middleware.process_request(req, resp)
            middleware.process_response(
                req,
                resp,
                resource=None,
                req_succeeded=True,
            )

            assert resp.get_header(custom_header) == header_value
            assert resp.get_header("X-Correlation-ID") is None

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

    def test_process_response_overwrites_existing_correlation_id_header(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
        request_response_factory: cabc.Callable[
            ..., tuple[falcon.Request, falcon.Response]
        ],
    ) -> None:
        """Verify response processing overwrites a pre-existing echo header."""
        middleware = CorrelationIDMiddleware(trusted_sources=["127.0.0.1"])

        def _inner() -> None:
            req, resp = request_response_factory(correlation_id="trusted-id")
            resp.set_header("X-Correlation-ID", "pre-existing-id")

            middleware.process_request(req, resp)
            middleware.process_response(
                req,
                resp,
                resource=None,
                req_succeeded=True,
            )

            assert resp.get_header("X-Correlation-ID") == "trusted-id"

        isolated_context(_inner)

    def test_process_response_cleans_up_context_when_header_echo_fails(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
        request_response_factory: cabc.Callable[
            ..., tuple[falcon.Request, falcon.Response]
        ],
    ) -> None:
        """Verify response cleanup still runs if response header echo fails."""
        middleware = CorrelationIDMiddleware(trusted_sources=["127.0.0.1"])

        class HeaderFailingResponse(falcon.Response):
            """Falcon response that fails when setting a header."""

            def set_header(self, name: str, value: str) -> None:
                msg = f"failed to set {name}={value}"
                raise RuntimeError(msg)

        def _inner() -> None:
            req, _resp = request_response_factory(correlation_id="trusted-id")
            resp = HeaderFailingResponse()

            middleware.process_request(req, resp)
            assert correlation_id_var.get() == "trusted-id"

            with pytest.raises(RuntimeError, match="failed to set"):
                middleware.process_response(
                    req,
                    resp,
                    resource=None,
                    req_succeeded=True,
                )

            assert correlation_id_var.get() is None
            assert req.context._correlation_id_reset_token is None

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
