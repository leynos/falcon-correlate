"""Shared helpers for httpx wrapper unit tests."""

from __future__ import annotations

import typing as typ
from unittest import mock

import pytest

httpx = pytest.importorskip("httpx")

if typ.TYPE_CHECKING:
    import collections.abc as cabc

from falcon_correlate import correlation_id_var  # noqa: E402
from falcon_correlate.httpx import (  # noqa: E402
    _prepare_headers,
    async_request_with_correlation_id,
    request_with_correlation_id,
)

EXPECTED_TIMEOUT = 5


@pytest.fixture
def mock_async_client() -> cabc.Generator[mock.AsyncMock, None, None]:
    """Provide a pre-configured httpx.AsyncClient mock.

    Yields
    ------
    AsyncMock
        The patched ``httpx.AsyncClient`` instance used by the test.

    """
    with mock.patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = mock.AsyncMock()
        mock_client.request.return_value = httpx.Response(200)
        mock_client_cls.return_value.__aenter__ = mock.AsyncMock(
            return_value=mock_client
        )
        mock_client_cls.return_value.__aexit__ = mock.AsyncMock(return_value=False)
        yield mock_client


def run_sync(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    correlation_id: str | None = None,
    **kwargs: typ.Any,  # noqa: ANN401 -- mirrors flexible httpx.request kwargs.
) -> dict[str, typ.Any]:
    """Run ``request_with_correlation_id`` in an isolated context.

    Returns the method, URL, and forwarded keyword arguments captured from the
    mocked ``httpx.request`` call.

    Returns
    -------
    dict[str, typ.Any]
        A mapping containing ``method``, ``url``, and the forwarded request
        keyword arguments.
    """
    method: str = kwargs.pop("method", "GET")
    url: str = kwargs.pop("url", "http://example.com")
    captured: dict[str, typ.Any] = {}

    def _logic() -> None:
        """Exercise the isolated test scenario."""
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


async def run_async(
    mock_async_client: mock.AsyncMock,
    correlation_id: str | None = None,
    **kwargs: typ.Any,  # noqa: ANN401 -- mirrors flexible httpx request kwargs.
) -> dict[str, typ.Any]:
    """Run ``async_request_with_correlation_id`` in a managed correlation context.

    Returns the keyword arguments captured from the mocked
    ``httpx.AsyncClient.request`` call.

    Returns
    -------
    dict[str, typ.Any]
        The forwarded request keyword arguments captured from the async client.
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


def run_prepare_headers(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    kwargs: dict[str, typ.Any],
    correlation_id: str | None = None,
) -> tuple[dict[str, typ.Any], dict[str, typ.Any]]:
    """Run ``_prepare_headers`` in an isolated context.

    Returns ``(headers, remaining_kwargs)`` where *remaining_kwargs*
    is the mutated input dict after ``headers`` has been popped.

    Returns
    -------
    tuple[dict[str, typ.Any], dict[str, typ.Any]]
        A pair containing the prepared headers and the mutated keyword-argument
        mapping after ``headers`` has been removed.
    """
    result: dict[str, typ.Any] = {}

    def _logic() -> None:
        """Exercise the isolated test scenario."""
        if correlation_id is not None:
            correlation_id_var.set(correlation_id)
        result["headers"] = _prepare_headers(kwargs)

    isolated_context(_logic)
    return result.get("headers", {}), kwargs
