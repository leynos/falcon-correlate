"""Shared test doubles for Celery result-backend inspection tests."""

from __future__ import annotations

import logging
import typing as typ

if typ.TYPE_CHECKING:
    import pytest


class FailingBackend:
    """Backend test double whose URI inspection fails."""

    @staticmethod
    def as_uri() -> str:
        """Raise to model a temporarily unavailable backend inspection."""
        raise RuntimeError


class MalformedCeleryApp:
    """Celery-shaped app with a backend that cannot report its URI."""

    def __init__(self) -> None:
        """Initialize the backend member inspected by the helper."""
        self.backend = FailingBackend()

    @staticmethod
    def send_task(*args: object, **kwargs: object) -> object:
        """Satisfy the configured-app shape without publishing a task."""
        return None


class AppWithoutBackend:
    """Malformed app double without an optional backend attribute."""

    @staticmethod
    def send_task(*args: object, **kwargs: object) -> object:
        """Satisfy the configured-app shape without publishing a task."""
        return None


class StubCeleryApp:
    """Celery-shaped app double with a fixed backend."""

    def __init__(self, backend: object) -> None:
        """Store the backend inspected by the helper."""
        self.backend = backend

    @staticmethod
    def send_task(*args: object, **kwargs: object) -> object:
        """Satisfy the configured-app shape without publishing a task."""
        return None


class RaisingBackendPropertyApp:
    """App double whose backend access raises."""

    @property
    def backend(self) -> typ.NoReturn:
        """Raise to model an application that cannot expose its backend."""
        raise RuntimeError

    @staticmethod
    def send_task(*args: object, **kwargs: object) -> object:
        """Satisfy the configured-app shape without publishing a task."""
        return None


class RaisingUriBackend:
    """Backend double whose URI accessor raises."""

    @property
    def as_uri(self) -> str:
        """Raise to model a backend whose URI lookup fails."""
        raise RuntimeError


class StringableUri:
    """URI object that renders itself through ``str``."""

    def __init__(self, value: str) -> None:
        """Store the rendered URI value."""
        self._value = value

    def __str__(self) -> str:
        """Return the stored URI value."""
        return f"{self._value}"


def celery_debug_messages(caplog: pytest.LogCaptureFixture) -> list[str]:
    """Return debug diagnostics emitted by the Celery integration."""
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == "falcon_correlate.celery" and record.levelno == logging.DEBUG
    ]
