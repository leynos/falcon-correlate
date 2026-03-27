"""Unit tests for httpx correlation ID wrapper functions.

These tests validate the ``request_with_correlation_id`` and
``async_request_with_correlation_id`` wrapper functions that inject the
current correlation ID into outgoing ``httpx`` request headers.

All tests are skipped when ``httpx`` is not installed.
"""

from __future__ import annotations

import types
import typing as typ

import pytest

httpx = pytest.importorskip("httpx")

from unittest import mock  # noqa: E402

if typ.TYPE_CHECKING:
    import collections.abc as cabc

from falcon_correlate import (  # noqa: E402
    correlation_id_var,
)
from falcon_correlate.httpx import (  # noqa: E402
    _prepare_headers,
    async_request_with_correlation_id,
    request_with_correlation_id,
)
from falcon_correlate.middleware import DEFAULT_HEADER_NAME  # noqa: E402

_EXPECTED_TIMEOUT = 5


# -- helpers & fixtures ------------------------------------------------------


@pytest.fixture
def mock_async_client() -> typ.Generator[mock.AsyncMock, None, None]:
    """Provide a pre-configured httpx.AsyncClient mock."""
    with mock.patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = mock.AsyncMock()
        mock_client.request.return_value = httpx.Response(200)
        mock_client_cls.return_value.__aenter__ = mock.AsyncMock(
            return_value=mock_client
        )
        mock_client_cls.return_value.__aexit__ = mock.AsyncMock(return_value=False)
        yield mock_client


def _run_sync(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    correlation_id: str | None = None,
    **kwargs: typ.Any,  # noqa: ANN401
) -> dict[str, typ.Any]:
    """Run ``request_with_correlation_id`` in an isolated context.

    Returns the keyword arguments and positional arguments (method, url)
    captured from the mocked ``httpx.request`` call.
    """
    method: str = kwargs.pop("method", "GET")
    url: str = kwargs.pop("url", "http://example.com")
    captured: dict[str, typ.Any] = {}

    def _logic() -> None:
        if correlation_id is not None:
            correlation_id_var.set(correlation_id)
        with mock.patch("httpx.request") as mock_request:
            mock_request.return_value = httpx.Response(200)
            request_with_correlation_id(method, url, **kwargs)
            captured.update(mock_request.call_args.kwargs)
            captured["method"] = mock_request.call_args.args[0]
            captured["url"] = mock_request.call_args.args[1]

    isolated_context(_logic)
    return captured


async def _run_async(
    mock_async_client: mock.AsyncMock,
    correlation_id: str | None = None,
    **kwargs: typ.Any,  # noqa: ANN401
) -> dict[str, typ.Any]:
    """Run ``async_request_with_correlation_id`` in a managed correlation context.

    Returns the keyword arguments captured from the mocked
    ``httpx.AsyncClient.request`` call.
    """
    token = (
        correlation_id_var.set(correlation_id) if correlation_id is not None else None
    )
    try:
        await async_request_with_correlation_id("GET", "http://example.com", **kwargs)
        return mock_async_client.request.call_args.kwargs
    finally:
        if token is not None:
            correlation_id_var.reset(token)


def _run_prepare_headers(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    kwargs: dict[str, typ.Any],
    correlation_id: str | None = None,
) -> tuple[dict[str, typ.Any], dict[str, typ.Any]]:
    """Run ``_prepare_headers`` in an isolated context.

    Returns ``(headers, remaining_kwargs)`` where *remaining_kwargs*
    is the mutated input dict after ``headers`` has been popped.
    """
    result: dict[str, typ.Any] = {}

    def _logic() -> None:
        if correlation_id is not None:
            correlation_id_var.set(correlation_id)
        result["headers"] = _prepare_headers(kwargs)

    isolated_context(_logic)
    return result.get("headers", {}), kwargs


# -- sync wrapper tests -------------------------------------------------------


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
        captured = _run_sync(
            isolated_context,
            correlation_id=correlation_id,
            **extra_kwargs,
        )
        assert captured["headers"]["X-Correlation-ID"] == correlation_id
        assert captured["method"] == "GET"
        assert captured["url"] == "http://example.com"

    def test_does_not_add_header_when_context_is_empty(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify no header is added when the context variable is unset."""
        captured = _run_sync(isolated_context)

        assert "X-Correlation-ID" not in captured["headers"]

    def test_preserves_existing_caller_headers(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify caller-supplied headers are preserved."""
        captured = _run_sync(
            isolated_context,
            correlation_id="sync-cid-002",
            headers={"Authorization": "Bearer token"},
        )

        headers = captured["headers"]
        assert headers["Authorization"] == "Bearer token"
        assert headers["X-Correlation-ID"] == "sync-cid-002"

    def test_passes_through_additional_kwargs(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify extra keyword arguments are forwarded to httpx."""
        captured = _run_sync(
            isolated_context,
            method="POST",
            json={"key": "val"},
            timeout=_EXPECTED_TIMEOUT,
        )

        assert captured["json"] == {"key": "val"}
        assert captured["timeout"] == _EXPECTED_TIMEOUT

    def test_converts_immutable_headers_to_mutable(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify immutable mapping headers are converted without error."""
        immutable = types.MappingProxyType({"Accept": "text/html"})
        captured = _run_sync(
            isolated_context,
            correlation_id="sync-cid-004",
            headers=immutable,
        )

        headers = captured["headers"]
        assert headers["Accept"] == "text/html"
        assert headers["X-Correlation-ID"] == "sync-cid-004"

    def test_accepts_sequence_style_headers(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify sequence-style headers (list/tuple of pairs) are handled."""
        sequence_headers = [("Accept", "text/html")]
        captured = _run_sync(
            isolated_context,
            correlation_id="sync-cid-005",
            headers=sequence_headers,
        )

        headers = captured["headers"]
        assert headers["Accept"] == "text/html"
        assert headers["X-Correlation-ID"] == "sync-cid-005"

    def test_copies_httpx_headers_before_injecting_correlation_id(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Reused caller ``httpx.Headers`` must not retain injected IDs."""
        shared_headers = httpx.Headers({"Accept": "text/html"})

        first_call = _run_sync(
            isolated_context,
            correlation_id="sync-cid-006",
            headers=shared_headers,
        )
        second_call = _run_sync(
            isolated_context,
            correlation_id="sync-cid-007",
            headers=shared_headers,
        )

        first_headers = first_call["headers"]
        second_headers = second_call["headers"]

        assert first_headers is not shared_headers
        assert second_headers is not shared_headers
        assert first_headers["Accept"] == "text/html"
        assert second_headers["Accept"] == "text/html"
        assert first_headers[DEFAULT_HEADER_NAME] == "sync-cid-006"
        assert second_headers[DEFAULT_HEADER_NAME] == "sync-cid-007"
        assert DEFAULT_HEADER_NAME not in shared_headers


# -- async wrapper tests -------------------------------------------------------


class TestAsyncRequestWithCorrelationId:
    """Tests for the async ``async_request_with_correlation_id`` wrapper."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("extra_kwargs", "correlation_id", "expected_extra_headers"),
        [
            ({}, "async-cid-001", {}),
            ({"headers": None}, "async-cid-003", {}),
            (
                {"headers": {"Authorization": "Bearer token"}},
                "async-cid-002",
                {"Authorization": "Bearer token"},
            ),
        ],
        ids=["plain", "headers_none", "preserves_headers"],
    )
    async def test_injects_correlation_id_header(
        self,
        mock_async_client: mock.AsyncMock,
        extra_kwargs: dict[str, typ.Any],
        correlation_id: str,
        expected_extra_headers: dict[str, str],
    ) -> None:
        """Verify the async wrapper injects the correlation ID header when set."""
        call_kwargs = await _run_async(
            mock_async_client,
            correlation_id=correlation_id,
            **extra_kwargs,
        )
        headers = call_kwargs["headers"]
        assert headers["X-Correlation-ID"] == correlation_id
        for key, value in expected_extra_headers.items():
            assert headers[key] == value

    @pytest.mark.asyncio
    async def test_does_not_add_header_when_context_is_empty(
        self,
        mock_async_client: mock.AsyncMock,
    ) -> None:
        """Verify no header is added when the context variable is unset."""
        await async_request_with_correlation_id("GET", "http://example.com")

        call_kwargs = mock_async_client.request.call_args.kwargs
        assert "X-Correlation-ID" not in call_kwargs["headers"]

    @pytest.mark.asyncio
    async def test_passes_through_additional_kwargs(
        self,
        mock_async_client: mock.AsyncMock,
    ) -> None:
        """Verify extra keyword arguments are forwarded to httpx."""
        await async_request_with_correlation_id(
            "POST",
            "http://example.com",
            json={"key": "val"},
            timeout=_EXPECTED_TIMEOUT,
        )

        call_kwargs = mock_async_client.request.call_args.kwargs
        assert call_kwargs["json"] == {"key": "val"}
        assert call_kwargs["timeout"] == _EXPECTED_TIMEOUT


# -- _prepare_headers tests ----------------------------------------------------


class TestPrepareHeaders:
    """Tests for the private ``_prepare_headers`` helper."""

    def test_extracts_headers_from_kwargs(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify headers are popped from kwargs and returned."""
        kwargs: dict[str, typ.Any] = {
            "headers": {"Accept": "text/html"},
            "timeout": _EXPECTED_TIMEOUT,
        }
        headers, remaining = _run_prepare_headers(isolated_context, kwargs)

        assert headers["Accept"] == "text/html"
        assert "headers" not in remaining
        assert remaining["timeout"] == _EXPECTED_TIMEOUT

    def test_returns_empty_dict_when_no_headers(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify an empty dict is returned when no headers are passed."""
        kwargs: dict[str, typ.Any] = {"timeout": _EXPECTED_TIMEOUT}
        headers, _remaining = _run_prepare_headers(isolated_context, kwargs)

        assert headers == {}

    def test_injects_correlation_id(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify the correlation ID is injected into headers."""
        kwargs: dict[str, typ.Any] = {}
        headers, _remaining = _run_prepare_headers(
            isolated_context, kwargs, correlation_id="prep-cid-001"
        )

        assert headers["X-Correlation-ID"] == "prep-cid-001"

    def test_preserves_caller_supplied_correlation_id_header(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify caller-supplied correlation ID header is preserved."""
        kwargs: dict[str, typ.Any] = {
            "headers": {"X-Correlation-ID": "caller-cid-123"},
        }
        headers, _remaining = _run_prepare_headers(
            isolated_context, kwargs, correlation_id="prep-cid-001"
        )

        assert headers["X-Correlation-ID"] == "caller-cid-123"

    def test_does_not_inject_when_no_correlation_id(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify no header is added when the context variable is unset."""
        kwargs: dict[str, typ.Any] = {}
        headers, _remaining = _run_prepare_headers(isolated_context, kwargs)

        assert "X-Correlation-ID" not in headers


# -- export tests (no duplication — left as-is) ---------------------------------


class TestHttpxWrapperExports:
    """Tests for public API exports of httpx wrapper functions."""

    def test_request_with_correlation_id_in_all(self) -> None:
        """Verify request_with_correlation_id is in __all__."""
        import falcon_correlate

        assert "request_with_correlation_id" in falcon_correlate.__all__

    def test_async_request_with_correlation_id_in_all(self) -> None:
        """Verify async_request_with_correlation_id is in __all__."""
        import falcon_correlate

        assert "async_request_with_correlation_id" in falcon_correlate.__all__

    def test_request_with_correlation_id_importable(self) -> None:
        """Verify request_with_correlation_id is importable from root."""
        from falcon_correlate import request_with_correlation_id

        assert callable(request_with_correlation_id)

    def test_async_request_with_correlation_id_importable(self) -> None:
        """Verify async_request_with_correlation_id is importable."""
        from falcon_correlate import async_request_with_correlation_id

        assert callable(async_request_with_correlation_id)
