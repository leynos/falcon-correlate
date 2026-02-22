"""Unit tests for req.context and contextvar dual-access parity."""

from __future__ import annotations

import contextvars
import threading
import typing as typ
from concurrent.futures import ThreadPoolExecutor

import pytest

from falcon_correlate import CorrelationIDMiddleware, correlation_id_var

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    import falcon


class TestReqContextIntegration:
    """Tests proving req.context.correlation_id and correlation_id_var parity."""

    @pytest.mark.parametrize(
        "scenario",
        [
            (
                lambda: CorrelationIDMiddleware(
                    generator=lambda: "generated-no-header",
                ),
                {"correlation_id": None},
                "generated-no-header",
            ),
            (
                lambda: CorrelationIDMiddleware(
                    trusted_sources=["127.0.0.1"],
                ),
                {"correlation_id": "trusted-incoming-id"},
                "trusted-incoming-id",
            ),
            (
                lambda: CorrelationIDMiddleware(
                    trusted_sources=["127.0.0.1"],
                    generator=lambda: "generated-untrusted",
                ),
                {
                    "correlation_id": "untrusted-incoming-id",
                    "remote_addr": "203.0.113.5",
                },
                "generated-untrusted",
            ),
            (
                lambda: CorrelationIDMiddleware(
                    trusted_sources=["127.0.0.1"],
                    generator=lambda: "generated-rejected",
                    validator=lambda _: False,
                ),
                {"correlation_id": "rejected-incoming-id"},
                "generated-rejected",
            ),
        ],
        ids=[
            "generated_id_no_header",
            "trusted_incoming_id",
            "untrusted_source_rejected",
            "validator_rejects_incoming",
        ],
    )
    def test_req_context_matches_contextvar(
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
        """Verify req.context.correlation_id matches correlation_id_var.get()."""
        middleware_factory, request_kwargs, expected_id = scenario

        def _inner() -> None:
            middleware = middleware_factory()
            req, resp = request_response_factory(**request_kwargs)

            middleware.process_request(req, resp)

            assert req.context.correlation_id == expected_id, (
                f"Expected req.context.correlation_id {expected_id!r}, "
                f"got {req.context.correlation_id!r}"
            )
            assert correlation_id_var.get() == expected_id, (
                f"Expected correlation_id_var {expected_id!r}, "
                f"got {correlation_id_var.get()!r}"
            )
            assert req.context.correlation_id == correlation_id_var.get(), (
                "req.context.correlation_id and correlation_id_var.get() "
                "must always return the same value"
            )

        isolated_context(_inner)

    def test_dual_access_parity_across_concurrent_requests(
        self,
        request_response_factory: cabc.Callable[
            ..., tuple[falcon.Request, falcon.Response]
        ],
    ) -> None:
        """Verify concurrent requests each observe matching dual-access values."""
        middleware = CorrelationIDMiddleware(trusted_sources=["127.0.0.1"])
        barrier = threading.Barrier(2)

        def _worker(
            correlation_id: str,
        ) -> tuple[str | None, str | None, str | None, bool, bool]:
            def _inner() -> tuple[str | None, str | None, str | None, bool, bool]:
                req, resp = request_response_factory(
                    correlation_id=correlation_id,
                )

                middleware.process_request(req, resp)
                req_context_value = req.context.correlation_id
                pre_barrier_contextvar = correlation_id_var.get()
                # Wait for both threads to reach this point so their
                # contexts overlap.
                barrier.wait(timeout=2.0)
                # Re-read contextvar after overlap to verify isolation
                # holds under true concurrency.
                post_barrier_contextvar = correlation_id_var.get()

                pre_parity = req_context_value == pre_barrier_contextvar
                post_parity = req_context_value == post_barrier_contextvar

                middleware.process_response(
                    req,
                    resp,
                    resource=None,
                    req_succeeded=True,
                )
                return (
                    req_context_value,
                    pre_barrier_contextvar,
                    post_barrier_contextvar,
                    pre_parity,
                    post_parity,
                )

            return contextvars.copy_context().run(_inner)

        request_ids = ["concurrent-a", "concurrent-b"]
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(_worker, request_ids))

        for expected_id, (
            req_ctx,
            pre_ctx_var,
            post_ctx_var,
            pre_parity,
            post_parity,
        ) in zip(
            request_ids,
            results,
            strict=True,
        ):
            assert req_ctx == expected_id, (
                f"Expected req.context value {expected_id!r}, got {req_ctx!r}"
            )
            assert pre_ctx_var == expected_id, (
                f"Expected pre-barrier contextvar {expected_id!r}, got {pre_ctx_var!r}"
            )
            assert post_ctx_var == expected_id, (
                f"Expected post-barrier contextvar {expected_id!r}, "
                f"got {post_ctx_var!r}"
            )
            assert pre_parity, f"Pre-barrier parity failed for {expected_id!r}"
            assert post_parity, f"Post-barrier parity failed for {expected_id!r}"
