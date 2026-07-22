"""Unit tests for the Falcon ASGI correlation ID middleware."""

from __future__ import annotations

import asyncio
import inspect

import pytest

from falcon_correlate import (
    CorrelationIDConfig,
    CorrelationIDMiddlewareASGI,
    correlation_id_var,
)
from falcon_correlate.unittests.asgi_middleware_helpers import (
    _HeaderFailingResponse,
    _process_request,
    _process_response,
    _Request,
    _Response,
)


class TestCorrelationIDMiddlewareASGIConfiguration:
    """Tests for ASGI middleware construction and public hook shape."""

    def test_default_construction_uses_keyword_configuration(self) -> None:
        """Verify default construction mirrors WSGI keyword configuration."""
        middleware = CorrelationIDMiddlewareASGI(generator=lambda: "generated-asgi")

        assert middleware.config.generator() == "generated-asgi", (
            "expected middleware.config.generator() to return 'generated-asgi' "
            f"but got {middleware.config.generator()!r}"
        )
        assert middleware.header_name == "X-Correlation-ID", (
            "expected middleware.header_name to be 'X-Correlation-ID' but got "
            f"{middleware.header_name!r}"
        )
        assert middleware.echo_header_in_response is True, (
            "expected middleware.echo_header_in_response to be True but got "
            f"{middleware.echo_header_in_response!r}"
        )

    def test_config_based_construction_uses_given_config(self) -> None:
        """Verify ASGI middleware accepts a pre-built configuration."""
        config = CorrelationIDConfig(header_name="X-Request-ID")
        middleware = CorrelationIDMiddlewareASGI(config=config)

        assert middleware.config is config, (
            "expected middleware.config to be the supplied config object but got "
            f"{middleware.config!r}"
        )
        assert middleware.header_name == "X-Request-ID", (
            "expected middleware.header_name to be 'X-Request-ID' but got "
            f"{middleware.header_name!r}"
        )

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
        assert inspect.iscoroutinefunction(
            CorrelationIDMiddlewareASGI.process_request,
        ), "expected CorrelationIDMiddlewareASGI.process_request to be a coroutine"
        assert inspect.iscoroutinefunction(
            CorrelationIDMiddlewareASGI.process_response,
        ), "expected CorrelationIDMiddlewareASGI.process_response to be a coroutine"


class TestCorrelationIDMiddlewareASGIRequestLifecycle:
    """Tests for direct ASGI request and response hook behaviour."""

    @pytest.mark.asyncio
    async def test_process_request_generates_missing_correlation_id(self) -> None:
        """Verify ASGI request processing generates when no header is present."""
        middleware = CorrelationIDMiddlewareASGI(generator=lambda: "generated-asgi")
        req = _Request()
        resp = _Response()

        await _process_request(middleware, req, resp)

        assert req.context.correlation_id == "generated-asgi", (
            "expected req.context.correlation_id to be 'generated-asgi' but got "
            f"{req.context.correlation_id!r}"
        )
        assert correlation_id_var.get() == "generated-asgi", (
            "expected correlation_id_var.get() to be 'generated-asgi' but got "
            f"{correlation_id_var.get()!r}"
        )

        await _process_response(middleware, req, resp)
        assert correlation_id_var.get() is None, (
            "expected correlation_id_var.get() to be None after response but got "
            f"{correlation_id_var.get()!r}"
        )
        assert resp.get_header("X-Correlation-ID") == "generated-asgi", (
            "expected resp.get_header('X-Correlation-ID') to be 'generated-asgi' "
            f"but got {resp.get_header('X-Correlation-ID')!r}"
        )

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

        assert req.context.correlation_id == expected_id, (
            "expected req.context.correlation_id to equal expected_id "
            f"{expected_id!r} but got {req.context.correlation_id!r}"
        )
        assert correlation_id_var.get() == expected_id, (
            "expected correlation_id_var.get() to equal expected_id "
            f"{expected_id!r} but got {correlation_id_var.get()!r}"
        )

        await _process_response(middleware, req, resp)
        assert correlation_id_var.get() is None, (
            "expected correlation_id_var.get() to be None after response but got "
            f"{correlation_id_var.get()!r}"
        )

    @pytest.mark.asyncio
    async def test_validator_exception_generates_new_id(self) -> None:
        """Verify validator exceptions reject incoming ASGI correlation IDs."""

        def rejecting_validator(_value: str) -> bool:
            """Reject the supplied correlation ID for the test."""
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

        assert req.context.correlation_id == "generated-after-exception", (
            "expected req.context.correlation_id to be "
            f"'generated-after-exception' but got {req.context.correlation_id!r}"
        )

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

        assert resp.get_header("X-Correlation-ID") == expected_header, (
            "expected resp.get_header('X-Correlation-ID') to equal "
            f"expected_header {expected_header!r} but got "
            f"{resp.get_header('X-Correlation-ID')!r}"
        )
        assert correlation_id_var.get() is None, (
            "expected correlation_id_var.get() to be None after response but got "
            f"{correlation_id_var.get()!r}"
        )

    @pytest.mark.asyncio
    async def test_process_response_skips_echo_when_correlation_id_absent(self) -> None:
        """Verify ASGI response processing skips absent request IDs."""
        middleware = CorrelationIDMiddlewareASGI()
        req = _Request()
        resp = _Response()

        await _process_response(middleware, req, resp)

        assert resp.get_header("X-Correlation-ID") is None, (
            "expected resp.get_header('X-Correlation-ID') to be None but got "
            f"{resp.get_header('X-Correlation-ID')!r}"
        )
        assert correlation_id_var.get() is None, (
            "expected correlation_id_var.get() to be None after response but got "
            f"{correlation_id_var.get()!r}"
        )

    @pytest.mark.asyncio
    async def test_process_response_cleans_up_context_when_header_echo_fails(
        self,
    ) -> None:
        """Verify ASGI cleanup still runs if response header echo fails."""
        middleware = CorrelationIDMiddlewareASGI(generator=lambda: "generated-asgi")
        req = _Request()
        resp = _HeaderFailingResponse()

        await _process_request(middleware, req, resp)
        assert correlation_id_var.get() == "generated-asgi", (
            "expected correlation_id_var.get() to be 'generated-asgi' before "
            f"header failure but got {correlation_id_var.get()!r}"
        )

        with pytest.raises(RuntimeError, match="failed to set"):
            await _process_response(middleware, req, resp)

        assert correlation_id_var.get() is None, (
            "expected correlation_id_var.get() to be None after failure but got "
            f"{correlation_id_var.get()!r}"
        )
        assert getattr(req.context, "_correlation_id_reset_token", None) is None, (
            "expected req.context._correlation_id_reset_token to be None but got "
            f"{getattr(req.context, '_correlation_id_reset_token', None)!r}"
        )

    @pytest.mark.asyncio
    async def test_concurrent_asgi_requests_keep_correlation_ids_isolated(
        self,
    ) -> None:
        """Verify ASGI request-local context is isolated between tasks."""
        # A shared iterator deliberately gives each single-threaded task a unique ID.
        ids = iter(f"generated-{index}" for index in range(16))
        middleware = CorrelationIDMiddlewareASGI(generator=lambda: next(ids))

        async def run_request() -> tuple[str, str | None, str | None]:
            """Run one ASGI request and capture its correlation ID."""
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
            assert request_id is not None, (
                "expected request_id to be set during ASGI request but got None"
            )
            return request_id, during_request_id, correlation_id_var.get()

        results = await asyncio.gather(*(run_request() for _ in range(16)))

        expected_results = [
            (f"generated-{index}", f"generated-{index}", None) for index in range(16)
        ]
        assert results == expected_results, (
            f"expected ASGI concurrent results {expected_results!r} but got {results!r}"
        )
        assert correlation_id_var.get() is None, (
            "expected correlation_id_var.get() to be None after concurrent "
            f"requests but got {correlation_id_var.get()!r}"
        )
