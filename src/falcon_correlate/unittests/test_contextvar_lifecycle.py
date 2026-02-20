"""Unit tests for context variable lifecycle integration in middleware."""

from __future__ import annotations

import contextvars
import threading
from concurrent.futures import ThreadPoolExecutor

import falcon
import falcon.testing

from falcon_correlate import CorrelationIDMiddleware, correlation_id_var

_RESET_TOKEN_ATTR = "_correlation_id_reset_token"  # noqa: S105


def _build_request_response(
    *,
    correlation_id: str,
) -> tuple[falcon.Request, falcon.Response]:
    """Create request/response objects with an incoming correlation ID header."""
    environ = falcon.testing.create_environ(
        path="/contextvar-lifecycle",
        headers={"X-Correlation-ID": correlation_id},
    )
    return falcon.Request(environ), falcon.Response()


class TestContextVariableLifecycle:
    """Tests for middleware-managed `correlation_id_var` lifecycle."""

    def test_process_request_sets_context_var_and_stores_reset_token(self) -> None:
        """Verify process_request sets `correlation_id_var` and stores a reset token."""
        middleware = CorrelationIDMiddleware(trusted_sources=["127.0.0.1"])

        def _inner() -> None:
            req, resp = _build_request_response(correlation_id="trusted-id")

            middleware.process_request(req, resp)

            assert req.context.correlation_id == "trusted-id"
            assert correlation_id_var.get() == "trusted-id"
            token = getattr(req.context, _RESET_TOKEN_ATTR, None)
            assert isinstance(token, contextvars.Token)

        contextvars.copy_context().run(_inner)

    def test_process_response_resets_context_var_after_successful_request(self) -> None:
        """Verify process_response clears `correlation_id_var` on normal completion."""
        middleware = CorrelationIDMiddleware(trusted_sources=["127.0.0.1"])

        def _inner() -> None:
            req, resp = _build_request_response(correlation_id="trusted-id")

            middleware.process_request(req, resp)
            assert correlation_id_var.get() == "trusted-id"

            middleware.process_response(
                req,
                resp,
                resource=None,
                req_succeeded=True,
            )

            assert correlation_id_var.get() is None

        contextvars.copy_context().run(_inner)

    def test_process_response_resets_context_var_when_request_fails(self) -> None:
        """Verify cleanup runs when request processing reports failure."""
        middleware = CorrelationIDMiddleware(trusted_sources=["127.0.0.1"])

        def _inner() -> None:
            req, resp = _build_request_response(correlation_id="trusted-id")

            middleware.process_request(req, resp)
            assert correlation_id_var.get() == "trusted-id"

            middleware.process_response(
                req,
                resp,
                resource=None,
                req_succeeded=False,
            )

            assert correlation_id_var.get() is None

        contextvars.copy_context().run(_inner)

    def test_process_response_is_safe_when_token_missing(self) -> None:
        """Verify process_response is a no-op when no reset token is present."""
        middleware = CorrelationIDMiddleware()

        def _inner() -> None:
            environ = falcon.testing.create_environ(path="/contextvar-lifecycle")
            req = falcon.Request(environ)
            resp = falcon.Response()

            middleware.process_response(
                req,
                resp,
                resource=None,
                req_succeeded=True,
            )

            assert correlation_id_var.get() is None

        contextvars.copy_context().run(_inner)

    def test_context_is_isolated_between_concurrent_requests(self) -> None:
        """Verify concurrent requests do not share correlation context state."""
        middleware = CorrelationIDMiddleware(trusted_sources=["127.0.0.1"])
        barrier = threading.Barrier(2)

        def _worker(correlation_id: str) -> tuple[str | None, str | None, str | None]:
            def _inner() -> tuple[str | None, str | None, str | None]:
                req, resp = _build_request_response(correlation_id=correlation_id)

                middleware.process_request(req, resp)
                observed_before = correlation_id_var.get()
                barrier.wait(timeout=2.0)
                observed_after = correlation_id_var.get()

                middleware.process_response(
                    req,
                    resp,
                    resource=None,
                    req_succeeded=True,
                )
                observed_cleared = correlation_id_var.get()
                return observed_before, observed_after, observed_cleared

            return contextvars.copy_context().run(_inner)

        request_ids = ["request-a", "request-b"]
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(_worker, request_ids))

        for expected_id, (observed_before, observed_after, observed_cleared) in zip(
            request_ids,
            results,
            strict=True,
        ):
            assert observed_before == expected_id
            assert observed_after == expected_id
            assert observed_cleared is None

        assert correlation_id_var.get() is None
