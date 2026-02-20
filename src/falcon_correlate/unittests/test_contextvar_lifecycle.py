"""Unit tests for context variable lifecycle integration in middleware."""

from __future__ import annotations

import contextvars
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable  # noqa: UP035, ICN003  # FIXME: explicit import requested

import falcon
import falcon.testing

from falcon_correlate import CorrelationIDMiddleware, correlation_id_var
from falcon_correlate.middleware import _CORRELATION_ID_RESET_TOKEN_ATTR


def _build_request_response(
    *,
    correlation_id: str | None = None,
    remote_addr: str = "127.0.0.1",
) -> tuple[falcon.Request, falcon.Response]:
    """Create request/response objects for lifecycle tests."""
    headers: dict[str, str] | None = None
    if correlation_id is not None:
        headers = {"X-Correlation-ID": correlation_id}

    environ = falcon.testing.create_environ(
        path="/contextvar-lifecycle",
        headers=headers,
        remote_addr=remote_addr,
    )
    return falcon.Request(environ), falcon.Response()


def _run_in_isolated_context(test_func: Callable[[], None]) -> None:
    """Execute test function in an isolated contextvar context.

    Ensures each test starts with a clean contextvar state and prevents
    cross-test contamination of correlation_id_var values.
    """
    contextvars.copy_context().run(test_func)


class TestContextVariableLifecycle:
    """Tests for middleware-managed `correlation_id_var` lifecycle."""

    def _assert_contextvar_state(self, req: falcon.Request, expected_id: str) -> None:
        """Assert request/contextvar lifecycle state after process_request."""
        assert req.context.correlation_id == expected_id
        assert correlation_id_var.get() == expected_id
        token = getattr(req.context, _CORRELATION_ID_RESET_TOKEN_ATTR, None)
        assert isinstance(token, contextvars.Token)

    def test_process_request_sets_context_var_and_stores_reset_token(self) -> None:
        """Verify process_request sets `correlation_id_var` and stores a reset token."""
        middleware = CorrelationIDMiddleware(trusted_sources=["127.0.0.1"])

        def _inner() -> None:
            req, resp = _build_request_response(correlation_id="trusted-id")

            middleware.process_request(req, resp)

            self._assert_contextvar_state(req, "trusted-id")

        _run_in_isolated_context(_inner)

    def test_process_request_generates_id_when_header_missing(self) -> None:
        """Verify missing header triggers generated ID and contextvar token storage."""
        middleware = CorrelationIDMiddleware(
            trusted_sources=["127.0.0.1"],
            generator=lambda: "generated-missing-header",
        )

        def _inner() -> None:
            req, resp = _build_request_response(correlation_id=None)

            middleware.process_request(req, resp)

            self._assert_contextvar_state(req, "generated-missing-header")

        _run_in_isolated_context(_inner)

    def test_process_request_replaces_invalid_id_from_trusted_source(self) -> None:
        """Verify trusted invalid IDs are replaced and lifecycle state tracks them."""
        middleware = CorrelationIDMiddleware(
            trusted_sources=["127.0.0.1"],
            generator=lambda: "generated-invalid-trusted",
            validator=lambda value: False,
        )

        def _inner() -> None:
            req, resp = _build_request_response(correlation_id="invalid-id")

            middleware.process_request(req, resp)

            self._assert_contextvar_state(req, "generated-invalid-trusted")

        _run_in_isolated_context(_inner)

    def test_process_request_ignores_valid_id_from_untrusted_source(self) -> None:
        """Verify untrusted incoming IDs are ignored and replaced."""
        middleware = CorrelationIDMiddleware(
            trusted_sources=["127.0.0.1"],
            generator=lambda: "generated-untrusted",
        )

        def _inner() -> None:
            req, resp = _build_request_response(
                correlation_id="untrusted-id",
                remote_addr="203.0.113.5",
            )

            middleware.process_request(req, resp)

            self._assert_contextvar_state(req, "generated-untrusted")

        _run_in_isolated_context(_inner)

    def test_process_response_resets_context_var_after_successful_request(self) -> None:
        """Verify process_response clears `correlation_id_var` on normal completion."""
        middleware = CorrelationIDMiddleware(trusted_sources=["127.0.0.1"])

        def _inner() -> None:
            req, resp = _build_request_response(correlation_id="trusted-id")

            middleware.process_request(req, resp)
            self._assert_contextvar_state(req, "trusted-id")

            middleware.process_response(
                req,
                resp,
                resource=None,
                req_succeeded=True,
            )

            assert correlation_id_var.get() is None

        _run_in_isolated_context(_inner)

    def test_process_response_resets_context_var_when_request_fails(self) -> None:
        """Verify cleanup runs when request processing reports failure."""
        middleware = CorrelationIDMiddleware(trusted_sources=["127.0.0.1"])

        def _inner() -> None:
            req, resp = _build_request_response(correlation_id="trusted-id")

            middleware.process_request(req, resp)
            self._assert_contextvar_state(req, "trusted-id")

            middleware.process_response(
                req,
                resp,
                resource=None,
                req_succeeded=False,
            )

            assert correlation_id_var.get() is None

        _run_in_isolated_context(_inner)

    def test_process_response_is_safe_when_token_missing(self) -> None:
        """Verify process_response is a no-op when no reset token is present."""
        middleware = CorrelationIDMiddleware()

        def _inner() -> None:
            req, resp = _build_request_response()

            middleware.process_response(
                req,
                resp,
                resource=None,
                req_succeeded=True,
            )

            assert correlation_id_var.get() is None

        _run_in_isolated_context(_inner)

    def test_process_response_is_safe_with_non_token_reset_attr(self) -> None:
        """Verify process_response ignores non-Token reset attribute values."""
        middleware = CorrelationIDMiddleware()

        def _inner() -> None:
            original_token = correlation_id_var.set("original-correlation-id")
            req, resp = _build_request_response()
            non_token = object()
            setattr(req.context, _CORRELATION_ID_RESET_TOKEN_ATTR, non_token)

            middleware.process_response(
                req,
                resp,
                resource=None,
                req_succeeded=False,
            )

            assert correlation_id_var.get() == "original-correlation-id"
            assert getattr(req.context, _CORRELATION_ID_RESET_TOKEN_ATTR) is non_token
            correlation_id_var.reset(original_token)

        _run_in_isolated_context(_inner)

    def test_process_response_is_safe_with_mismatched_token_var(self) -> None:
        """Verify process_response ignores tokens from unrelated context variables."""
        middleware = CorrelationIDMiddleware()
        foreign_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
            "foreign",
            default=None,
        )

        def _inner() -> None:
            original_token = correlation_id_var.set("original-correlation-id")
            foreign_token = foreign_var.set("foreign-value")
            req, resp = _build_request_response()
            setattr(req.context, _CORRELATION_ID_RESET_TOKEN_ATTR, foreign_token)

            middleware.process_response(
                req,
                resp,
                resource=None,
                req_succeeded=False,
            )

            assert correlation_id_var.get() == "original-correlation-id"
            assert (
                getattr(req.context, _CORRELATION_ID_RESET_TOKEN_ATTR) is foreign_token
            )
            foreign_var.reset(foreign_token)
            correlation_id_var.reset(original_token)

        _run_in_isolated_context(_inner)

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
