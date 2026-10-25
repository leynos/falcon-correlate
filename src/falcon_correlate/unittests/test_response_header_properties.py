"""Property tests for concurrent response-header lifecycle invariants."""

from __future__ import annotations

import contextvars
import threading
import typing as typ
from concurrent.futures import ThreadPoolExecutor

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from falcon_correlate import CorrelationIDMiddleware, correlation_id_var

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    import falcon


_CORRELATION_ID_SUFFIX = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
    min_size=1,
    max_size=8,
)


@given(
    task_count=st.integers(min_value=2, max_value=8),
    id_suffix=_CORRELATION_ID_SUFFIX,
)
@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_response_header_isolation_across_concurrent_request_counts(
    request_response_factory: cabc.Callable[
        ..., tuple[falcon.Request, falcon.Response]
    ],
    task_count: int,
    id_suffix: str,
) -> None:
    """Verify concurrent response headers remain isolated across request counts."""
    middleware = CorrelationIDMiddleware(trusted_sources=["127.0.0.1"])
    barrier = threading.Barrier(task_count)
    request_ids = [f"request-{id_suffix}-{index}" for index in range(task_count)]

    def _worker(correlation_id: str) -> tuple[str | None, str | None]:
        """Run one generated request through the shared middleware."""

        def _inner() -> tuple[str | None, str | None]:
            """Process a response inside its copied context."""
            req, resp = request_response_factory(correlation_id=correlation_id)
            middleware.process_request(req, resp)
            barrier.wait(timeout=2.0)
            middleware.process_response(
                req,
                resp,
                resource=None,
                req_succeeded=True,
            )
            barrier.wait(timeout=2.0)
            return resp.get_header("X-Correlation-ID"), correlation_id_var.get()

        return contextvars.copy_context().run(_inner)

    with ThreadPoolExecutor(max_workers=task_count) as executor:
        results = list(executor.map(_worker, request_ids))

    echoed_headers: list[str | None] = []
    for expected_id, (echoed_header, context_after_response) in zip(
        request_ids,
        results,
        strict=True,
    ):
        other_ids = set(request_ids) - {expected_id}
        assert echoed_header not in other_ids, (
            f"Cross-request header contamination for {expected_id!r}: "
            f"received {echoed_header!r}"
        )
        assert echoed_header == expected_id, (
            f"Expected echoed header {expected_id!r}, got {echoed_header!r}"
        )
        assert context_after_response is None, (
            f"Expected cleared context for {expected_id!r}, "
            f"got {context_after_response!r}"
        )
        echoed_headers.append(echoed_header)

    assert set(echoed_headers) == set(request_ids), (
        f"Expected distinct echoed headers {set(request_ids)!r}, "
        f"got {set(echoed_headers)!r}"
    )
    assert correlation_id_var.get() is None, (
        "Expected top-level correlation_id_var to remain None after concurrent run"
    )
