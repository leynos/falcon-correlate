"""Shared ASGI middleware test utilities.

The lightweight request and response doubles in this module let unit and
property tests invoke ``CorrelationIDMiddlewareASGI`` hooks directly without a
Falcon ASGI application.  The async wrappers keep tests focused on middleware
lifecycle behaviour while the doubles model only the request context, header
lookup, and response-header mutation surface used by the middleware.
"""

from __future__ import annotations

import dataclasses as dc
import typing as typ

if typ.TYPE_CHECKING:
    import contextvars as cv

    import falcon.asgi

    from falcon_correlate import CorrelationIDMiddlewareASGI


@dc.dataclass(slots=True)
class _Context:
    """Minimal Falcon-like request context for direct middleware tests."""

    correlation_id: str | None = None
    _correlation_id_reset_token: cv.Token[str | None] | None = None


class _HeaderLookup:
    """Provide shared header lookup behaviour for ASGI test doubles."""

    headers: dict[str, str]

    @typ.final
    def get_header(self, name: str) -> str | None:
        """Return the named header when present."""
        return self.headers.get(name)


class _Request(_HeaderLookup):
    """Minimal ASGI request double for middleware hook tests."""

    def __init__(
        self,
        *,
        headers: dict[str, str] | None = None,
        remote_addr: str | None = "127.0.0.1",
    ) -> None:
        """Create a request double with optional headers and remote address."""
        self.context = _Context()
        self.remote_addr = remote_addr
        self.headers = headers or {}


class _Response(_HeaderLookup):
    """Minimal ASGI response double for middleware hook tests."""

    def __init__(self) -> None:
        """Create an empty response-header store."""
        self.headers: dict[str, str] = {}

    def set_header(self, name: str, value: str) -> None:
        """Record a response header."""
        self.headers[name] = value


class _HeaderFailingResponse(_Response):
    """Response double that fails during header mutation."""

    @typ.override
    def set_header(
        self,
        name: str,
        value: str,
    ) -> None:
        """Raise when middleware tries to echo the response header.

        Raises
        ------
        RuntimeError
            When the test helper intentionally exercises this failure path.

        """
        msg = f"failed to set {name}={value}"
        raise RuntimeError(msg)


def _cast_asgi_doubles(
    req: _Request,
    resp: _Response,
) -> "tuple[falcon.asgi.Request, falcon.asgi.Response]":  # ruff: ignore[quoted-annotation] -- falcon.asgi types are TYPE_CHECKING-only.
    """Cast the ASGI test doubles to Falcon request and response types."""
    return (
        typ.cast("falcon.asgi.Request", req),
        typ.cast("falcon.asgi.Response", resp),
    )


async def _process_request(
    middleware: CorrelationIDMiddlewareASGI,
    req: _Request,
    resp: _Response,
) -> None:
    """Call the public ASGI request hook with a lightweight request double."""
    cast_req, cast_resp = _cast_asgi_doubles(req, resp)
    await middleware.process_request(cast_req, cast_resp)


async def _process_response(
    middleware: CorrelationIDMiddlewareASGI,
    req: _Request,
    resp: _Response,
) -> None:
    """Call the public ASGI response hook with lightweight doubles."""
    cast_req, cast_resp = _cast_asgi_doubles(req, resp)
    await middleware.process_response(
        cast_req,
        cast_resp,
        resource=None,
        req_succeeded=True,
    )
