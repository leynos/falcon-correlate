"""Falcon ASGI integration tests for correlation ID middleware."""

from __future__ import annotations

from http import HTTPStatus

import falcon.asgi
import falcon.testing

from falcon_correlate import CorrelationIDMiddlewareASGI
from tests.asgi_resources import ASGICorrelationEchoResource


class TestCorrelationIDMiddlewareASGIFalconIntegration:
    """Tests for ASGI middleware in a real Falcon ASGI application."""

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
