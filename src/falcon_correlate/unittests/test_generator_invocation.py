"""Unit tests for generator invocation in process_request()."""

from __future__ import annotations

from unittest import mock

import falcon
import falcon.testing

from falcon_correlate import CorrelationIDMiddleware
from falcon_correlate.middleware import default_uuid7_generator
from falcon_correlate.unittests.uuid7_helpers import assert_uuid7_hex


class SimpleResource:
    """A simple Falcon resource for testing."""

    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """Handle GET requests with correlation ID from context."""
        correlation_id = getattr(req.context, "correlation_id", None)
        resp.media = {
            "correlation_id": correlation_id,
            "has_correlation_id": hasattr(req.context, "correlation_id"),
        }


class TestGeneratorInvocationWhenHeaderMissing:
    """Tests for generator invocation when no correlation ID header is present."""

    def test_generator_called_when_header_missing(self) -> None:
        """Verify generator is called when no correlation ID header present."""
        mock_generator = mock.MagicMock(return_value="generated-id-123")
        middleware = CorrelationIDMiddleware(generator=mock_generator)
        app = falcon.App(middleware=[middleware])
        app.add_route("/test", SimpleResource())
        client = falcon.testing.TestClient(app)

        response = client.simulate_get("/test")

        mock_generator.assert_called_once()
        assert response.json["correlation_id"] == "generated-id-123"

    def test_default_generator_used_when_custom_not_provided(self) -> None:
        """Verify default_uuid7_generator is used when no custom generator."""
        middleware = CorrelationIDMiddleware()
        app = falcon.App(middleware=[middleware])
        app.add_route("/test", SimpleResource())
        client = falcon.testing.TestClient(app)

        response = client.simulate_get("/test")

        # The default generator produces UUIDv7 hex strings
        correlation_id = response.json["correlation_id"]
        assert correlation_id is not None
        assert_uuid7_hex(correlation_id)

    def test_generator_output_stored_in_context(self) -> None:
        """Verify generator output is stored on req.context.correlation_id."""

        def custom_gen() -> str:
            return "context-stored-id"

        middleware = CorrelationIDMiddleware(generator=custom_gen)
        app = falcon.App(middleware=[middleware])
        app.add_route("/test", SimpleResource())
        client = falcon.testing.TestClient(app)

        response = client.simulate_get("/test")

        assert response.json["has_correlation_id"] is True
        assert response.json["correlation_id"] == "context-stored-id"


class TestGeneratorInvocationWhenSourceUntrusted:
    """Tests for generator invocation when request source is untrusted."""

    def test_generator_called_when_source_untrusted(self) -> None:
        """Verify generator is called when source is not trusted."""
        mock_generator = mock.MagicMock(return_value="generated-for-untrusted")
        # Trust only 10.0.0.1, but TestClient uses 127.0.0.1 by default
        middleware = CorrelationIDMiddleware(
            generator=mock_generator,
            trusted_sources=["10.0.0.1"],
        )
        app = falcon.App(middleware=[middleware])
        app.add_route("/test", SimpleResource())
        client = falcon.testing.TestClient(app)

        response = client.simulate_get(
            "/test",
            headers={"X-Correlation-ID": "external-id-should-be-rejected"},
        )

        mock_generator.assert_called_once()
        assert response.json["correlation_id"] == "generated-for-untrusted"

    def test_incoming_id_rejected_from_untrusted_source(self) -> None:
        """Verify incoming ID is rejected when source is untrusted."""

        def custom_gen() -> str:
            return "new-generated-id"

        # Trust only 10.0.0.1, but TestClient uses 127.0.0.1 by default
        middleware = CorrelationIDMiddleware(
            generator=custom_gen,
            trusted_sources=["10.0.0.1"],
        )
        app = falcon.App(middleware=[middleware])
        app.add_route("/test", SimpleResource())
        client = falcon.testing.TestClient(app)

        response = client.simulate_get(
            "/test",
            headers={"X-Correlation-ID": "untrusted-incoming-id"},
        )

        # The incoming ID should be ignored; generator output should be used
        assert response.json["correlation_id"] == "new-generated-id"

    def test_generator_called_when_no_trusted_sources_configured(self) -> None:
        """Verify generator is called when no trusted sources are configured."""
        mock_generator = mock.MagicMock(return_value="no-trust-generated-id")
        middleware = CorrelationIDMiddleware(generator=mock_generator)
        app = falcon.App(middleware=[middleware])
        app.add_route("/test", SimpleResource())
        client = falcon.testing.TestClient(app)

        response = client.simulate_get(
            "/test",
            headers={"X-Correlation-ID": "should-be-rejected"},
        )

        mock_generator.assert_called_once()
        assert response.json["correlation_id"] == "no-trust-generated-id"


class TestGeneratorInvocationWithTrustedSource:
    """Tests for generator behaviour with trusted sources."""

    def test_generator_not_called_when_trusted_source_provides_header(self) -> None:
        """Verify generator is NOT called when trusted source provides header."""
        mock_generator = mock.MagicMock(return_value="should-not-be-used")
        # Trust 127.0.0.1, which is TestClient's default remote_addr
        middleware = CorrelationIDMiddleware(
            generator=mock_generator,
            trusted_sources=["127.0.0.1"],
        )
        app = falcon.App(middleware=[middleware])
        app.add_route("/test", SimpleResource())
        client = falcon.testing.TestClient(app)

        response = client.simulate_get(
            "/test",
            headers={"X-Correlation-ID": "trusted-incoming-id"},
        )

        mock_generator.assert_not_called()
        assert response.json["correlation_id"] == "trusted-incoming-id"

    def test_generator_called_when_trusted_source_sends_empty_header(self) -> None:
        """Verify generator is called when trusted source sends empty header."""
        mock_generator = mock.MagicMock(return_value="generated-for-empty")
        middleware = CorrelationIDMiddleware(
            generator=mock_generator,
            trusted_sources=["127.0.0.1"],
        )
        app = falcon.App(middleware=[middleware])
        app.add_route("/test", SimpleResource())
        client = falcon.testing.TestClient(app)

        response = client.simulate_get(
            "/test",
            headers={"X-Correlation-ID": "   "},  # whitespace-only
        )

        mock_generator.assert_called_once()
        assert response.json["correlation_id"] == "generated-for-empty"


class TestCustomGeneratorBehaviour:
    """Tests for custom generator behaviour."""

    def test_custom_generator_output_used_as_correlation_id(self) -> None:
        """Verify custom generator output becomes the correlation ID."""

        def my_generator() -> str:
            return "my-custom-correlation-id"

        middleware = CorrelationIDMiddleware(generator=my_generator)
        app = falcon.App(middleware=[middleware])
        app.add_route("/test", SimpleResource())
        client = falcon.testing.TestClient(app)

        response = client.simulate_get("/test")

        assert response.json["correlation_id"] == "my-custom-correlation-id"

    def test_generator_called_for_each_request(self) -> None:
        """Verify generator is called for each request."""
        call_count = 0
        expected_call_count = 2

        def counting_generator() -> str:
            nonlocal call_count
            call_count += 1
            return f"request-{call_count}"

        middleware = CorrelationIDMiddleware(generator=counting_generator)
        app = falcon.App(middleware=[middleware])
        app.add_route("/test", SimpleResource())
        client = falcon.testing.TestClient(app)

        response1 = client.simulate_get("/test")
        response2 = client.simulate_get("/test")

        assert call_count == expected_call_count
        assert response1.json["correlation_id"] == "request-1"
        assert response2.json["correlation_id"] == "request-2"

    def test_middleware_generator_property_returns_configured_generator(self) -> None:
        """Verify middleware.generator returns the configured generator."""

        def my_gen() -> str:
            return "test"

        middleware = CorrelationIDMiddleware(generator=my_gen)
        assert middleware.generator is my_gen

    def test_middleware_uses_default_generator_when_none_provided(self) -> None:
        """Verify middleware uses default_uuid7_generator when no generator given."""
        middleware = CorrelationIDMiddleware()
        assert middleware.generator is default_uuid7_generator
