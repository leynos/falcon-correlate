"""Falcon ASGI integration tests for correlation ID middleware."""

from __future__ import annotations

import asyncio
from http import HTTPStatus

import falcon.asgi
import falcon.testing
import pytest

from falcon_correlate import CorrelationIDMiddlewareASGI, correlation_id_var
from tests.asgi_resources import (
    ASGICorrelationEchoResource,
    ASGIInterleavedCorrelationResource,
)


class TestCorrelationIDMiddlewareASGIFalconIntegration:
    """Tests for ASGI middleware in a real Falcon ASGI application."""

    def test_interleaved_resource_rejects_non_positive_request_count(self) -> None:
        """Verify barrier misconfiguration fails during construction."""
        with pytest.raises(ValueError, match="expected_requests must be positive"):
            ASGIInterleavedCorrelationResource(expected_requests=0)

    def test_falcon_asgi_app_exposes_and_echoes_correlation_id(self) -> None:
        """Verify a Falcon ASGI app observes and echoes the same ID."""
        app = falcon.asgi.App(
            middleware=[
                CorrelationIDMiddlewareASGI(
                    trusted_sources=["127.0.0.1"],
                ),
            ],
        )
        app.add_route("/correlation", ASGICorrelationEchoResource())
        client = falcon.testing.TestClient(app)

        result = client.simulate_get(
            "/correlation",
            headers={"X-Correlation-ID": "trusted-asgi"},
        )

        assert result.status_code == HTTPStatus.OK, (
            f"expected result.status_code to be {HTTPStatus.OK} but got "
            f"{result.status_code}"
        )
        expected_json = {
            "context_correlation_id": "trusted-asgi",
            "contextvar_correlation_id": "trusted-asgi",
        }
        assert result.json == expected_json, (
            f"expected result.json to be {expected_json!r} but got {result.json!r}"
        )
        assert result.headers["X-Correlation-ID"] == "trusted-asgi", (
            "expected result.headers['X-Correlation-ID'] to be 'trusted-asgi' "
            f"but got {result.headers['X-Correlation-ID']!r}"
        )

    @pytest.mark.asyncio
    async def test_concurrent_falcon_asgi_requests_isolate_context(self) -> None:
        """Verify real Falcon ASGI requests keep task-local context isolated."""
        request_count = 4
        app = falcon.asgi.App(
            middleware=[
                CorrelationIDMiddlewareASGI(
                    trusted_sources=["127.0.0.1"],
                ),
            ],
        )
        app.add_route(
            "/correlation",
            ASGIInterleavedCorrelationResource(expected_requests=request_count),
        )

        async with falcon.testing.ASGIConductor(app) as conductor:
            results = await asyncio.wait_for(
                asyncio.gather(
                    *(
                        conductor.simulate_get(
                            "/correlation",
                            headers={"X-Correlation-ID": f"cid-{index}"},
                        )
                        for index in range(request_count)
                    ),
                ),
                timeout=5.0,
            )

        for index, result in enumerate(results):
            expected_id = f"cid-{index}"
            expected_json = {
                "context_correlation_id": expected_id,
                "contextvar_correlation_id": expected_id,
                "contextvar_correlation_id_after_wait": expected_id,
            }
            assert result.status_code == HTTPStatus.OK, (
                f"expected result.status_code to be {HTTPStatus.OK} but got "
                f"{result.status_code}"
            )
            assert result.json == expected_json, (
                f"expected result.json to be {expected_json!r} but got {result.json!r}"
            )
            assert result.headers["X-Correlation-ID"] == expected_id, (
                "expected response header to match the request ID "
                f"{expected_id!r} but got "
                f"{result.headers['X-Correlation-ID']!r}"
            )

        assert correlation_id_var.get() is None, (
            "expected correlation_id_var.get() to be None after concurrent "
            f"ASGI requests but got {correlation_id_var.get()!r}"
        )
