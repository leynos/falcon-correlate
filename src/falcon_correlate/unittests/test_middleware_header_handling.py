"""Unit tests for CorrelationIDMiddleware header retrieval."""

from __future__ import annotations

import falcon
import falcon.testing
import pytest

from falcon_correlate import CorrelationIDMiddleware
from tests.conftest import CorrelationEchoResource


class TestCorrelationIDHeaderRetrieval:
    """Tests for correlation ID header retrieval.

    Note: These tests configure 127.0.0.1 as a trusted source because
    Falcon's TestClient uses that as the default remote_addr. This allows
    testing header retrieval behaviour in isolation from trusted source logic.
    """

    def _client_with_resource(self) -> falcon.testing.TestClient:
        """Create a test client with the correlation echo resource.

        The middleware is configured to trust 127.0.0.1 (TestClient's default
        remote_addr) so that header retrieval can be tested independently.
        """
        middleware = CorrelationIDMiddleware(trusted_sources=["127.0.0.1"])
        app = falcon.App(middleware=[middleware])
        app.add_route("/correlation", CorrelationEchoResource())
        return falcon.testing.TestClient(app)

    def test_header_value_is_stored_in_request_context(self) -> None:
        """Verify a present header from trusted source is stored on req.context."""
        client = self._client_with_resource()
        response = client.simulate_get(
            "/correlation",
            headers={"X-Correlation-ID": "cid-123"},
        )

        assert response.json["has_correlation_id"] is True
        assert response.json["correlation_id"] == "cid-123"

    def test_missing_header_does_not_set_context(self) -> None:
        """Verify missing header leaves req.context unset."""
        client = self._client_with_resource()
        response = client.simulate_get("/correlation")

        assert response.json["has_correlation_id"] is False
        assert response.json["correlation_id"] is None

    @pytest.mark.parametrize(
        "header_value",
        ["", " ", "\t", "   "],
        ids=["empty", "space", "tab", "spaces"],
    )
    def test_empty_header_is_treated_as_missing(self, header_value: str) -> None:
        """Verify empty or whitespace header values are ignored."""
        client = self._client_with_resource()
        response = client.simulate_get(
            "/correlation",
            headers={"X-Correlation-ID": header_value},
        )

        assert response.json["has_correlation_id"] is False
        assert response.json["correlation_id"] is None

    def test_header_value_with_surrounding_whitespace_is_normalized(self) -> None:
        """Verify non-empty header values are trimmed before use."""
        client = self._client_with_resource()
        response = client.simulate_get(
            "/correlation",
            headers={"X-Correlation-ID": "  cid-123  "},
        )

        assert response.json["has_correlation_id"] is True
        assert response.json["correlation_id"] == "cid-123"
