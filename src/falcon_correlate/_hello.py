"""Resolve the ``hello`` greeting from the Rust extension or pure Python.

The optional compiled extension ``_falcon_correlate_rs`` is preferred when it is
importable; otherwise the pure-Python implementation is used as a fallback.
"""

from __future__ import annotations

PACKAGE_NAME = "falcon_correlate"

try:  # pragma: no cover - Rust optional
    rust = __import__(f"_{PACKAGE_NAME}_rs")
    hello = rust.hello
except ModuleNotFoundError:  # pragma: no cover - Python fallback
    from .pure import hello

__all__ = ["PACKAGE_NAME", "hello"]
