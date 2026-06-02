"""Property tests for Falcon ASGI middleware context invariants."""

from __future__ import annotations

import asyncio
import collections.abc as cabc  # noqa: TC003 - requested runtime import.

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from falcon_correlate import CorrelationIDMiddlewareASGI, correlation_id_var
from falcon_correlate.unittests.asgi_middleware_helpers import (
    _process_request,
    _process_response,
    _Request,
    _Response,
)


@given(task_count=st.integers(min_value=2, max_value=16))
@settings(
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_async_context_isolation_property(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    task_count: int,
) -> None:
    """Verify variable ASGI task counts keep correlation IDs isolated."""

    async def _exercise_concurrent_requests() -> None:
        middleware = CorrelationIDMiddlewareASGI(trusted_sources=["127.0.0.1"])
        all_requests_started = asyncio.Event()
        ready_count = [0]
        ready_lock = asyncio.Lock()

        async def _run_request(index: int) -> tuple[str | None, ...]:
            expected_id = f"cid-{index}"
            req = _Request(headers={"X-Correlation-ID": expected_id})
            resp = _Response()

            await _process_request(middleware, req, resp)
            context_id = req.context.correlation_id
            before_wait_id = correlation_id_var.get()

            # Keep the barrier counter protected if this helper gains awaits.
            async with ready_lock:
                ready_count[0] += 1
                if ready_count[0] == task_count:
                    all_requests_started.set()

            await asyncio.wait_for(all_requests_started.wait(), timeout=2.0)
            await asyncio.sleep(0)
            after_wait_id = correlation_id_var.get()
            await _process_response(middleware, req, resp)

            return (
                context_id,
                before_wait_id,
                after_wait_id,
                correlation_id_var.get(),
            )

        results = await asyncio.gather(
            *(_run_request(index) for index in range(task_count)),
        )
        expected_results = [
            (f"cid-{index}", f"cid-{index}", f"cid-{index}", None)
            for index in range(task_count)
        ]
        assert results == expected_results, (
            f"expected ASGI task isolation results {expected_results!r} but got "
            f"{results!r}"
        )

    isolated_context(lambda: asyncio.run(_exercise_concurrent_requests()))
    assert correlation_id_var.get() is None, (
        "expected correlation_id_var.get() to be None after property run but got "
        f"{correlation_id_var.get()!r}"
    )
