"""Unit tests for sync httpx correlation ID wrapper functions."""

from __future__ import annotations

import types
import typing as typ

import pytest

httpx = pytest.importorskip("httpx")

from falcon_correlate.middleware import (  # noqa: E402 -- dependency probe first.
    DEFAULT_HEADER_NAME,
)
from falcon_correlate.unittests.httpx_wrapper_helpers import (  # noqa: E402 -- dependency probe first.
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
        assert captured["headers"][DEFAULT_HEADER_NAME] == correlation_id, (
            "expected condition: captured['headers'][DEFAULT_HEADER_NAME] ..."
        )
        assert captured["method"] == "GET", "expected captured['method'] to equal 'GET'"
        assert captured["url"] == "http://example.com", (
            "expected captured['url'] to equal 'http://example.com'"
        )

    def test_does_not_add_header_when_context_is_empty(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify no header is added when the context variable is unset."""
        captured = run_sync(isolated_context)

        assert DEFAULT_HEADER_NAME not in captured["headers"], (
            "expected condition: DEFAULT_HEADER_NAME not in captured['head..."
        )

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
        assert headers["Authorization"] == "Bearer token", (
            "expected headers['Authorization'] to equal 'Bearer token'"
        )
        assert headers[DEFAULT_HEADER_NAME] == "sync-cid-002", (
            "expected headers[DEFAULT_HEADER_NAME] to equal 'sync-cid-002'"
        )

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

        assert captured["json"] == {"key": "val"}, (
            "expected captured['json'] to equal {'key': 'val'}"
        )
        assert captured["timeout"] == EXPECTED_TIMEOUT, (
            "expected captured['timeout'] to equal EXPECTED_TIMEOUT"
        )

    @pytest.mark.parametrize(
        ("headers_input", "correlation_id"),
        [
            (types.MappingProxyType({"Accept": "text/html"}), "sync-cid-004"),
            ([("Accept", "text/html")], "sync-cid-005"),
        ],
        ids=["immutable_mapping", "sequence"],
    )
    def test_accepts_alternative_header_formats(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
        headers_input: object,
        correlation_id: str,
    ) -> None:
        """Verify immutable-mapping and sequence-style headers are handled."""
        captured = run_sync(
            isolated_context,
            correlation_id=correlation_id,
            headers=headers_input,
        )

        headers = captured["headers"]
        assert headers["Accept"] == "text/html", (
            "expected headers['Accept'] to equal 'text/html'"
        )
        assert headers[DEFAULT_HEADER_NAME] == correlation_id, (
            "expected headers[DEFAULT_HEADER_NAME] to equal correlation_id"
        )

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

        assert first_headers is not shared_headers, (
            "expected first_headers not to be shared_headers"
        )
        assert second_headers is not shared_headers, (
            "expected second_headers not to be shared_headers"
        )
        assert first_headers is not second_headers, (
            "expected first_headers not to be second_headers"
        )
        assert first_headers["Accept"] == "text/html", (
            "expected first_headers['Accept'] to equal 'text/html'"
        )
        assert second_headers["Accept"] == "text/html", (
            "expected second_headers['Accept'] to equal 'text/html'"
        )
        assert first_headers[DEFAULT_HEADER_NAME] == "sync-cid-006", (
            "expected condition: first_headers[DEFAULT_HEADER_NAME] == 'sy..."
        )
        assert second_headers[DEFAULT_HEADER_NAME] == "sync-cid-007", (
            "expected condition: second_headers[DEFAULT_HEADER_NAME] == 's..."
        )
        assert DEFAULT_HEADER_NAME not in shared_headers, (
            "expected DEFAULT_HEADER_NAME not to be present in shared_headers"
        )
