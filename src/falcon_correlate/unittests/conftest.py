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
logger_with_capture
    Factory callable that creates a named logger with a
    ``ContextualLogFilter``-equipped ``StreamHandler`` and yields the
    ``(logging.Logger, io.StringIO)`` pair, cleaning up the handler on
    exit.

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

Build a logger with contextual log capture::

    def test_logger(logger_with_capture):
        test_logger, stream = logger_with_capture("my_test_logger")
        test_logger.info("hello")
        assert "hello" in stream.getvalue()

"""

from __future__ import annotations

import contextvars
import io
import logging
import typing as typ

import falcon
import falcon.testing
import pytest

from falcon_correlate import ContextualLogFilter

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


_CTX_LOG_FORMAT = "[%(correlation_id)s][%(user_id)s] %(message)s"


@pytest.fixture
def logger_with_capture() -> cabc.Generator[
    cabc.Callable[[str], tuple[logging.Logger, io.StringIO]], None, None
]:
    """Provide a factory for loggers with ``ContextualLogFilter`` capture.

    Each call to the returned factory creates a named logger backed by a
    ``StreamHandler`` writing to a fresh ``io.StringIO``.  The handler
    uses a ``ContextualLogFilter`` and the standard
    ``[%(correlation_id)s][%(user_id)s] %(message)s`` format string.

    All handlers added via the factory are removed automatically when
    the fixture tears down, preventing inter-test handler leakage.

    Yields
    ------
    cabc.Callable[[str], tuple[logging.Logger, io.StringIO]]
        A factory accepting a logger *name* and returning a
        ``(logging.Logger, io.StringIO)`` pair.

    """
    cleanup: list[tuple[logging.Logger, logging.Handler, bool, int]] = []

    def factory(name: str) -> tuple[logging.Logger, io.StringIO]:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter(_CTX_LOG_FORMAT))
        handler.addFilter(ContextualLogFilter())

        test_logger = logging.getLogger(name)
        original_propagate = test_logger.propagate
        original_level = test_logger.level
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.INFO)
        test_logger.propagate = False
        cleanup.append((test_logger, handler, original_propagate, original_level))
        return test_logger, stream

    yield factory

    for lgr, hdlr, orig_propagate, orig_level in cleanup:
        lgr.removeHandler(hdlr)
        lgr.propagate = orig_propagate
        lgr.setLevel(orig_level)
