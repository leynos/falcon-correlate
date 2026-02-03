"""Unit tests for generator invocation in process_request()."""

from __future__ import annotations

import typing as typ
from unittest import mock

import falcon
import falcon.testing
import pytest

from falcon_correlate import CorrelationIDMiddleware
from falcon_correlate.middleware import default_uuid7_generator
from falcon_correlate.unittests.uuid7_helpers import assert_uuid7_hex

if typ.TYPE_CHECKING:
    import collections.abc as cabc


class _MiddlewareKwargs(typ.TypedDict, total=False):
    """Type definition for CorrelationIDMiddleware keyword arguments."""

    generator: cabc.Callable[[], str]
    trusted_sources: cabc.Iterable[str]


class SimpleResource:
    """A simple Falcon resource for testing."""

    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """Handle GET requests with correlation ID from context."""
        correlation_id = getattr(req.context, "correlation_id", None)
        resp.media = {
            "correlation_id": correlation_id,
            "has_correlation_id": hasattr(req.context, "correlation_id"),
        }


def _verify_generator_called_and_id_matches(
    client: falcon.testing.TestClient,
    mock_generator: mock.MagicMock,
    expected_id: str,
    headers: dict[str, str] | None = None,
) -> None:
    """Verify generator was called once and produced the expected correlation ID.

    Args:
        client: The Falcon test client to use.
        mock_generator: The mock generator to verify was called.
        expected_id: The expected correlation ID in the response.
        headers: Optional headers to include in the request.

    """
    response = client.simulate_get("/test", headers=headers)

    mock_generator.assert_called_once()
    assert response.json["has_correlation_id"] is True, (
        "Expected correlation ID to be set on request context"
    )
    assert response.json["correlation_id"] == expected_id, (
        f"Expected correlation ID '{expected_id}', "
        f"got '{response.json['correlation_id']}'"
    )


@pytest.fixture
def simple_resource() -> SimpleResource:
    """Provide a SimpleResource instance for testing."""
    return SimpleResource()


@pytest.fixture
def create_test_client(
    simple_resource: SimpleResource,
) -> cabc.Callable[..., falcon.testing.TestClient]:
    """Build test clients with configurable middleware.

    Args:
        simple_resource: The resource fixture to add to the app.

    Returns:
        A factory function that creates TestClient instances.

    """

    def _create(
        generator: cabc.Callable[[], str] | None = None,
        trusted_sources: cabc.Iterable[str] | None = None,
    ) -> falcon.testing.TestClient:
        """Build a test client with the specified middleware configuration.

        Args:
            generator: Optional custom generator for correlation IDs.
            trusted_sources: Optional list of trusted source IPs/CIDRs.

        Returns:
            A configured Falcon TestClient.

        """
        kwargs: _MiddlewareKwargs = {}
        if generator is not None:
            kwargs["generator"] = generator
        if trusted_sources is not None:
            kwargs["trusted_sources"] = trusted_sources

        middleware = CorrelationIDMiddleware(**kwargs)
        app = falcon.App(middleware=[middleware])
        app.add_route("/test", simple_resource)
        return falcon.testing.TestClient(app)

    return _create


class TestGeneratorInvocationWhenHeaderMissing:
    """Tests for generator invocation when no correlation ID header is present."""

    def test_generator_called_when_header_missing(
        self,
        create_test_client: cabc.Callable[..., falcon.testing.TestClient],
    ) -> None:
        """Verify generator is called when no correlation ID header present."""
        mock_generator = mock.MagicMock(return_value="generated-id-123")
        client = create_test_client(generator=mock_generator)

        _verify_generator_called_and_id_matches(
            client, mock_generator, "generated-id-123"
        )

    def test_default_generator_used_when_custom_not_provided(
        self,
        create_test_client: cabc.Callable[..., falcon.testing.TestClient],
    ) -> None:
        """Verify default_uuid7_generator is used when no custom generator."""
        client = create_test_client()

        response = client.simulate_get("/test")

        # The default generator produces UUIDv7 hex strings
        correlation_id = response.json["correlation_id"]
        assert correlation_id is not None
        assert_uuid7_hex(correlation_id)

    def test_generator_output_stored_in_context(
        self,
        create_test_client: cabc.Callable[..., falcon.testing.TestClient],
    ) -> None:
        """Verify generator output is stored on req.context.correlation_id."""

        def custom_gen() -> str:
            return "context-stored-id"

        client = create_test_client(generator=custom_gen)

        response = client.simulate_get("/test")

        assert response.json["has_correlation_id"] is True
        assert response.json["correlation_id"] == "context-stored-id"


class TestGeneratorInvocationWhenSourceUntrusted:
    """Tests for generator invocation when request source is untrusted."""

    @pytest.mark.parametrize(
        ("trusted_sources", "incoming_header"),
        [
            pytest.param(
                ["10.0.0.1"],
                "external-id-should-be-rejected",
                id="untrusted_source",
            ),
            pytest.param(
                None,
                "should-be-rejected",
                id="no_trusted_sources_configured",
            ),
        ],
    )
    def test_generator_called_for_untrusted_scenarios(
        self,
        create_test_client: cabc.Callable[..., falcon.testing.TestClient],
        trusted_sources: list[str] | None,
        incoming_header: str,
    ) -> None:
        """Verify generator is called when source is untrusted or no sources configured.

        When trusted_sources is configured but doesn't include the client IP,
        or when no trusted sources are configured at all, the generator should
        be called and any incoming correlation ID header should be rejected.
        """
        expected_id = "generated-for-untrusted-scenario"
        mock_generator = mock.MagicMock(return_value=expected_id)
        client = create_test_client(
            generator=mock_generator,
            trusted_sources=trusted_sources,
        )

        _verify_generator_called_and_id_matches(
            client,
            mock_generator,
            expected_id,
            headers={"X-Correlation-ID": incoming_header},
        )

    def test_incoming_id_rejected_from_untrusted_source(
        self,
        create_test_client: cabc.Callable[..., falcon.testing.TestClient],
    ) -> None:
        """Verify incoming ID is rejected when source is untrusted."""

        def custom_gen() -> str:
            return "new-generated-id"

        # Trust only 10.0.0.1, but TestClient uses 127.0.0.1 by default
        client = create_test_client(
            generator=custom_gen,
            trusted_sources=["10.0.0.1"],
        )

        response = client.simulate_get(
            "/test",
            headers={"X-Correlation-ID": "untrusted-incoming-id"},
        )

        # The incoming ID should be ignored; generator output should be used
        assert response.json["correlation_id"] == "new-generated-id"


class TestGeneratorInvocationWithTrustedSource:
    """Tests for generator behaviour with trusted sources."""

    def test_generator_not_called_when_trusted_source_provides_header(
        self,
        create_test_client: cabc.Callable[..., falcon.testing.TestClient],
    ) -> None:
        """Verify generator is NOT called when trusted source provides header."""
        mock_generator = mock.MagicMock(return_value="should-not-be-used")
        # Trust 127.0.0.1, which is TestClient's default remote_addr
        client = create_test_client(
            generator=mock_generator,
            trusted_sources=["127.0.0.1"],
        )

        response = client.simulate_get(
            "/test",
            headers={"X-Correlation-ID": "trusted-incoming-id"},
        )

        mock_generator.assert_not_called()
        assert response.json["correlation_id"] == "trusted-incoming-id"

    def test_generator_called_when_trusted_source_sends_empty_header(
        self,
        create_test_client: cabc.Callable[..., falcon.testing.TestClient],
    ) -> None:
        """Verify generator is called when trusted source sends empty header."""
        mock_generator = mock.MagicMock(return_value="generated-for-empty")
        client = create_test_client(
            generator=mock_generator,
            trusted_sources=["127.0.0.1"],
        )

        _verify_generator_called_and_id_matches(
            client,
            mock_generator,
            "generated-for-empty",
            headers={"X-Correlation-ID": "   "},  # whitespace-only
        )


class TestCustomGeneratorBehaviour:
    """Tests for custom generator behaviour."""

    def test_custom_generator_output_used_as_correlation_id(
        self,
        create_test_client: cabc.Callable[..., falcon.testing.TestClient],
    ) -> None:
        """Verify custom generator output becomes the correlation ID."""

        def my_generator() -> str:
            return "my-custom-correlation-id"

        client = create_test_client(generator=my_generator)

        response = client.simulate_get("/test")

        assert response.json["correlation_id"] == "my-custom-correlation-id"

    def test_generator_called_for_each_request(
        self,
        create_test_client: cabc.Callable[..., falcon.testing.TestClient],
    ) -> None:
        """Verify generator is called for each request."""
        call_count = 0
        expected_call_count = 2

        def counting_generator() -> str:
            nonlocal call_count
            call_count += 1
            return f"request-{call_count}"

        client = create_test_client(generator=counting_generator)

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
