"""Unit tests for async httpx correlation ID wrapper functions."""

from __future__ import annotations

import typing as typ
from unittest import mock

import pytest

httpx = pytest.importorskip("httpx")

from falcon_correlate.httpx import async_request_with_correlation_id  # noqa: E402
from falcon_correlate.middleware import DEFAULT_HEADER_NAME  # noqa: E402
from falcon_correlate.unittests.httpx_wrapper_helpers import (  # noqa: E402
    EXPECTED_TIMEOUT,
    run_async,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc


@pytest.fixture
def mock_async_client() -> cabc.Generator[mock.AsyncMock, None, None]:
    """Provide a pre-configured httpx.AsyncClient mock."""
    with mock.patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = mock.AsyncMock()
        mock_client.request.return_value = httpx.Response(200)
        mock_client_cls.return_value.__aenter__ = mock.AsyncMock(
            return_value=mock_client
        )
        mock_client_cls.return_value.__aexit__ = mock.AsyncMock(return_value=False)
        yield mock_client


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
    # Parametrized pytest fixture matrix documents async header combinations.
    # pylint: disable-next=too-many-arguments,too-many-positional-arguments
    async def test_injects_correlation_id_header(
        self,
        mock_async_client: mock.AsyncMock,
        extra_kwargs: dict[str, typ.Any],
        correlation_id: str,
        expected_extra_headers: dict[str, str],
    ) -> None:
        """Verify the async wrapper injects the correlation ID header when set."""
        call_kwargs = await run_async(
            mock_async_client,
            correlation_id=correlation_id,
            **extra_kwargs,
        )
        headers = call_kwargs["headers"]
        assert headers[DEFAULT_HEADER_NAME] == correlation_id
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
        assert DEFAULT_HEADER_NAME not in call_kwargs["headers"]

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
            timeout=EXPECTED_TIMEOUT,
        )

        call_kwargs = mock_async_client.request.call_args.kwargs
        assert call_kwargs["json"] == {"key": "val"}
        assert call_kwargs["timeout"] == EXPECTED_TIMEOUT
