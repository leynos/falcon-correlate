"""Shared helpers for quickstart example tests.

The quickstart unit and behavioural suites both import the runnable modules
from ``examples/quickstart``. Keeping that import strategy here ensures both
suites exercise the same documented example boundary.
"""

from __future__ import annotations

import importlib
import typing as typ

if typ.TYPE_CHECKING:
    import types


def _load_quickstart_module(module_name: str) -> types.ModuleType:
    """Import a quickstart example module by short name.

    Returns
    -------
    types.ModuleType
        The imported example module.

    """
    return importlib.import_module(f"examples.quickstart.{module_name}")
