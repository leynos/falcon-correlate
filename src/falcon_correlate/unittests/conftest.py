"""Shared pytest fixtures for falcon-correlate unit tests."""

from __future__ import annotations

import contextvars
import typing as typ

import falcon
import falcon.testing
import pytest

if typ.TYPE_CHECKING:
    import collections.abc as cabc


@pytest.fixture
def request_response_factory() -> cabc.Callable[
    ..., tuple[falcon.Request, falcon.Response]
]:
    """Create request/response objects for middleware unit tests."""

    def factory(
        *,
        correlation_id: str | None = None,
        remote_addr: str = "127.0.0.1",
    ) -> tuple[falcon.Request, falcon.Response]:
        headers: dict[str, str] | None = None
        if correlation_id is not None:
            headers = {"X-Correlation-ID": correlation_id}

        environ = falcon.testing.create_environ(
            path="/test",
            headers=headers,
            remote_addr=remote_addr,
        )
        return falcon.Request(environ), falcon.Response()

    return factory


@pytest.fixture
def isolated_context() -> cabc.Callable[[cabc.Callable[[], None]], None]:
    """Provide a fresh contextvar context to prevent cross-test leakage."""

    def runner(func: cabc.Callable[[], None]) -> None:
        contextvars.copy_context().run(func)

    return runner
