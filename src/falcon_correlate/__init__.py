"""falcon-correlate package."""

from __future__ import annotations

from .celery import propagate_correlation_id_to_celery
from .httpx import (
    AsyncCorrelationIDTransport,
    CorrelationIDTransport,
    async_request_with_correlation_id,
    request_with_correlation_id,
)
from .middleware import (
    RECOMMENDED_LOG_FORMAT,
    ContextualLogFilter,
    CorrelationIDConfig,
    CorrelationIDMiddleware,
    correlation_id_var,
    default_uuid7_generator,
    default_uuid_validator,
    user_id_var,
)

PACKAGE_NAME = "falcon_correlate"

try:  # pragma: no cover - Rust optional
    rust = __import__(f"_{PACKAGE_NAME}_rs")
    hello = rust.hello
except ModuleNotFoundError:  # pragma: no cover - Python fallback
    from .pure import hello

__all__ = [
    "RECOMMENDED_LOG_FORMAT",
    "AsyncCorrelationIDTransport",
    "ContextualLogFilter",
    "CorrelationIDConfig",
    "CorrelationIDMiddleware",
    "CorrelationIDTransport",
    "async_request_with_correlation_id",
    "correlation_id_var",
    "default_uuid7_generator",
    "default_uuid_validator",
    "hello",
    "propagate_correlation_id_to_celery",
    "request_with_correlation_id",
    "user_id_var",
]
