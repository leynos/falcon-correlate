"""Structural typing protocols shared by the WSGI and ASGI middleware.

These protocols describe the narrow request/response surface the
correlation ID middleware relies on, so the shared lifecycle base can
be typed against either Falcon flavour.
"""

from __future__ import annotations

import typing as typ


class _RequestLike(typ.Protocol):
    """Small request surface shared by Falcon WSGI and ASGI."""

    context: typ.Any

    @property
    def remote_addr(self) -> str:
        """IP address of the request source.

        Declared as a read-only property: the middleware only reads
        this attribute, and Falcon's ``Request.remote_addr`` is itself
        a read-only property, so a mutable protocol member would
        (correctly) fail to match it under ty >= 0.0.57.
        """

    def get_header(self, name: str) -> str | None:
        """Return a request header by name."""


class _ResponseLike(typ.Protocol):
    """Small response surface shared by Falcon WSGI and ASGI."""

    def set_header(self, name: str, value: str) -> None:
        """Set a response header."""
