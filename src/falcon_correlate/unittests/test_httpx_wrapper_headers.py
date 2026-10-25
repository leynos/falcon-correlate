"""Unit tests for httpx wrapper header preparation."""

from __future__ import annotations

import types
import typing as typ

import pytest

httpx = pytest.importorskip("httpx")

from falcon_correlate.middleware import (  # ruff: ignore[module-import-not-at-top-of-file] -- dependency probe first.
    DEFAULT_HEADER_NAME,
)
from falcon_correlate.unittests.httpx_wrapper_helpers import (  # ruff: ignore[module-import-not-at-top-of-file] -- dependency probe first.
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
        """Verify headers are returned without mutating the input mapping."""
        kwargs: dict[str, typ.Any] = {
            "headers": {"Accept": "text/html"},
            "timeout": EXPECTED_TIMEOUT,
        }
        kwargs_before = kwargs.copy()
        headers, request_kwargs = run_prepare_headers(isolated_context, kwargs)

        failure_message = "expected headers['Accept'] to equal 'text/html'"
        assert headers["Accept"] == "text/html", failure_message
        failure_message = "expected input kwargs to retain its headers"
        assert "headers" in kwargs, failure_message
        failure_message = "expected input kwargs to equal its pre-call snapshot"
        assert kwargs == kwargs_before, failure_message
        failure_message = "expected 'headers' not to be present in request_kwargs"
        assert "headers" not in request_kwargs, failure_message
        failure_message = "expected request_kwargs['timeout'] to equal EXPECTED_TIMEOUT"
        assert request_kwargs["timeout"] == EXPECTED_TIMEOUT, failure_message
        failure_message = "expected request_kwargs to be a new mapping"
        assert request_kwargs is not kwargs, failure_message

    def test_returns_empty_dict_when_no_headers(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify an empty ``httpx.Headers`` is returned without headers."""
        kwargs: dict[str, typ.Any] = {"timeout": EXPECTED_TIMEOUT}
        headers, _request_kwargs = run_prepare_headers(isolated_context, kwargs)

        failure_message = "expected an httpx.Headers object"
        assert isinstance(headers, httpx.Headers), failure_message
        assert headers == {}, "expected headers to equal {}"

    def test_injects_correlation_id(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify the correlation ID is injected into headers."""
        kwargs: dict[str, typ.Any] = {}
        headers, _request_kwargs = run_prepare_headers(
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
        headers, _request_kwargs = run_prepare_headers(
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
        headers, _request_kwargs = run_prepare_headers(isolated_context, kwargs)

        failure_message = "expected DEFAULT_HEADER_NAME not to be present in headers"
        assert DEFAULT_HEADER_NAME not in headers, failure_message

    def test_accepts_read_only_kwargs_mapping(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify a read-only mapping can be prepared without mutation."""
        kwargs = types.MappingProxyType({
            "headers": {"Accept": "text/html"},
            "timeout": EXPECTED_TIMEOUT,
        })
        kwargs_before = dict(kwargs)

        headers, request_kwargs = run_prepare_headers(isolated_context, kwargs)

        failure_message = "expected input kwargs to equal its pre-call snapshot"
        assert dict(kwargs) == kwargs_before, failure_message
        failure_message = "expected headers['Accept'] to equal 'text/html'"
        assert headers["Accept"] == "text/html", failure_message
        failure_message = "expected request_kwargs to exclude headers"
        assert "headers" not in request_kwargs, failure_message
        failure_message = "expected request_kwargs to retain timeout"
        assert request_kwargs["timeout"] == EXPECTED_TIMEOUT, failure_message

    def test_does_not_mutate_caller_header_dict_during_injection(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify injected IDs are added only to the copied headers."""
        caller_headers = {"Accept": "text/html"}
        caller_headers_before = caller_headers.copy()

        headers, _request_kwargs = run_prepare_headers(
            isolated_context,
            {"headers": caller_headers},
            correlation_id="prep-cid-002",
        )

        failure_message = "expected the caller-supplied header dict to be unchanged"
        assert caller_headers == caller_headers_before, failure_message
        failure_message = "expected prepared headers to be a new object"
        assert headers is not caller_headers, failure_message
        failure_message = "expected prepared headers to contain the injected ID"
        assert headers[DEFAULT_HEADER_NAME] == "prep-cid-002", failure_message

    def test_preserves_duplicate_non_correlation_headers(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify repeated caller headers survive preparation."""
        headers, _request_kwargs = run_prepare_headers(
            isolated_context,
            {"headers": [("X-Trace", "first"), ("X-Trace", "second")]},
        )

        failure_message = "expected both X-Trace values to be preserved"
        assert headers.get_list("X-Trace") == ["first", "second"], failure_message

    def test_preserves_lowercase_correlation_header_without_injection(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify a lowercase caller header blocks case-insensitive injection."""
        headers, _request_kwargs = run_prepare_headers(
            isolated_context,
            {"headers": [("x-correlation-id", "caller-cid")]},
            correlation_id="prep-cid-003",
        )

        failure_message = "expected only the caller correlation ID to remain"
        assert headers.get_list(DEFAULT_HEADER_NAME) == ["caller-cid"], failure_message

    def test_preserves_case_variant_duplicate_correlation_headers(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify both caller case variants survive without injection."""
        headers, _request_kwargs = run_prepare_headers(
            isolated_context,
            {
                "headers": [
                    ("X-Correlation-ID", "caller-first"),
                    ("x-correlation-id", "caller-second"),
                ]
            },
            correlation_id="prep-cid-004",
        )

        failure_message = "expected both caller correlation IDs to remain"
        assert headers.get_list(DEFAULT_HEADER_NAME) == [
            "caller-first",
            "caller-second",
        ], failure_message
