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


class ConfigEchoScenario(typ.NamedTuple):
    """Scenario for response-header echo configuration tests."""

    echo_header_in_response: bool
    request_kwargs: dict[str, str]
    expected_header: str | None


class TestCorrelationIDResponseHeader:
    """Tests for response-header echoing in the WSGI middleware."""

    @pytest.mark.parametrize(
        "scenario",
        [
            ConfigEchoScenario(
                echo_header_in_response=True,
                request_kwargs={"correlation_id": "trusted-id"},
                expected_header="trusted-id",
            ),
            ConfigEchoScenario(
                echo_header_in_response=False,
                request_kwargs={"correlation_id": "trusted-id"},
                expected_header=None,
            ),
            ConfigEchoScenario(
                echo_header_in_response=False,
                request_kwargs={},
                expected_header=None,
            ),
        ],
        ids=["enabled_trusted", "disabled_trusted", "disabled_generated"],
    )
    def test_process_response_echoes_correlation_id_according_to_config(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
        request_response_factory: cabc.Callable[
            ..., tuple[falcon.Request, falcon.Response]
        ],
        scenario: ConfigEchoScenario,
    ) -> None:
        """Verify response processing honours response-header echo config."""
        middleware = CorrelationIDMiddleware(
            trusted_sources=["127.0.0.1"],
            generator=lambda: "generated-id",
            echo_header_in_response=scenario.echo_header_in_response,
        )

        def _inner() -> None:
            """Exercise the request lifecycle inside an isolated context."""
            req, resp = request_response_factory(**scenario.request_kwargs)
            middleware.process_request(req, resp)
            if not scenario.request_kwargs:
                assert req.context.correlation_id == "generated-id", (
                    "expected generated request correlation ID to be "
                    f"'generated-id' but got {req.context.correlation_id!r}"
                )
            middleware.process_response(
                req,
                resp,
                resource=None,
                req_succeeded=True,
            )
            assert resp.get_header("X-Correlation-ID") == scenario.expected_header, (
                f"expected response header {scenario.expected_header!r} "
                f"but got {resp.get_header('X-Correlation-ID')!r}"
            )

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
            """Exercise response echoing with a custom header name."""
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

            assert resp.get_header(custom_header) == header_value, (
                f"expected {custom_header} header to equal header_value "
                f"{header_value!r} but got {resp.get_header(custom_header)!r}"
            )
            assert resp.get_header("X-Correlation-ID") is None, (
                "expected X-Correlation-ID header to be absent but got "
                f"{resp.get_header('X-Correlation-ID')!r}"
            )

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
            """Exercise response echoing for one final-ID scenario."""
            req, resp = request_response_factory(**scenario.request_kwargs)

            scenario.middleware.process_request(req, resp)
            scenario.middleware.process_response(
                req,
                resp,
                resource=None,
                req_succeeded=True,
            )

            assert resp.get_header("X-Correlation-ID") == scenario.expected_header, (
                "expected X-Correlation-ID header to equal "
                f"scenario.expected_header {scenario.expected_header!r} but got "
                f"{resp.get_header('X-Correlation-ID')!r}"
            )

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
            """Exercise response echoing over an existing header value."""
            req, resp = request_response_factory(correlation_id="trusted-id")
            resp.set_header("X-Correlation-ID", "pre-existing-id")
            middleware.process_request(req, resp)
            middleware.process_response(req, resp, resource=None, req_succeeded=True)
            actual_header = resp.get_header("X-Correlation-ID")
            assert actual_header == "trusted-id", (
                f"expected 'trusted-id', got {actual_header!r}"
            )

        isolated_context(_inner)

    def test_process_response_cleans_up_context_when_header_echo_fails(
        self,
        caplog: pytest.LogCaptureFixture,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
        request_response_factory: cabc.Callable[
            ..., tuple[falcon.Request, falcon.Response]
        ],
    ) -> None:
        """Verify response cleanup still runs if response header echo fails."""
        middleware = CorrelationIDMiddleware(trusted_sources=["127.0.0.1"])
        caplog.set_level(logging.WARNING, logger=_LOGGER_NAME)

        class HeaderFailingResponse(falcon.Response):
            """Falcon response that fails when setting a header."""

            def set_header(self, name: str, value: str) -> None:
                """Raise to simulate Falcon response header mutation failure.

                Raises
                ------
                RuntimeError
                    When the test helper intentionally exercises this failure path.

                """
                msg = f"failed to set {name}={value}"
                raise RuntimeError(msg)

        def _inner() -> None:
            """Exercise cleanup when response header mutation raises."""
            req, _resp = request_response_factory(correlation_id="trusted-id")
            resp = HeaderFailingResponse()

            middleware.process_request(req, resp)
            assert correlation_id_var.get() == "trusted-id", (
                "expected correlation_id_var to equal 'trusted-id' before "
                f"header echo failure but got {correlation_id_var.get()!r}"
            )

            with pytest.raises(RuntimeError, match="failed to set"):
                middleware.process_response(
                    req,
                    resp,
                    resource=None,
                    req_succeeded=True,
                )

            assert correlation_id_var.get() is None, (
                "expected correlation_id_var to be reset after header echo "
                f"failure but got {correlation_id_var.get()!r}"
            )
            assert req.context._correlation_id_reset_token is None, (
                "expected req.context._correlation_id_reset_token to be None "
                f"but got {req.context._correlation_id_reset_token!r}"
            )

        isolated_context(_inner)
        failure_record = next(
            record
            for record in caplog.records
            if record.name == _LOGGER_NAME
            and record.levelno == logging.WARNING
            and record.getMessage() == "Failed to echo correlation ID response header"
        )
        failure_log = typ.cast("typ.Any", failure_record)
        assert failure_log.correlation_id == "trusted-id", (
            "expected response-header failure log correlation_id to be "
            f"'trusted-id' but got {failure_log.correlation_id!r}"
        )
        assert failure_log.header_name == "X-Correlation-ID", (
            "expected response-header failure log header_name to be "
            f"'X-Correlation-ID' but got {failure_log.header_name!r}"
        )

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
    # pylint: disable-next=too-many-arguments,too-many-positional-arguments  # pytest injects fixtures and scenario.
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
            """Exercise response processing when request ID is absent."""
            req, resp = request_response_factory()
            if scenario.has_context_value:
                req.context.correlation_id = scenario.context_value

            middleware.process_response(
                req,
                resp,
                resource=None,
                req_succeeded=True,
            )

            assert resp.get_header("X-Correlation-ID") is None, (
                "expected X-Correlation-ID header to be absent when "
                f"scenario={scenario!r} but got "
                f"{resp.get_header('X-Correlation-ID')!r}"
            )

        isolated_context(_inner)
        assert (
            "Correlation ID response header echo skipped; middleware token absent"
            in caplog.text
        ), (
            "expected caplog.text to contain response-header skip message but got "
            f"{caplog.text!r}"
        )

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
            """Exercise response echo ordering before context cleanup."""
            req, resp = request_response_factory(correlation_id="trusted-id")

            middleware.process_request(req, resp)
            assert correlation_id_var.get() == "trusted-id", (
                "expected correlation_id_var to equal 'trusted-id' before "
                f"response cleanup but got {correlation_id_var.get()!r}"
            )

            middleware.process_response(
                req,
                resp,
                resource=None,
                req_succeeded=True,
            )

            assert resp.get_header("X-Correlation-ID") == "trusted-id", (
                "expected X-Correlation-ID header to equal 'trusted-id' but got "
                f"{resp.get_header('X-Correlation-ID')!r}"
            )
            assert correlation_id_var.get() is None, (
                "expected correlation_id_var to be reset after response cleanup "
                f"but got {correlation_id_var.get()!r}"
            )

        isolated_context(_inner)
        assert "Correlation ID response header echoed" in caplog.text
