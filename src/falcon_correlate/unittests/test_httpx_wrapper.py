"""Unit tests for sync httpx correlation ID wrapper functions."""

from __future__ import annotations

import types
import typing as typ

import pytest

httpx = pytest.importorskip("httpx")

from falcon_correlate.middleware import DEFAULT_HEADER_NAME  # noqa: E402
from falcon_correlate.unittests.httpx_wrapper_helpers import (  # noqa: E402
    EXPECTED_TIMEOUT,
    run_sync,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc


class TestRequestWithCorrelationId:
    """Tests for the synchronous ``request_with_correlation_id`` wrapper."""

    @pytest.mark.parametrize(
        ("extra_kwargs", "correlation_id"),
        [
            ({}, "sync-cid-001"),
            ({"headers": None}, "sync-cid-003"),
        ],
        ids=["plain", "headers_none"],
    )
    def test_injects_correlation_id_header(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
        extra_kwargs: dict[str, typ.Any],
        correlation_id: str,
    ) -> None:
        """Verify the wrapper injects the correlation ID header when set."""
        captured = run_sync(
            isolated_context,
            correlation_id=correlation_id,
            **extra_kwargs,
        )
        assert captured["headers"][DEFAULT_HEADER_NAME] == correlation_id
        assert captured["method"] == "GET"
        assert captured["url"] == "http://example.com"

    def test_does_not_add_header_when_context_is_empty(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify no header is added when the context variable is unset."""
        captured = run_sync(isolated_context)

        assert DEFAULT_HEADER_NAME not in captured["headers"]

    def test_preserves_existing_caller_headers(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify caller-supplied headers are preserved."""
        captured = run_sync(
            isolated_context,
            correlation_id="sync-cid-002",
            headers={"Authorization": "Bearer token"},
        )

        headers = captured["headers"]
        assert headers["Authorization"] == "Bearer token"
        assert headers[DEFAULT_HEADER_NAME] == "sync-cid-002"

    def test_passes_through_additional_kwargs(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify extra keyword arguments are forwarded to httpx."""
        captured = run_sync(
            isolated_context,
            method="POST",
            json={"key": "val"},
            timeout=EXPECTED_TIMEOUT,
        )

        assert captured["json"] == {"key": "val"}
        assert captured["timeout"] == EXPECTED_TIMEOUT

    def test_converts_immutable_headers_to_mutable(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify immutable mapping headers are converted without error."""
        immutable = types.MappingProxyType({"Accept": "text/html"})
        captured = run_sync(
            isolated_context,
            correlation_id="sync-cid-004",
            headers=immutable,
        )

        headers = captured["headers"]
        assert headers["Accept"] == "text/html"
        assert headers[DEFAULT_HEADER_NAME] == "sync-cid-004"

    def test_accepts_sequence_style_headers(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify sequence-style headers (list/tuple of pairs) are handled."""
        sequence_headers = [("Accept", "text/html")]
        captured = run_sync(
            isolated_context,
            correlation_id="sync-cid-005",
            headers=sequence_headers,
        )

        headers = captured["headers"]
        assert headers["Accept"] == "text/html"
        assert headers[DEFAULT_HEADER_NAME] == "sync-cid-005"

    def test_copies_httpx_headers_before_injecting_correlation_id(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Reused caller ``httpx.Headers`` must not retain injected IDs."""
        shared_headers = httpx.Headers({"Accept": "text/html"})

        first_call = run_sync(
            isolated_context,
            correlation_id="sync-cid-006",
            headers=shared_headers,
        )
        second_call = run_sync(
            isolated_context,
            correlation_id="sync-cid-007",
            headers=shared_headers,
        )

        first_headers = first_call["headers"]
        second_headers = second_call["headers"]

        assert first_headers is not shared_headers
        assert second_headers is not shared_headers
        assert first_headers is not second_headers
        assert first_headers["Accept"] == "text/html"
        assert second_headers["Accept"] == "text/html"
        assert first_headers[DEFAULT_HEADER_NAME] == "sync-cid-006"
        assert second_headers[DEFAULT_HEADER_NAME] == "sync-cid-007"
        assert DEFAULT_HEADER_NAME not in shared_headers
