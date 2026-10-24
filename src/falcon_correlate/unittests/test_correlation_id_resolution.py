"""Tests for the middleware's correlation ID query and storage command."""

from __future__ import annotations

import asyncio
import contextvars
import logging
import typing as typ
from unittest import mock

import pytest

from falcon_correlate import (
    CorrelationIDMiddleware,
    CorrelationIDMiddlewareASGI,
    correlation_id_var,
)
from falcon_correlate.middleware_utils import CORRELATION_ID_RESET_TOKEN_ATTR

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    import falcon
    import falcon.asgi

    from falcon_correlate.middleware_base import _CorrelationIDMiddlewareBase

_MIDDLEWARE_TYPES: tuple[type[_CorrelationIDMiddlewareBase], ...] = (
    CorrelationIDMiddleware,
    CorrelationIDMiddlewareASGI,
)
_VALIDATION_FAILURE = "Correlation ID failed validation, generating new ID"
_VALIDATOR_WARNING = (
    "Validator raised an exception for correlation ID, treating as invalid"
)
_VALIDATION_LOGS = {
    "reject": ((logging.DEBUG, _VALIDATION_FAILURE),),
    "raise": (
        (logging.WARNING, _VALIDATOR_WARNING),
        (logging.DEBUG, _VALIDATION_FAILURE),
    ),
}


class _RequestContext:
    """Minimal mutable context object for middleware request tests."""

    def __init__(self) -> None:
        """Initialize an empty request context."""
        self.correlation_id: str | None = None


class _RequestStub:
    """Small request double with controllable header and source address."""

    def __init__(self, incoming: str | None, remote_addr: str | None) -> None:
        """Store the values returned by the request protocol methods."""
        self._incoming = incoming
        # ``None`` models Falcon exposing no source address; the production
        # trust check already accepts that defensive runtime case.
        self.remote_addr: str = typ.cast("str", remote_addr)
        self.context = _RequestContext()

    def get_header(self, name: str) -> str | None:
        """Return the configured correlation ID header value."""
        if name != "X-Correlation-ID":
            return None
        return self._incoming


def _run_in_isolated_context(callback: cabc.Callable[[], None]) -> None:
    """Run one test scenario in a fresh copy of the current context."""
    contextvars.copy_context().run(callback)


def _seed_sentinels(
    middleware: _CorrelationIDMiddlewareBase,
    req: _RequestStub,
) -> object:
    """Seed request and ContextVar state used to prove query isolation."""
    req.context.correlation_id = "request-context-sentinel"
    reset_token_sentinel = object()
    setattr(req.context, CORRELATION_ID_RESET_TOKEN_ATTR, reset_token_sentinel)
    middleware._correlation_id_var.set("contextvar-sentinel")
    return reset_token_sentinel


def _assert_sentinels_unchanged(
    middleware: _CorrelationIDMiddlewareBase,
    req: _RequestStub,
    reset_token_sentinel: object,
) -> None:
    """Assert that resolving an ID leaves every request-side sentinel alone."""
    assert req.context.correlation_id == "request-context-sentinel", (
        "expected the request correlation ID sentinel to remain unchanged"
    )
    assert (
        getattr(req.context, CORRELATION_ID_RESET_TOKEN_ATTR) is reset_token_sentinel
    ), "expected the request reset-token sentinel to remain unchanged"
    assert middleware._correlation_id_var.get() == "contextvar-sentinel", (
        "expected the ContextVar sentinel to remain unchanged"
    )


def _middleware_log_records(
    caplog: pytest.LogCaptureFixture,
) -> list[logging.LogRecord]:
    """Return records emitted through the established middleware logger."""
    return [
        record
        for record in caplog.records
        if record.name == "falcon_correlate.middleware"
    ]


@pytest.mark.parametrize(
    "middleware_type",
    _MIDDLEWARE_TYPES,
    ids=["wsgi", "asgi"],
)
@pytest.mark.parametrize(
    "case",
    [
        (None, "127.0.0.1", "accept", "generated-id", 1, 0),
        (" \t ", "127.0.0.1", "accept", "generated-id", 1, 0),
        (" \tclient-id \n", "127.0.0.1", "missing", "client-id", 0, 0),
        ("accepted-id", "127.0.0.1", "accept", "accepted-id", 0, 1),
        ("rejected-id", "127.0.0.1", "reject", "generated-id", 1, 1),
        ("validator-error-id", "127.0.0.1", "raise", "generated-id", 1, 1),
        ("untrusted-id", "203.0.113.5", "accept", "generated-id", 1, 0),
        ("missing-address-id", None, "accept", "generated-id", 1, 0),
        ("malformed-address-id", "not-an-ip-address", "accept", "generated-id", 1, 0),
    ],
    ids=[
        "missing-header",
        "whitespace-header",
        "padded-trusted-header-without-validator",
        "validator-accepts",
        "validator-rejects",
        "validator-raises",
        "untrusted-source",
        "missing-remote-address",
        "malformed-remote-address",
    ],
)
def test_resolve_correlation_id_selects_without_mutating_state(
    middleware_type: type[_CorrelationIDMiddlewareBase],
    case: tuple[str | None, str | None, str, str, int, int],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify selection, callback counts, log order, and query isolation."""
    (
        incoming,
        remote_addr,
        validator_mode,
        expected_id,
        generator_calls,
        validator_calls,
    ) = case

    def exercise() -> None:
        """Run one request-resolution case inside its isolated context."""
        generator = mock.Mock(return_value="generated-id")
        validator = mock.Mock(return_value=validator_mode == "accept")
        if validator_mode == "raise":
            validator.side_effect = RuntimeError("validator failed")

        if validator_mode == "missing":
            middleware = middleware_type(
                trusted_sources=["127.0.0.1"],
                generator=generator,
            )
        else:
            middleware = middleware_type(
                trusted_sources=["127.0.0.1"],
                generator=generator,
                validator=validator,
            )
        req = _RequestStub(incoming, remote_addr)
        reset_token_sentinel = _seed_sentinels(middleware, req)

        with caplog.at_level(logging.DEBUG, logger="falcon_correlate.middleware"):
            actual_id = middleware._resolve_correlation_id(req)

        assert actual_id == expected_id, (
            f"expected resolved ID {expected_id!r}, got {actual_id!r}"
        )
        assert generator.call_count == generator_calls, (
            f"expected exact generator call count {generator_calls}, "
            f"got {generator.call_count}"
        )
        assert validator.call_count == validator_calls, (
            f"expected exact validator call count {validator_calls}, "
            f"got {validator.call_count}"
        )
        records = _middleware_log_records(caplog)
        actual_logs = tuple((record.levelno, record.getMessage()) for record in records)
        expected_logs = _VALIDATION_LOGS.get(validator_mode, ())
        assert actual_logs == expected_logs, (
            f"expected middleware logs {expected_logs!r}, got {actual_logs!r}"
        )
        _assert_sentinels_unchanged(middleware, req, reset_token_sentinel)

    _run_in_isolated_context(exercise)


@pytest.mark.parametrize(
    "middleware_type",
    _MIDDLEWARE_TYPES,
    ids=["wsgi", "asgi"],
)
def test_resolve_correlation_id_propagates_generator_failure(
    middleware_type: type[_CorrelationIDMiddlewareBase],
) -> None:
    """Verify a raising generator propagates without changing query sentinels."""

    def exercise() -> None:
        """Run the generator failure inside its isolated context."""
        generator = mock.Mock(side_effect=RuntimeError("generator failed"))
        middleware = middleware_type(generator=generator)
        req = _RequestStub(None, "127.0.0.1")
        reset_token_sentinel = _seed_sentinels(middleware, req)

        with pytest.raises(RuntimeError, match="generator failed"):
            middleware._resolve_correlation_id(req)

        assert generator.call_count == 1, (
            f"expected generator called once, got {generator.call_count}"
        )
        _assert_sentinels_unchanged(middleware, req, reset_token_sentinel)

    _run_in_isolated_context(exercise)


@pytest.mark.parametrize(
    "middleware_type",
    _MIDDLEWARE_TYPES,
    ids=["wsgi", "asgi"],
)
@pytest.mark.parametrize("context_var_mode", ["default", "injected"])
def test_store_request_correlation_id_writes_all_request_state(
    middleware_type: type[_CorrelationIDMiddlewareBase],
    context_var_mode: str,
) -> None:
    """Verify storage updates context, ContextVar, and its reset token."""

    def exercise() -> None:
        """Run the storage command inside its isolated context."""
        injected_context_var: contextvars.ContextVar[str | None] = (
            contextvars.ContextVar("injected-correlation-id")
        )
        is_injected = context_var_mode == "injected"
        context_var = injected_context_var if is_injected else correlation_id_var
        if is_injected:
            middleware = middleware_type(
                correlation_id_context_var=injected_context_var,
            )
        else:
            middleware = middleware_type()
        req = _RequestStub(None, "127.0.0.1")

        middleware._store_request_correlation_id(req, "stored-id")

        reset_token = getattr(req.context, CORRELATION_ID_RESET_TOKEN_ATTR)
        assert req.context.correlation_id == "stored-id", (
            "expected request context to contain the selected ID"
        )
        assert context_var.get() == "stored-id", (
            "expected the configured ContextVar to contain the selected ID"
        )
        assert isinstance(reset_token, contextvars.Token), (
            "expected request context to store a ContextVar token"
        )
        assert reset_token.var is context_var, (
            "expected reset token to belong to the configured ContextVar"
        )

    _run_in_isolated_context(exercise)


def _process_public_request_hook(
    middleware: _CorrelationIDMiddlewareBase,
    middleware_type: type[_CorrelationIDMiddlewareBase],
    req: _RequestStub,
) -> None:
    """Invoke the adapter's public hook, awaiting the ASGI implementation."""
    if middleware_type is CorrelationIDMiddlewareASGI:

        async def invoke_asgi() -> None:
            """Invoke the ASGI request hook with the minimal request double."""
            asgi_middleware = typ.cast("CorrelationIDMiddlewareASGI", middleware)
            await asgi_middleware.process_request(
                typ.cast("falcon.asgi.Request", req),
                typ.cast("falcon.asgi.Response", object()),
            )

        asyncio.run(invoke_asgi())
        return

    wsgi_middleware = typ.cast("CorrelationIDMiddleware", middleware)
    wsgi_middleware.process_request(
        typ.cast("falcon.Request", req),
        typ.cast("falcon.Response", object()),
    )


@pytest.mark.parametrize(
    "middleware_type",
    _MIDDLEWARE_TYPES,
    ids=["wsgi", "asgi"],
)
def test_public_process_request_leaves_state_unchanged_when_generator_raises(
    middleware_type: type[_CorrelationIDMiddlewareBase],
) -> None:
    """Verify adapter hooks preserve request state when generation fails."""

    def exercise() -> None:
        """Run the public-hook failure inside its isolated context."""
        generator = mock.Mock(side_effect=RuntimeError("generator failed"))
        context_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
            "request-hook-context"
        )
        middleware = middleware_type(
            generator=generator,
            correlation_id_context_var=context_var,
        )
        req = _RequestStub(None, "127.0.0.1")
        req.context.correlation_id = "request-context-sentinel"
        reset_token_sentinel = object()
        setattr(req.context, CORRELATION_ID_RESET_TOKEN_ATTR, reset_token_sentinel)
        context_var.set("contextvar-sentinel")

        with pytest.raises(RuntimeError, match="generator failed"):
            _process_public_request_hook(middleware, middleware_type, req)

        assert generator.call_count == 1, (
            f"expected generator called once, got {generator.call_count}"
        )
        assert req.context.correlation_id == "request-context-sentinel", (
            "expected the request correlation ID to remain unchanged"
        )
        assert (
            getattr(req.context, CORRELATION_ID_RESET_TOKEN_ATTR)
            is reset_token_sentinel
        ), "expected the reset-token attribute to remain unchanged"
        assert context_var.get() == "contextvar-sentinel", (
            "expected the configured ContextVar to remain unchanged"
        )

    _run_in_isolated_context(exercise)
