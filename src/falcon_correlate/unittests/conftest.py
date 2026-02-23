"""Shared pytest fixtures for falcon-correlate unit tests.

This module provides common fixtures used across the ``falcon_correlate``
unit-test suite, avoiding duplication of request/response factory helpers
and context-isolation utilities.

Fixtures
--------
request_response_factory
    Factory callable that builds ``falcon.Request`` / ``falcon.Response``
    pairs from keyword arguments (``correlation_id``, ``remote_addr``).
isolated_context
    Runner callable that executes a zero-argument function inside a fresh
    ``contextvars.Context``, preventing cross-test leakage.

Usage
-----
Fixtures are discovered automatically by pytest when test modules reside
under ``src/falcon_correlate/unittests/``.  No explicit import is needed::

    def test_example(request_response_factory, isolated_context):
        req, resp = request_response_factory(correlation_id="abc")
        ...

Examples
--------
Create a request/response pair with an incoming correlation ID header::

    def test_with_header(request_response_factory):
        req, resp = request_response_factory(correlation_id="test-id")
        assert req.get_header("X-Correlation-ID") == "test-id"

Run a callable in an isolated context to avoid contextvar bleed::

    def test_isolated(isolated_context):
        def _inner():
            correlation_id_var.set("isolated")
            assert correlation_id_var.get() == "isolated"

        isolated_context(_inner)

"""

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
    """Create request/response objects for middleware unit tests.

    Returns
    -------
    cabc.Callable[..., tuple[falcon.Request, falcon.Response]]
        A factory callable accepting the following keyword arguments:

        correlation_id : str | None
            Value for the ``X-Correlation-ID`` request header.  When
            ``None`` (the default), no header is added.
        remote_addr : str
            Simulated client IP address.  Defaults to ``"127.0.0.1"``.

        The callable returns a ``(falcon.Request, falcon.Response)`` tuple
        constructed via ``falcon.testing.create_environ``.

    """

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
    """Provide a fresh contextvar context to prevent cross-test leakage.

    Returns
    -------
    cabc.Callable[[cabc.Callable[[], None]], None]
        A runner callable that accepts a zero-argument function and
        executes it inside a ``contextvars.copy_context().run()`` call,
        ensuring that any ``ContextVar`` mutations are isolated from
        other tests.

    """

    def runner(func: cabc.Callable[[], None]) -> None:
        contextvars.copy_context().run(func)

    return runner
