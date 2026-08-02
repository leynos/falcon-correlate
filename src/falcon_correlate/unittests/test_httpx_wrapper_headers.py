"""Unit tests for httpx wrapper header preparation."""

from __future__ import annotations

import typing as typ

import pytest

pytest.importorskip("httpx")

from falcon_correlate.middleware import DEFAULT_HEADER_NAME
from falcon_correlate.unittests.httpx_wrapper_helpers import (
    EXPECTED_TIMEOUT,
    run_prepare_headers,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc


class TestPrepareHeaders:
    """Tests for the private ``_prepare_headers`` helper."""

    def test_extracts_headers_from_kwargs(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify headers are popped from kwargs and returned."""
        kwargs: dict[str, typ.Any] = {
            "headers": {"Accept": "text/html"},
            "timeout": EXPECTED_TIMEOUT,
        }
        headers, remaining = run_prepare_headers(isolated_context, kwargs)

        failure_message = "expected headers['Accept'] to equal 'text/html'"
        assert headers["Accept"] == "text/html", failure_message
        failure_message = "expected 'headers' not to be present in remaining"
        assert "headers" not in remaining, failure_message
        failure_message = "expected remaining['timeout'] to equal EXPECTED_TIMEOUT"
        assert remaining["timeout"] == EXPECTED_TIMEOUT, failure_message

    def test_returns_empty_dict_when_no_headers(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify an empty dict is returned when no headers are passed."""
        kwargs: dict[str, typ.Any] = {"timeout": EXPECTED_TIMEOUT}
        headers, _remaining = run_prepare_headers(isolated_context, kwargs)

        assert headers == {}, "expected headers to equal {}"

    def test_injects_correlation_id(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify the correlation ID is injected into headers."""
        kwargs: dict[str, typ.Any] = {}
        headers, _remaining = run_prepare_headers(
            isolated_context, kwargs, correlation_id="prep-cid-001"
        )

        failure_message = (
            "expected headers[DEFAULT_HEADER_NAME] to equal 'prep-cid-001'"
        )
        assert headers[DEFAULT_HEADER_NAME] == "prep-cid-001", failure_message

    def test_preserves_caller_supplied_correlation_id_header(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify caller-supplied correlation ID header is preserved."""
        kwargs: dict[str, typ.Any] = {
            "headers": {DEFAULT_HEADER_NAME: "caller-cid-123"},
        }
        headers, _remaining = run_prepare_headers(
            isolated_context, kwargs, correlation_id="prep-cid-001"
        )

        failure_message = (
            "expected headers[DEFAULT_HEADER_NAME] to equal 'caller-cid-123'"
        )
        assert headers[DEFAULT_HEADER_NAME] == "caller-cid-123", failure_message

    def test_does_not_inject_when_no_correlation_id(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify no header is added when the context variable is unset."""
        kwargs: dict[str, typ.Any] = {}
        headers, _remaining = run_prepare_headers(isolated_context, kwargs)

        failure_message = "expected DEFAULT_HEADER_NAME not to be present in headers"
        assert DEFAULT_HEADER_NAME not in headers, failure_message
