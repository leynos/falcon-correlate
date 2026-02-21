"""Unit tests for context variable lifecycle integration in middleware."""

from __future__ import annotations

import contextvars
import threading
import typing as typ
from concurrent.futures import ThreadPoolExecutor

import falcon
import falcon.testing
import pytest

from falcon_correlate import CorrelationIDMiddleware, correlation_id_var
from falcon_correlate.middleware import _CORRELATION_ID_RESET_TOKEN_ATTR

if typ.TYPE_CHECKING:
    import collections.abc as cabc


@pytest.fixture
def request_response_factory() -> cabc.Callable[
    ..., tuple[falcon.Request, falcon.Response]
]:
    """Create request/response objects for lifecycle tests."""

    def factory(
        *,
        correlation_id: str | None = None,
        remote_addr: str = "127.0.0.1",
    ) -> tuple[falcon.Request, falcon.Response]:
        headers: dict[str, str] | None = None
        if correlation_id is not None:
            headers = {"X-Correlation-ID": correlation_id}

        environ = falcon.testing.create_environ(
            path="/contextvar-lifecycle",
            headers=headers,
            remote_addr=remote_addr,
        )
        return falcon.Request(environ), falcon.Response()

    return factory


@pytest.fixture
def isolated_context() -> cabc.Callable[[cabc.Callable[[], None]], None]:
    """Fixture providing a fresh contextvar context for each test."""

    def runner(func: cabc.Callable[[], None]) -> None:
        contextvars.copy_context().run(func)

    return runner


class TestContextVariableLifecycle:
    """Tests for middleware-managed `correlation_id_var` lifecycle."""

    def _assert_contextvar_state(self, req: falcon.Request, expected_id: str) -> None:
        """Assert request/contextvar lifecycle state after process_request."""
        assert req.context.correlation_id == expected_id, (
            f"Expected request context correlation ID {expected_id!r}, "
            f"got {req.context.correlation_id!r}"
        )
        assert correlation_id_var.get() == expected_id, (
            f"Expected contextvar correlation ID {expected_id!r}, "
            f"got {correlation_id_var.get()!r}"
        )
        token = getattr(req.context, _CORRELATION_ID_RESET_TOKEN_ATTR, None)
        assert isinstance(token, contextvars.Token), (
            "Expected reset token on request context"
        )

    @pytest.mark.parametrize(
        "scenario",
        [
            (
                lambda: CorrelationIDMiddleware(trusted_sources=["127.0.0.1"]),
                {"correlation_id": "trusted-id"},
                "trusted-id",
            ),
            (
                lambda: CorrelationIDMiddleware(
                    trusted_sources=["127.0.0.1"],
                    generator=lambda: "generated-missing-header",
                ),
                {"correlation_id": None},
                "generated-missing-header",
            ),
            (
                lambda: CorrelationIDMiddleware(
                    trusted_sources=["127.0.0.1"],
                    generator=lambda: "generated-invalid-trusted",
                    validator=lambda _: False,
                ),
                {"correlation_id": "invalid-id"},
                "generated-invalid-trusted",
            ),
            (
                lambda: CorrelationIDMiddleware(
                    trusted_sources=["127.0.0.1"],
                    generator=lambda: "generated-untrusted",
                ),
                {
                    "correlation_id": "untrusted-id",
                    "remote_addr": "203.0.113.5",
                },
                "generated-untrusted",
            ),
        ],
        ids=[
            "trusted_source_valid_header",
            "missing_header_generates_id",
            "trusted_source_invalid_header",
            "untrusted_source_header_ignored",
        ],
    )
    def test_process_request_sets_context_var_and_stores_reset_token(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
        request_response_factory: cabc.Callable[
            ..., tuple[falcon.Request, falcon.Response]
        ],
        scenario: tuple[
            cabc.Callable[[], CorrelationIDMiddleware],
            dict[str, str | None],
            str,
        ],
    ) -> None:
        """Verify process_request sets `correlation_id_var` and stores a reset token."""
        middleware_factory, request_kwargs, expected_id = scenario

        def _inner() -> None:
            middleware = middleware_factory()
            req, resp = request_response_factory(**request_kwargs)

            middleware.process_request(req, resp)

            self._assert_contextvar_state(req, expected_id)

        isolated_context(_inner)

    @pytest.mark.parametrize(
        "req_succeeded",
        [True, False],
        ids=["successful_request", "failed_request"],
    )
    def test_process_response_resets_context_var_after_request(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
        request_response_factory: cabc.Callable[
            ..., tuple[falcon.Request, falcon.Response]
        ],
        *,
        req_succeeded: bool,
    ) -> None:
        """Verify process_response clears `correlation_id_var` for request outcomes."""
        middleware = CorrelationIDMiddleware(trusted_sources=["127.0.0.1"])

        def _inner() -> None:
            req, resp = request_response_factory(correlation_id="trusted-id")

            middleware.process_request(req, resp)
            self._assert_contextvar_state(req, "trusted-id")

            middleware.process_response(
                req,
                resp,
                resource=None,
                req_succeeded=req_succeeded,
            )

            assert correlation_id_var.get() is None, (
                "Expected correlation_id_var to be reset"
            )

        isolated_context(_inner)

    def test_process_response_is_safe_when_token_missing(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
        request_response_factory: cabc.Callable[
            ..., tuple[falcon.Request, falcon.Response]
        ],
    ) -> None:
        """Verify process_response is a no-op when no reset token is present."""
        middleware = CorrelationIDMiddleware()

        def _inner() -> None:
            req, resp = request_response_factory()

            middleware.process_response(
                req,
                resp,
                resource=None,
                req_succeeded=True,
            )

            assert correlation_id_var.get() is None, (
                "Expected correlation_id_var to remain None"
            )

        isolated_context(_inner)

    def test_process_response_is_safe_with_non_token_reset_attr(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
        request_response_factory: cabc.Callable[
            ..., tuple[falcon.Request, falcon.Response]
        ],
    ) -> None:
        """Verify process_response ignores non-Token reset attribute values."""
        middleware = CorrelationIDMiddleware()

        def _inner() -> None:
            original_token = correlation_id_var.set("original-correlation-id")
            req, resp = request_response_factory()
            non_token = object()
            setattr(req.context, _CORRELATION_ID_RESET_TOKEN_ATTR, non_token)

            middleware.process_response(
                req,
                resp,
                resource=None,
                req_succeeded=False,
            )

            assert correlation_id_var.get() == "original-correlation-id", (
                "Expected correlation_id_var to remain unchanged for "
                "non-token reset attribute"
            )
            assert (
                getattr(req.context, _CORRELATION_ID_RESET_TOKEN_ATTR) is non_token
            ), "Expected non-token reset attribute to be left untouched"
            correlation_id_var.reset(original_token)

        isolated_context(_inner)

    def test_process_response_is_safe_with_mismatched_token_var(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
        request_response_factory: cabc.Callable[
            ..., tuple[falcon.Request, falcon.Response]
        ],
    ) -> None:
        """Verify process_response ignores tokens from unrelated context variables."""
        middleware = CorrelationIDMiddleware()
        foreign_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
            "foreign",
            default=None,
        )

        def _inner() -> None:
            original_token = correlation_id_var.set("original-correlation-id")
            foreign_token = foreign_var.set("foreign-value")
            req, resp = request_response_factory()
            setattr(req.context, _CORRELATION_ID_RESET_TOKEN_ATTR, foreign_token)

            middleware.process_response(
                req,
                resp,
                resource=None,
                req_succeeded=False,
            )

            assert correlation_id_var.get() == "original-correlation-id", (
                "Expected correlation_id_var to remain unchanged for "
                "mismatched reset token"
            )
            assert (
                getattr(req.context, _CORRELATION_ID_RESET_TOKEN_ATTR) is foreign_token
            ), "Expected mismatched reset token to be preserved on request context"
            foreign_var.reset(foreign_token)
            correlation_id_var.reset(original_token)

        isolated_context(_inner)

    def test_context_is_isolated_between_concurrent_requests(
        self,
        request_response_factory: cabc.Callable[
            ..., tuple[falcon.Request, falcon.Response]
        ],
    ) -> None:
        """Verify concurrent requests do not share correlation context state."""
        middleware = CorrelationIDMiddleware(trusted_sources=["127.0.0.1"])
        barrier = threading.Barrier(2)

        def _worker(correlation_id: str) -> tuple[str | None, str | None, str | None]:
            def _inner() -> tuple[str | None, str | None, str | None]:
                req, resp = request_response_factory(correlation_id=correlation_id)

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
            assert observed_before == expected_id, (
                f"Expected pre-barrier value {expected_id!r}, got {observed_before!r}"
            )
            assert observed_after == expected_id, (
                f"Expected post-barrier value {expected_id!r}, got {observed_after!r}"
            )
            assert observed_cleared is None, (
                f"Expected cleared value None for {expected_id!r}, "
                f"got {observed_cleared!r}"
            )

        assert correlation_id_var.get() is None, (
            "Expected top-level correlation_id_var to remain None after concurrent run"
        )
