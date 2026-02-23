"""Unit tests for req.context and contextvar dual-access parity.

This module verifies that ``req.context.correlation_id`` and
``correlation_id_var.get()`` always return the same value after
``CorrelationIDMiddleware.process_request`` executes, across all
correlation-ID selection paths and under concurrent request handling.

Examples
--------
Run the tests in this module with pytest::

    pytest src/falcon_correlate/unittests/test_req_context_integration.py -v

Notes
-----
These tests exercise the middleware directly (without a full Falcon
``App``) using the ``request_response_factory`` and ``isolated_context``
fixtures from ``conftest.py``.  No production code changes are needed;
the middleware already sets both access paths in ``process_request``.

"""

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
    """Tests proving req.context.correlation_id and correlation_id_var parity.

    Each test invokes ``CorrelationIDMiddleware.process_request`` and
    asserts that ``req.context.correlation_id`` equals
    ``correlation_id_var.get()`` for the same request, covering every
    correlation-ID selection path and concurrent-request isolation.

    Notes
    -----
    The parametrized test covers four selection paths: generated ID (no
    incoming header), trusted incoming ID, untrusted source rejection,
    and validator rejection.  The concurrency test uses a
    ``ThreadPoolExecutor`` with a ``Barrier`` to force overlapping
    execution windows.

    """

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
        """Verify req.context.correlation_id matches correlation_id_var.get().

        Parameters
        ----------
        isolated_context : cabc.Callable
            Fixture that runs a zero-argument callable inside a fresh
            ``contextvars.Context`` to prevent cross-test leakage.
        request_response_factory : cabc.Callable
            Fixture that builds ``(Request, Response)`` pairs from
            keyword arguments such as ``correlation_id`` and
            ``remote_addr``.
        scenario : tuple
            A three-element tuple of (*middleware_factory*,
            *request_kwargs*, *expected_id*) where *middleware_factory*
            is a callable returning a ``CorrelationIDMiddleware``
            instance, *request_kwargs* is a dict passed to
            ``request_response_factory``, and *expected_id* is the
            correlation ID both access paths should return.

        """
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

    @staticmethod
    def _execute_concurrent_request(
        middleware: CorrelationIDMiddleware,
        barrier: threading.Barrier,
        request_response_factory: cabc.Callable[
            ..., tuple[falcon.Request, falcon.Response]
        ],
        correlation_id: str,
    ) -> tuple[str | None, str | None, str | None, bool, bool]:
        """Run a single concurrent request inside an isolated context.

        Parameters
        ----------
        middleware : CorrelationIDMiddleware
            The middleware instance shared across concurrent workers.
        barrier : threading.Barrier
            Barrier used to synchronise workers so their contexts
            overlap.
        request_response_factory : cabc.Callable
            Fixture that builds ``(Request, Response)`` pairs from
            keyword arguments.
        correlation_id : str
            The correlation ID to send as a trusted incoming header.

        Returns
        -------
        tuple[str | None, str | None, str | None, bool, bool]
            ``(req_context_value, pre_barrier_contextvar,
            post_barrier_contextvar, pre_parity, post_parity)``.

        """

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

    @staticmethod
    def _validate_concurrent_results(
        request_ids: list[str],
        results: list[tuple[str | None, str | None, str | None, bool, bool]],
    ) -> None:
        """Assert that each concurrent result shows correct parity.

        Parameters
        ----------
        request_ids : list[str]
            The correlation IDs that were sent.
        results : list[tuple]
            Worker results to validate, one per request ID.

        """
        for expected_id, (
            req_ctx,
            pre_ctx_var,
            post_ctx_var,
            pre_parity,
            post_parity,
        ) in zip(request_ids, results, strict=True):
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

    def test_dual_access_parity_across_concurrent_requests(
        self,
        request_response_factory: cabc.Callable[
            ..., tuple[falcon.Request, falcon.Response]
        ],
    ) -> None:
        """Verify concurrent requests each observe matching dual-access values.

        Two requests with distinct trusted correlation IDs are dispatched
        concurrently via ``ThreadPoolExecutor``.  A ``Barrier`` forces both
        threads to overlap, then each thread re-reads its ``ContextVar``
        to confirm isolation holds under true concurrency.

        Parameters
        ----------
        request_response_factory : cabc.Callable
            Fixture that builds ``(Request, Response)`` pairs from
            keyword arguments such as ``correlation_id`` and
            ``remote_addr``.

        """
        middleware = CorrelationIDMiddleware(trusted_sources=["127.0.0.1"])
        barrier = threading.Barrier(2)
        request_ids = ["concurrent-a", "concurrent-b"]

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda cid: self._execute_concurrent_request(
                        middleware,
                        barrier,
                        request_response_factory,
                        cid,
                    ),
                    request_ids,
                ),
            )

        self._validate_concurrent_results(request_ids, results)
