"""falcon-correlate package."""

from __future__ import annotations

from .middleware import (
    CorrelationIDConfig,
    CorrelationIDMiddleware,
    default_uuid7_generator,
    default_uuid_validator,
)

PACKAGE_NAME = "falcon_correlate"

try:  # pragma: no cover - Rust optional
    rust = __import__(f"_{PACKAGE_NAME}_rs")
    hello = rust.hello
except ModuleNotFoundError:  # pragma: no cover - Python fallback
    from .pure import hello

__all__ = [
    "CorrelationIDConfig",
    "CorrelationIDMiddleware",
    "default_uuid7_generator",
    "default_uuid_validator",
    "hello",
]
