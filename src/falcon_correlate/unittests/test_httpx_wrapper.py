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

_EXPECTED_TIMEOUT = 5


class TestRequestWithCorrelationId:
    """Tests for the synchronous ``request_with_correlation_id`` wrapper."""

    def test_adds_correlation_id_header_when_set(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify the wrapper injects the correlation ID header."""
        captured_kwargs: dict[str, typ.Any] = {}

        def test_logic() -> None:
            correlation_id_var.set("sync-cid-001")
            with mock.patch("httpx.request") as mock_request:
                mock_request.return_value = httpx.Response(200)
                request_with_correlation_id("GET", "http://example.com")
                captured_kwargs.update(mock_request.call_args.kwargs)

        isolated_context(test_logic)

        assert captured_kwargs["headers"]["X-Correlation-ID"] == ("sync-cid-001")

    def test_does_not_add_header_when_context_is_empty(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify no header is added when the context variable is unset."""
        captured_kwargs: dict[str, typ.Any] = {}

        def test_logic() -> None:
            with mock.patch("httpx.request") as mock_request:
                mock_request.return_value = httpx.Response(200)
                request_with_correlation_id("GET", "http://example.com")
                captured_kwargs.update(mock_request.call_args.kwargs)

        isolated_context(test_logic)

        assert "X-Correlation-ID" not in captured_kwargs["headers"]

    def test_preserves_existing_caller_headers(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify caller-supplied headers are preserved."""
        captured_kwargs: dict[str, typ.Any] = {}

        def test_logic() -> None:
            correlation_id_var.set("sync-cid-002")
            with mock.patch("httpx.request") as mock_request:
                mock_request.return_value = httpx.Response(200)
                request_with_correlation_id(
                    "GET",
                    "http://example.com",
                    headers={"Authorization": "Bearer token"},
                )
                captured_kwargs.update(mock_request.call_args.kwargs)

        isolated_context(test_logic)

        headers = captured_kwargs["headers"]
        assert headers["Authorization"] == "Bearer token"
        assert headers["X-Correlation-ID"] == "sync-cid-002"

    def test_handles_none_headers_argument(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify headers=None does not cause an error."""
        captured_kwargs: dict[str, typ.Any] = {}

        def test_logic() -> None:
            correlation_id_var.set("sync-cid-003")
            with mock.patch("httpx.request") as mock_request:
                mock_request.return_value = httpx.Response(200)
                request_with_correlation_id(
                    "GET",
                    "http://example.com",
                    headers=None,
                )
                captured_kwargs.update(mock_request.call_args.kwargs)

        isolated_context(test_logic)

        assert captured_kwargs["headers"]["X-Correlation-ID"] == ("sync-cid-003")

    def test_passes_through_additional_kwargs(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify extra keyword arguments are forwarded to httpx."""
        captured_kwargs: dict[str, typ.Any] = {}

        def test_logic() -> None:
            with mock.patch("httpx.request") as mock_request:
                mock_request.return_value = httpx.Response(200)
                request_with_correlation_id(
                    "POST",
                    "http://example.com",
                    json={"key": "val"},
                    timeout=_EXPECTED_TIMEOUT,
                )
                captured_kwargs.update(mock_request.call_args.kwargs)

        isolated_context(test_logic)

        assert captured_kwargs["json"] == {"key": "val"}
        assert captured_kwargs["timeout"] == _EXPECTED_TIMEOUT

    def test_converts_immutable_headers_to_mutable(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify immutable mapping headers are converted without error."""
        captured_kwargs: dict[str, typ.Any] = {}
        immutable = types.MappingProxyType({"Accept": "text/html"})

        def test_logic() -> None:
            correlation_id_var.set("sync-cid-004")
            with mock.patch("httpx.request") as mock_request:
                mock_request.return_value = httpx.Response(200)
                request_with_correlation_id(
                    "GET",
                    "http://example.com",
                    headers=immutable,
                )
                captured_kwargs.update(mock_request.call_args.kwargs)

        isolated_context(test_logic)

        headers = captured_kwargs["headers"]
        assert headers["Accept"] == "text/html"
        assert headers["X-Correlation-ID"] == "sync-cid-004"


class TestAsyncRequestWithCorrelationId:
    """Tests for the async ``async_request_with_correlation_id`` wrapper."""

    @pytest.mark.asyncio
    async def test_adds_correlation_id_header_when_set(
        self,
    ) -> None:
        """Verify the async wrapper injects the correlation ID header."""
        token = correlation_id_var.set("async-cid-001")
        try:
            mock_response = httpx.Response(200)
            with mock.patch(
                "httpx.AsyncClient",
            ) as mock_client_cls:
                mock_client = mock.AsyncMock()
                mock_client.request.return_value = mock_response
                mock_client_cls.return_value.__aenter__ = mock.AsyncMock(
                    return_value=mock_client
                )
                mock_client_cls.return_value.__aexit__ = mock.AsyncMock(
                    return_value=False
                )

                await async_request_with_correlation_id("GET", "http://example.com")

                call_kwargs = mock_client.request.call_args.kwargs
                assert call_kwargs["headers"]["X-Correlation-ID"] == ("async-cid-001")
        finally:
            correlation_id_var.reset(token)

    @pytest.mark.asyncio
    async def test_does_not_add_header_when_context_is_empty(
        self,
    ) -> None:
        """Verify no header is added when the context variable is unset."""
        mock_response = httpx.Response(200)
        with mock.patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = mock.AsyncMock()
            mock_client.request.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = mock.AsyncMock(
                return_value=mock_client
            )
            mock_client_cls.return_value.__aexit__ = mock.AsyncMock(return_value=False)

            await async_request_with_correlation_id("GET", "http://example.com")

            call_kwargs = mock_client.request.call_args.kwargs
            assert "X-Correlation-ID" not in call_kwargs["headers"]

    @pytest.mark.asyncio
    async def test_preserves_existing_caller_headers(
        self,
    ) -> None:
        """Verify caller-supplied headers are preserved."""
        token = correlation_id_var.set("async-cid-002")
        try:
            mock_response = httpx.Response(200)
            with mock.patch(
                "httpx.AsyncClient",
            ) as mock_client_cls:
                mock_client = mock.AsyncMock()
                mock_client.request.return_value = mock_response
                mock_client_cls.return_value.__aenter__ = mock.AsyncMock(
                    return_value=mock_client
                )
                mock_client_cls.return_value.__aexit__ = mock.AsyncMock(
                    return_value=False
                )

                await async_request_with_correlation_id(
                    "GET",
                    "http://example.com",
                    headers={"Authorization": "Bearer token"},
                )

                call_kwargs = mock_client.request.call_args.kwargs
                headers = call_kwargs["headers"]
                assert headers["Authorization"] == "Bearer token"
                assert headers["X-Correlation-ID"] == "async-cid-002"
        finally:
            correlation_id_var.reset(token)

    @pytest.mark.asyncio
    async def test_handles_none_headers_argument(
        self,
    ) -> None:
        """Verify headers=None does not cause an error."""
        token = correlation_id_var.set("async-cid-003")
        try:
            mock_response = httpx.Response(200)
            with mock.patch(
                "httpx.AsyncClient",
            ) as mock_client_cls:
                mock_client = mock.AsyncMock()
                mock_client.request.return_value = mock_response
                mock_client_cls.return_value.__aenter__ = mock.AsyncMock(
                    return_value=mock_client
                )
                mock_client_cls.return_value.__aexit__ = mock.AsyncMock(
                    return_value=False
                )

                await async_request_with_correlation_id(
                    "GET",
                    "http://example.com",
                    headers=None,
                )

                call_kwargs = mock_client.request.call_args.kwargs
                assert call_kwargs["headers"]["X-Correlation-ID"] == ("async-cid-003")
        finally:
            correlation_id_var.reset(token)

    @pytest.mark.asyncio
    async def test_passes_through_additional_kwargs(
        self,
    ) -> None:
        """Verify extra keyword arguments are forwarded to httpx."""
        mock_response = httpx.Response(200)
        with mock.patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = mock.AsyncMock()
            mock_client.request.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = mock.AsyncMock(
                return_value=mock_client
            )
            mock_client_cls.return_value.__aexit__ = mock.AsyncMock(return_value=False)

            await async_request_with_correlation_id(
                "POST",
                "http://example.com",
                json={"key": "val"},
                timeout=_EXPECTED_TIMEOUT,
            )

            call_kwargs = mock_client.request.call_args.kwargs
            assert call_kwargs["json"] == {"key": "val"}
            assert call_kwargs["timeout"] == _EXPECTED_TIMEOUT


class TestPrepareHeaders:
    """Tests for the private ``_prepare_headers`` helper."""

    def test_extracts_headers_from_kwargs(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify headers are popped from kwargs and returned."""
        result: dict[str, typ.Any] = {}

        def test_logic() -> None:
            kwargs: dict[str, typ.Any] = {
                "headers": {"Accept": "text/html"},
                "timeout": _EXPECTED_TIMEOUT,
            }
            headers = _prepare_headers(kwargs)
            result["headers"] = headers
            result["kwargs"] = kwargs

        isolated_context(test_logic)

        assert result["headers"]["Accept"] == "text/html"
        assert "headers" not in result["kwargs"]
        assert result["kwargs"]["timeout"] == _EXPECTED_TIMEOUT

    def test_returns_empty_dict_when_no_headers(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify an empty dict is returned when no headers are passed."""
        result: dict[str, typ.Any] = {}

        def test_logic() -> None:
            kwargs: dict[str, typ.Any] = {"timeout": _EXPECTED_TIMEOUT}
            result["headers"] = _prepare_headers(kwargs)

        isolated_context(test_logic)

        assert result["headers"] == {}

    def test_injects_correlation_id(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify the correlation ID is injected into headers."""
        result: dict[str, typ.Any] = {}

        def test_logic() -> None:
            correlation_id_var.set("prep-cid-001")
            kwargs: dict[str, typ.Any] = {}
            result["headers"] = _prepare_headers(kwargs)

        isolated_context(test_logic)

        assert result["headers"]["X-Correlation-ID"] == "prep-cid-001"

    def test_does_not_inject_when_no_correlation_id(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify no header is added when the context variable is unset."""
        result: dict[str, typ.Any] = {}

        def test_logic() -> None:
            kwargs: dict[str, typ.Any] = {}
            result["headers"] = _prepare_headers(kwargs)

        isolated_context(test_logic)

        assert "X-Correlation-ID" not in result["headers"]


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
