"""Shared fixtures for the behavioural test suite.

Every scenario collected under ``tests/bdd`` runs with
``correlation_id_var`` and ``user_id_var`` bound to ``None``, and leaves the
ambient values it found in place afterwards. Step modules must not redefine
``_reset_context_variables``; keep only feature-specific cleanup (structlog
configuration, logger handlers, Celery signal registration, and the Celery
token store) in step modules, and make any local fixture that touches context
state depend explicitly on ``_reset_context_variables``.
"""

from __future__ import annotations

import contextlib
import typing as typ

import pytest

if typ.TYPE_CHECKING:
    import collections.abc as cabc

from falcon_correlate import correlation_id_var, user_id_var


@contextlib.contextmanager
def isolated_context_variables() -> cabc.Generator[None, None, None]:
    """Bind both public context variables to ``None`` for the block.

    Yields
    ------
    None
        Control while ``correlation_id_var`` and ``user_id_var`` read as
        ``None``. The ambient values are restored on exit, including when the
        block raises.

    """
    correlation_token = correlation_id_var.set(None)
    user_id_token = user_id_var.set(None)
    try:
        yield
    finally:
        user_id_var.reset(user_id_token)
        correlation_id_var.reset(correlation_token)


@pytest.fixture(autouse=True)
def _reset_context_variables() -> cabc.Generator[None, None, None]:
    """Give every BDD scenario a clean context and restore ambient values."""
    with isolated_context_variables():
        yield
