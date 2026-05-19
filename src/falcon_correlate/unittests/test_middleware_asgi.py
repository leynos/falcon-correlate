"""Unit tests for the Falcon ASGI correlation ID middleware."""
# pylint: disable=too-many-arguments,too-many-positional-arguments  # Falcon middleware hooks and pytest fixtures require multi-arg signatures.

from __future__ import annotations

import asyncio
import inspect
import typing as typ
from http import HTTPStatus

import falcon.asgi
import falcon.testing
import pytest

from falcon_correlate import (
    CorrelationIDConfig,
    CorrelationIDMiddlewareASGI,
    correlation_id_var,
)
from tests.asgi_resources import ASGICorrelationEchoResource


class _Context:
    """Minimal Falcon-like request context for direct middleware tests."""

    correlation_id: str | None = None
    _correlation_id_reset_token: typ.Any = None


class _Request:
    """Minimal ASGI request double for middleware hook tests."""

    def __init__(
        self,
        *,
        headers: dict[str, str] | None = None,
        remote_addr: str | None = "127.0.0.1",
    ) -> None:
        self.context = _Context()
        self.remote_addr = remote_addr
        self._headers = headers or {}

    def get_header(self, name: str) -> str | None:
        """Return a test header by name."""
        return self._headers.get(name)


class _Response:
    """Minimal ASGI response double for middleware hook tests."""

    def __init__(self) -> None:
        self.headers: dict[str, str] = {}

    def set_header(self, name: str, value: str) -> None:
        """Record a response header."""
        self.headers[name] = value

    def get_header(self, name: str) -> str | None:
        """Return a recorded response header."""
        return self.headers.get(name)


class _HeaderFailingResponse(_Response):
    """Response double that fails during header mutation."""

    def set_header(self, name: str, value: str) -> None:
        """Raise when middleware tries to echo the response header."""
        msg = f"failed to set {name}={value}"
        raise RuntimeError(msg)


async def _process_request(
    middleware: CorrelationIDMiddlewareASGI,
    req: _Request,
    resp: _Response,
) -> None:
    """Call the public ASGI request hook with a lightweight request double."""
    await middleware.process_request(
        typ.cast("falcon.asgi.Request", req),
        typ.cast("falcon.asgi.Response", resp),
    )


async def _process_response(
    middleware: CorrelationIDMiddlewareASGI,
    req: _Request,
    resp: _Response,
) -> None:
    """Call the public ASGI response hook with lightweight doubles."""
    await middleware.process_response(
        typ.cast("falcon.asgi.Request", req),
        typ.cast("falcon.asgi.Response", resp),
        resource=None,
        req_succeeded=True,
    )


class TestCorrelationIDMiddlewareASGIConfiguration:
    """Tests for ASGI middleware construction and public hook shape."""

    def test_default_construction_uses_keyword_configuration(self) -> None:
        """Verify default construction mirrors WSGI keyword configuration."""
        middleware = CorrelationIDMiddlewareASGI(generator=lambda: "generated-asgi")

        assert middleware.config.generator() == "generated-asgi"
        assert middleware.header_name == "X-Correlation-ID"
        assert middleware.echo_header_in_response is True

    def test_config_based_construction_uses_given_config(self) -> None:
        """Verify ASGI middleware accepts a pre-built configuration."""
        config = CorrelationIDConfig(header_name="X-Request-ID")
        middleware = CorrelationIDMiddlewareASGI(config=config)

        assert middleware.config is config
        assert middleware.header_name == "X-Request-ID"

    def test_config_and_kwargs_conflict_raises_value_error(self) -> None:
        """Verify config-plus-keyword rejection matches WSGI middleware."""
        config = CorrelationIDConfig()

        with pytest.raises(
            ValueError,
            match="Cannot specify both 'config' and individual parameters",
        ):
            CorrelationIDMiddlewareASGI(config=config, header_name="X-Request-ID")

    def test_process_hooks_are_coroutines(self) -> None:
        """Verify Falcon ASGI hooks are explicit coroutine functions."""
        assert inspect.iscoroutinefunction(CorrelationIDMiddlewareASGI.process_request)
        assert inspect.iscoroutinefunction(CorrelationIDMiddlewareASGI.process_response)


class TestCorrelationIDMiddlewareASGIRequestLifecycle:
    """Tests for direct ASGI request and response hook behaviour."""

    @pytest.mark.asyncio
    async def test_process_request_generates_missing_correlation_id(self) -> None:
        """Verify ASGI request processing generates when no header is present."""
        middleware = CorrelationIDMiddlewareASGI(generator=lambda: "generated-asgi")
        req = _Request()
        resp = _Response()

        await _process_request(middleware, req, resp)

        assert req.context.correlation_id == "generated-asgi"
        assert correlation_id_var.get() == "generated-asgi"

        await _process_response(middleware, req, resp)
        assert correlation_id_var.get() is None
        assert resp.get_header("X-Correlation-ID") == "generated-asgi"

    @pytest.mark.parametrize(
        ("middleware", "req", "expected_id"),
        [
            (
                CorrelationIDMiddlewareASGI(trusted_sources=["127.0.0.1"]),
                _Request(headers={"X-Correlation-ID": " trusted-asgi "}),
                "trusted-asgi",
            ),
            (
                CorrelationIDMiddlewareASGI(
                    generator=lambda: "generated-untrusted",
                    trusted_sources=["10.0.0.1"],
                ),
                _Request(headers={"X-Correlation-ID": "untrusted-asgi"}),
                "generated-untrusted",
            ),
            (
                CorrelationIDMiddlewareASGI(
                    generator=lambda: "generated-invalid",
                    trusted_sources=["127.0.0.1"],
                    validator=lambda _: False,
                ),
                _Request(headers={"X-Correlation-ID": "invalid-asgi"}),
                "generated-invalid",
            ),
            (
                CorrelationIDMiddlewareASGI(
                    generator=lambda: "generated-empty",
                    trusted_sources=["127.0.0.1"],
                ),
                _Request(headers={"X-Correlation-ID": "   "}),
                "generated-empty",
            ),
        ],
        ids=["trusted", "untrusted", "invalid", "empty"],
    )
    @pytest.mark.asyncio
    async def test_process_request_selects_final_correlation_id(
        self,
        middleware: CorrelationIDMiddlewareASGI,
        req: _Request,
        expected_id: str,
    ) -> None:
        """Verify ASGI request processing applies WSGI selection rules."""
        resp = _Response()

        await _process_request(middleware, req, resp)

        assert req.context.correlation_id == expected_id
        assert correlation_id_var.get() == expected_id

        await _process_response(middleware, req, resp)
        assert correlation_id_var.get() is None

    @pytest.mark.asyncio
    async def test_validator_exception_generates_new_id(self) -> None:
        """Verify validator exceptions reject incoming ASGI correlation IDs."""

        def rejecting_validator(_value: str) -> bool:
            msg = "validator failed"
            raise RuntimeError(msg)

        middleware = CorrelationIDMiddlewareASGI(
            generator=lambda: "generated-after-exception",
            trusted_sources=["127.0.0.1"],
            validator=rejecting_validator,
        )
        req = _Request(headers={"X-Correlation-ID": "incoming-asgi"})
        resp = _Response()

        await _process_request(middleware, req, resp)

        assert req.context.correlation_id == "generated-after-exception"

        await _process_response(middleware, req, resp)

    @pytest.mark.parametrize(
        ("echo_header_in_response", "expected_header"),
        [(True, "generated-asgi"), (False, None)],
        ids=["enabled", "disabled"],
    )
    @pytest.mark.asyncio
    async def test_process_response_honours_echo_configuration(
        self,
        echo_header_in_response: bool,  # noqa: FBT001 - pytest parametrized value
        expected_header: str | None,
    ) -> None:
        """Verify ASGI response processing honours header echo configuration."""
        middleware = CorrelationIDMiddlewareASGI(
            generator=lambda: "generated-asgi",
            echo_header_in_response=echo_header_in_response,
        )
        req = _Request()
        resp = _Response()

        await _process_request(middleware, req, resp)
        await _process_response(middleware, req, resp)

        assert resp.get_header("X-Correlation-ID") == expected_header
        assert correlation_id_var.get() is None

    @pytest.mark.asyncio
    async def test_process_response_skips_echo_when_correlation_id_absent(self) -> None:
        """Verify ASGI response processing skips absent request IDs."""
        middleware = CorrelationIDMiddlewareASGI()
        req = _Request()
        resp = _Response()

        await _process_response(middleware, req, resp)

        assert resp.get_header("X-Correlation-ID") is None
        assert correlation_id_var.get() is None

    @pytest.mark.asyncio
    async def test_process_response_cleans_up_context_when_header_echo_fails(
        self,
    ) -> None:
        """Verify ASGI cleanup still runs if response header echo fails."""
        middleware = CorrelationIDMiddlewareASGI(generator=lambda: "generated-asgi")
        req = _Request()
        resp = _HeaderFailingResponse()

        await _process_request(middleware, req, resp)
        assert correlation_id_var.get() == "generated-asgi"

        with pytest.raises(RuntimeError, match="failed to set"):
            await _process_response(middleware, req, resp)

        assert correlation_id_var.get() is None
        assert getattr(req.context, "_correlation_id_reset_token", None) is None

    @pytest.mark.asyncio
    async def test_concurrent_asgi_requests_keep_correlation_ids_isolated(
        self,
    ) -> None:
        """Verify ASGI request-local context is isolated between tasks."""
        # A shared iterator deliberately gives each single-threaded task a unique ID.
        ids = iter(f"generated-{index}" for index in range(16))
        middleware = CorrelationIDMiddlewareASGI(generator=lambda: next(ids))

        async def run_request() -> tuple[str, str | None, str | None]:
            req = _Request()
            resp = _Response()

            await _process_request(middleware, req, resp)
            request_id = req.context.correlation_id
            during_request_id = correlation_id_var.get()
            # Repeated yields intentionally force task interleaving for contextvars.
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            await asyncio.sleep(0.001)
            await _process_response(middleware, req, resp)
            assert request_id is not None
            return request_id, during_request_id, correlation_id_var.get()

        results = await asyncio.gather(*(run_request() for _ in range(16)))

        assert results == [
            (f"generated-{index}", f"generated-{index}", None) for index in range(16)
        ]
        assert correlation_id_var.get() is None


class TestCorrelationIDMiddlewareASGIFalconIntegration:
    """Tests for ASGI middleware in a real Falcon ASGI application."""

    def test_falcon_asgi_app_exposes_and_echoes_correlation_id(self) -> None:
        """Verify a Falcon ASGI app observes and echoes the same ID."""
        app = falcon.asgi.App(
            middleware=[
                CorrelationIDMiddlewareASGI(
                    trusted_sources=["127.0.0.1"],
                ),
            ],
        )
        app.add_route("/correlation", ASGICorrelationEchoResource())
        client = falcon.testing.TestClient(app)

        result = client.simulate_get(
            "/correlation",
            headers={"X-Correlation-ID": "trusted-asgi"},
        )

        assert result.status_code == HTTPStatus.OK
        assert result.json == {
            "context_correlation_id": "trusted-asgi",
            "contextvar_correlation_id": "trusted-asgi",
        }
        assert result.headers["X-Correlation-ID"] == "trusted-asgi"
