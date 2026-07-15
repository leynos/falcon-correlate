"""Property tests for middleware lifecycle invariants.

Hypothesis-generated inputs exercise request selection across trust and
validation combinations, response cleanup when echo handlers raise, and
context isolation across concurrent middleware lifecycles. These properties
guard the request/response invariants that fixed examples can miss.
"""

from __future__ import annotations

import contextvars
import threading
import typing as typ
from concurrent.futures import ThreadPoolExecutor

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from falcon_correlate import CorrelationIDMiddleware, correlation_id_var
from falcon_correlate.middleware import _CORRELATION_ID_RESET_TOKEN_ATTR

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    import falcon


_ID_TEXT = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cc", "Cs"),
        blacklist_characters="\r\n",
    ),
    min_size=1,
    max_size=24,
)
_HEADER_TEXT = _ID_TEXT.filter(lambda value: bool(value.strip()))
_HEADER_OR_EMPTY = st.one_of(st.none(), st.just(""), st.just("   "), _HEADER_TEXT)


class _PropertyResponse:
    """Small response double with optional header mutation failure."""

    def __init__(self, *, should_fail: bool = False) -> None:
        """Initialize the test double."""
        self.headers: dict[str, str] = {}
        self.should_fail = should_fail

    def set_header(self, name: str, value: str) -> None:
        """Record a response header or raise when configured to fail."""
        if self.should_fail:
            msg = f"failed to set {name}={value}"
            raise RuntimeError(msg)
        self.headers[name] = value

    def get_header(self, name: str) -> str | None:
        """Return a recorded response header."""
        return self.headers.get(name)


def _expected_correlation_id(
    *,
    incoming: str | None,
    is_trusted: bool,
    validator_mode: str,
    generated_id: str,
) -> str:
    """Return the expected request correlation ID for a generated scenario."""
    normalized = incoming.strip() if incoming is not None else None
    if not normalized or not is_trusted:
        return generated_id
    if validator_mode in {"missing", "accept"}:
        return normalized
    return generated_id


def _validator_for(mode: str) -> cabc.Callable[[str], bool] | None:
    """Build a validator matching the generated validation mode."""
    if mode == "missing":
        return None
    if mode == "accept":
        return lambda _value: True
    if mode == "reject":
        return lambda _value: False

    def _raise(_value: str) -> bool:
        """Raise the configured validation exception."""
        msg = "validator failed"
        raise RuntimeError(msg)

    return _raise


class _RequestSelectionScenario(typ.NamedTuple):
    """Hypothesis-generated scenario for request correlation ID selection."""

    incoming: str | None
    is_trusted: bool
    validator_mode: str
    generated_id: str


@st.composite
def _request_selection_scenarios(
    draw: "st.DrawFn",  # noqa: UP037 -- st.DrawFn is not runtime-stable.
) -> _RequestSelectionScenario:
    """Composite Hypothesis strategy for request-selection property scenarios."""
    return _RequestSelectionScenario(
        incoming=draw(_HEADER_OR_EMPTY),
        is_trusted=draw(st.booleans()),
        validator_mode=draw(st.sampled_from(["missing", "accept", "reject", "raise"])),
        generated_id=draw(_ID_TEXT),
    )


@given(scenario=_request_selection_scenarios())
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_process_request_selection_property(
    request_response_factory: cabc.Callable[..., tuple[typ.Any, typ.Any]],
    scenario: _RequestSelectionScenario,
) -> None:
    """Verify request ID selection across trust and validator combinations."""
    remote_addr = "127.0.0.1" if scenario.is_trusted else "203.0.113.5"
    trusted_sources = ["127.0.0.1"]
    middleware = CorrelationIDMiddleware(
        trusted_sources=trusted_sources,
        generator=lambda: scenario.generated_id,
        validator=_validator_for(scenario.validator_mode),
    )
    req, resp = request_response_factory(
        correlation_id=scenario.incoming,
        remote_addr=remote_addr,
    )

    context = contextvars.copy_context()
    context.run(middleware.process_request, req, resp)
    expected = _expected_correlation_id(
        incoming=scenario.incoming,
        is_trusted=scenario.is_trusted,
        validator_mode=scenario.validator_mode,
        generated_id=scenario.generated_id,
    )

    assert req.context.correlation_id == expected, (
        f"expected req.context.correlation_id to be {expected!r} but got "
        f"{req.context.correlation_id!r}"
    )
    assert context.run(correlation_id_var.get) == expected, (
        f"expected correlation_id_var.get() to be {expected!r} but got "
        f"{context.run(correlation_id_var.get)!r}"
    )

    context.run(
        middleware.process_response,
        req,
        resp,
        None,
        True,  # noqa: FBT003 - Falcon middleware hook receives positional bool
    )
    assert context.run(correlation_id_var.get) is None, (
        "expected correlation_id_var.get() to be None after response but got "
        f"{context.run(correlation_id_var.get)!r}"
    )


@given(
    should_fail=st.booleans(),
    correlation_id=_ID_TEXT,
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_process_response_cleanup_property(
    request_response_factory: cabc.Callable[..., tuple[typ.Any, typ.Any]],
    should_fail: bool,  # noqa: FBT001 - generated property input
    correlation_id: str,
) -> None:
    """Verify response cleanup runs whether header echo succeeds or raises."""
    middleware = CorrelationIDMiddleware(
        trusted_sources=["127.0.0.1"],
        generator=lambda: "unused-generated-id",
    )
    req, _resp = request_response_factory(correlation_id=correlation_id)
    resp = _PropertyResponse(should_fail=should_fail)
    expected_id = correlation_id.strip() or "unused-generated-id"

    def _inner() -> None:
        """Exercise the request lifecycle inside an isolated context."""
        response = typ.cast("falcon.Response", resp)
        middleware.process_request(req, response)
        if should_fail:
            with pytest.raises(RuntimeError, match="failed to set"):
                middleware.process_response(
                    req,
                    response,
                    None,
                    True,  # noqa: FBT003 - Falcon middleware hook receives positional bool
                )
        else:
            middleware.process_response(
                req,
                response,
                None,
                True,  # noqa: FBT003 - Falcon middleware hook receives positional bool
            )
            assert resp.get_header("X-Correlation-ID") == expected_id, (
                "expected response header to equal selected correlation ID "
                f"{expected_id!r} but got "
                f"{resp.get_header('X-Correlation-ID')!r}"
            )

        assert correlation_id_var.get() is None, (
            "expected correlation_id_var.get() to be None after response but got "
            f"{correlation_id_var.get()!r}"
        )
        assert getattr(req.context, _CORRELATION_ID_RESET_TOKEN_ATTR, None) is None, (
            "expected reset token attribute to be None after response but got "
            f"{getattr(req.context, _CORRELATION_ID_RESET_TOKEN_ATTR, None)!r}"
        )

    contextvars.copy_context().run(_inner)


@given(task_count=st.integers(min_value=1, max_value=8))
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_concurrent_context_isolation_property(
    request_response_factory: cabc.Callable[..., tuple[typ.Any, typ.Any]],
    task_count: int,
) -> None:
    """Verify arbitrary concurrent request counts keep correlation IDs isolated."""
    middleware = CorrelationIDMiddleware(trusted_sources=["127.0.0.1"])
    barrier = threading.Barrier(task_count)

    def _worker(index: int) -> tuple[str | None, str | None, str | None]:
        """Run one concurrent request scenario."""

        def _inner() -> tuple[str | None, str | None, str | None]:
            """Exercise the request lifecycle inside an isolated context."""
            correlation_id = f"cid-{index}"
            req, resp = request_response_factory(correlation_id=correlation_id)
            middleware.process_request(req, resp)
            before = correlation_id_var.get()
            barrier.wait(timeout=2.0)
            during = correlation_id_var.get()
            middleware.process_response(
                req,
                resp,
                None,
                True,  # noqa: FBT003 - Falcon middleware hook receives positional bool
            )
            return before, during, correlation_id_var.get()

        return contextvars.copy_context().run(_inner)

    with ThreadPoolExecutor(max_workers=task_count) as executor:
        results = list(executor.map(_worker, range(task_count)))

    expected = [(f"cid-{index}", f"cid-{index}", None) for index in range(task_count)]
    assert results == expected, (
        f"expected concurrent isolation results {expected!r} but got {results!r}"
    )
