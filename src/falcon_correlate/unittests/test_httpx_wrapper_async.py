"""Unit tests for async httpx correlation ID wrapper functions."""

from __future__ import annotations

import typing as typ
from unittest import mock

import pytest

httpx = pytest.importorskip("httpx")

pytest_plugins = ("falcon_correlate.unittests.httpx_wrapper_helpers",)

from falcon_correlate import (  # ruff: ignore[module-import-not-at-top-of-file] -- dependency probe first.
    correlation_id_var,
)
from falcon_correlate.httpx import (  # ruff: ignore[module-import-not-at-top-of-file] -- dependency probe first.
    async_request_with_correlation_id,
)
from falcon_correlate.middleware import (  # ruff: ignore[module-import-not-at-top-of-file] -- dependency probe first.
    DEFAULT_HEADER_NAME,
)
from falcon_correlate.unittests.httpx_wrapper_helpers import (  # ruff: ignore[module-import-not-at-top-of-file] -- dependency probe first.
    EXPECTED_TIMEOUT,
    run_async,
)

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
        failure_message = (
            "expected headers[DEFAULT_HEADER_NAME] to equal correlation_id"
        )
        assert headers[DEFAULT_HEADER_NAME] == correlation_id, failure_message
        for key, value in expected_extra_headers.items():
            assert headers[key] == value, "expected headers[key] to equal value"

    @pytest.mark.asyncio
    async def test_does_not_add_header_when_context_is_empty(
        self,
        mock_async_client: mock.AsyncMock,
    ) -> None:
        """Verify no header is added when the context variable is unset."""
        await async_request_with_correlation_id("GET", "http://example.com")

        call_kwargs = mock_async_client.request.call_args.kwargs
        failure_message = (
            "expected condition: DEFAULT_HEADER_NAME not in call_kwargs['h..."
        )
        assert DEFAULT_HEADER_NAME not in call_kwargs["headers"], failure_message

    @pytest.mark.asyncio
    async def test_passes_through_additional_kwargs(
        self,
        mock_async_client: mock.AsyncMock,
    ) -> None:
        """Verify extra keyword arguments are forwarded to httpx."""
        token = correlation_id_var.set("async-cid-004")
        try:
            await async_request_with_correlation_id(
                "POST",
                "http://example.com",
                headers={"X-Request-ID": "caller-request-id"},
                json={"key": "val"},
                timeout=EXPECTED_TIMEOUT,
            )
        finally:
            correlation_id_var.reset(token)

        call_kwargs = mock_async_client.request.call_args.kwargs
        headers = call_kwargs["headers"]
        failure_message = "expected forwarded headers to be an httpx.Headers object"
        assert isinstance(headers, httpx.Headers), failure_message
        failure_message = "expected the caller header to be preserved"
        assert headers["X-Request-ID"] == "caller-request-id", failure_message
        failure_message = "expected the correlation ID header to be injected"
        assert headers[DEFAULT_HEADER_NAME] == "async-cid-004", failure_message
        failure_message = "expected only headers, json and timeout to be forwarded"
        assert call_kwargs.keys() == {"headers", "json", "timeout"}, failure_message
        failure_message = "expected call_kwargs['json'] to equal {'key': 'val'}"
        assert call_kwargs["json"] == {"key": "val"}, failure_message
        failure_message = "expected call_kwargs['timeout'] to equal EXPECTED_TIMEOUT"
        assert call_kwargs["timeout"] == EXPECTED_TIMEOUT, failure_message
        failure_message = "expected the async request method to be 'POST'"
        assert mock_async_client.request.call_args.args[0] == "POST", failure_message

    @pytest.mark.asyncio
    async def test_preserves_case_variant_correlation_header(
        self,
        mock_async_client: mock.AsyncMock,
    ) -> None:
        """Verify the async wrapper preserves a lowercase caller header."""
        call_kwargs = await run_async(
            mock_async_client,
            correlation_id="async-cid-005",
            headers=[("x-correlation-id", "caller-cid")],
        )

        failure_message = "expected only the caller correlation ID to remain"
        assert call_kwargs["headers"].get_list(DEFAULT_HEADER_NAME) == ["caller-cid"], (
            failure_message
        )

    @pytest.mark.asyncio
    async def test_sends_prepared_headers_through_httpx_transport(self) -> None:
        """Verify repeated headers reach an in-process HTTPX transport."""
        received: dict[str, httpx.Request] = {}
        json_payload = {"key": "value"}
        caller_headers = [
            ("X-Repeated", "first"),
            ("x-repeated", "second"),
        ]
        actual_async_client = httpx.AsyncClient

        def receive_request(request: httpx.Request) -> httpx.Response:
            """Capture the request at the HTTPX transport boundary."""
            received["request"] = request
            return httpx.Response(200, request=request)

        def make_async_client() -> httpx.AsyncClient:
            """Build a real async client with an in-process transport."""
            transport = httpx.MockTransport(receive_request)
            return actual_async_client(transport=transport)

        token = correlation_id_var.set("async-transport-cid")
        try:
            with mock.patch("httpx.AsyncClient", side_effect=make_async_client):
                response = await async_request_with_correlation_id(
                    "POST",
                    "https://example.com/headers",
                    headers=caller_headers,
                    json=json_payload,
                    timeout=EXPECTED_TIMEOUT,
                )
        finally:
            correlation_id_var.reset(token)

        request = received["request"]
        failure_message = "expected the in-process HTTPX response to succeed"
        assert response.status_code == 200, failure_message
        failure_message = "expected both repeated headers to reach the transport"
        assert request.headers.get_list("X-Repeated", split_commas=False) == [
            "first",
            "second",
        ], failure_message
        failure_message = "expected the context correlation ID to reach the transport"
        assert request.headers.get_list(DEFAULT_HEADER_NAME, split_commas=False) == [
            "async-transport-cid"
        ], failure_message
        failure_message = "expected the caller header list to remain unchanged"
        assert caller_headers == [
            ("X-Repeated", "first"),
            ("x-repeated", "second"),
        ], failure_message
        failure_message = "expected the JSON payload to reach the transport"
        assert request.content == b'{"key":"value"}', failure_message
