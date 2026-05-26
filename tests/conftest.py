"""Shared pytest fixtures for falcon-correlate tests."""
# pylint: disable=too-many-arguments,too-many-positional-arguments  # Falcon WSGI and pytest fixture signatures require multiple arguments.

from __future__ import annotations

import contextvars
import typing as typ

import pytest

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    import falcon

from falcon_correlate import CorrelationIDMiddleware


class SimpleResource:
    """A simple Falcon resource for testing middleware integration."""

    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """Handle GET requests with a simple JSON response."""
        resp.media = {"message": "hello"}


class CorrelationEchoResource:
    """A Falcon resource that echoes correlation ID context."""

    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """Return correlation ID context for testing."""
        correlation_id = getattr(req.context, "correlation_id", None)
        resp.media = {
            "correlation_id": correlation_id,
            "has_correlation_id": hasattr(req.context, "correlation_id"),
        }


class TrackingMiddleware(CorrelationIDMiddleware):
    """Middleware that tracks hook invocations for testing.

    This middleware extends CorrelationIDMiddleware to record when
    process_request and process_response are called, enabling tests
    to verify middleware lifecycle behaviour.
    """

    def __init__(self, **kwargs: typ.Any) -> None:  # noqa: ANN401
        """Initialise tracking middleware with call flags reset."""
        super().__init__(**kwargs)
        self.process_request_called = False
        self.process_response_called = False

    def process_request(self, req: falcon.Request, resp: falcon.Response) -> None:
        """Track process_request invocation."""
        self.process_request_called = True
        super().process_request(req, resp)

    def process_response(
        self,
        req: falcon.Request,
        resp: falcon.Response,
        resource: object,
        req_succeeded: bool,  # noqa: FBT001 - Falcon WSGI middleware interface requirement
    ) -> None:
        """Track process_response invocation."""
        self.process_response_called = True
        super().process_response(req, resp, resource, req_succeeded)


@pytest.fixture
def isolated_context() -> cabc.Callable[[cabc.Callable[[], None]], None]:
    """Return a runner that isolates ContextVar changes per callable.

    Hypothesis and behaviour tests may execute many examples or scenarios in a
    single process. Run context-mutating callables through this fixture so
    ``correlation_id_var`` and other request-scoped ``ContextVar`` values do not
    leak between examples.

    Returns
    -------
    Callable[[Callable[[], None]], None]
        A runner that executes each callable in a copied context so
        ``ContextVar`` changes remain isolated from other examples.

    """

    def runner(func: cabc.Callable[[], None]) -> None:
        contextvars.copy_context().run(func)

    return runner
