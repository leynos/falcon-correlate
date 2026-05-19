"""Shared fixtures for property-based tests."""

from __future__ import annotations

import contextvars
import typing as typ

import pytest

if typ.TYPE_CHECKING:
    import collections.abc as cabc


@pytest.fixture
def isolated_context() -> cabc.Callable[[cabc.Callable[[], None]], None]:
    """Return a runner that isolates ContextVar changes per callable.

    Hypothesis runs each property many times, so context variables must not
    leak between examples or concurrent tests. Use this fixture to run a
    zero-argument callable inside ``contextvars.copy_context().run``::

        isolated_context(lambda: correlation_id_var.set("example"))

    """

    def runner(func: cabc.Callable[[], None]) -> None:
        """Run *func* inside a copied contextvars context."""
        contextvars.copy_context().run(func)

    return runner
