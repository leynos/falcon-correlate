"""Unit tests for CorrelationIDMiddleware."""

from __future__ import annotations

import inspect
from http import HTTPStatus

import falcon
import falcon.testing
import pytest

from falcon_correlate import CorrelationIDMiddleware


class TestCorrelationIDMiddlewareInstantiation:
    """Tests for CorrelationIDMiddleware instantiation."""

    def test_can_instantiate_middleware(self) -> None:
        """Verify the middleware can be instantiated."""
        middleware = CorrelationIDMiddleware()
        assert middleware is not None

    def test_middleware_is_class_instance(self) -> None:
        """Verify the middleware is an instance of CorrelationIDMiddleware."""
        middleware = CorrelationIDMiddleware()
        assert isinstance(middleware, CorrelationIDMiddleware)


class TestCorrelationIDMiddlewareInterface:
    """Tests for CorrelationIDMiddleware method interface."""

    def test_has_process_request_method(self) -> None:
        """Verify process_request method exists."""
        middleware = CorrelationIDMiddleware()
        assert hasattr(middleware, "process_request")
        assert callable(middleware.process_request)

    def test_has_process_response_method(self) -> None:
        """Verify process_response method exists."""
        middleware = CorrelationIDMiddleware()
        assert hasattr(middleware, "process_response")
        assert callable(middleware.process_response)

    def test_process_request_signature(self) -> None:
        """Verify process_request has correct parameter names."""
        middleware = CorrelationIDMiddleware()
        sig = inspect.signature(middleware.process_request)
        param_names = list(sig.parameters.keys())
        assert param_names == ["req", "resp"]

    def test_process_response_signature(self) -> None:
        """Verify process_response has correct parameter names."""
        middleware = CorrelationIDMiddleware()
        sig = inspect.signature(middleware.process_response)
        param_names = list(sig.parameters.keys())
        assert param_names == ["req", "resp", "resource", "req_succeeded"]


class TestCorrelationIDMiddlewareWithFalcon:
    """Tests for CorrelationIDMiddleware integration with Falcon."""

    @pytest.fixture
    def app_with_middleware(self) -> falcon.App:
        """Create a Falcon app with CorrelationIDMiddleware installed."""
        middleware = CorrelationIDMiddleware()
        return falcon.App(middleware=[middleware])

    @pytest.fixture
    def client(self, app_with_middleware: falcon.App) -> falcon.testing.TestClient:
        """Create a test client for the Falcon app."""
        return falcon.testing.TestClient(app_with_middleware)

    def test_middleware_can_be_added_to_falcon_app(
        self,
        app_with_middleware: falcon.App,
    ) -> None:
        """Verify middleware can be added to a Falcon application."""
        assert app_with_middleware is not None

    def test_request_completes_with_middleware(
        self,
        client: falcon.testing.TestClient,
    ) -> None:
        """Verify requests complete successfully with middleware installed."""
        # Request to non-existent route returns 404, but the middleware runs
        result = client.simulate_get("/")
        # 404 is expected since no routes are defined
        assert result.status_code == HTTPStatus.NOT_FOUND

    def test_process_request_is_called(self) -> None:
        """Verify process_request is invoked during request processing."""
        call_log: list[str] = []

        class TrackingMiddleware(CorrelationIDMiddleware):
            """Middleware that tracks method calls."""

            def process_request(
                self,
                req: falcon.Request,
                resp: falcon.Response,
            ) -> None:
                call_log.append("process_request_called")
                super().process_request(req, resp)

        class LoggingResource:
            def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
                call_log.append("resource_called")
                resp.media = {"status": "ok"}

        app = falcon.App(middleware=[TrackingMiddleware()])
        app.add_route("/test", LoggingResource())
        client = falcon.testing.TestClient(app)
        client.simulate_get("/test")

        assert "process_request_called" in call_log
        assert "resource_called" in call_log

    def test_process_response_is_called(self) -> None:
        """Verify process_response is invoked during request processing."""
        call_log: list[str] = []

        class TrackingMiddleware(CorrelationIDMiddleware):
            """Middleware that tracks method calls."""

            def process_response(
                self,
                req: falcon.Request,
                resp: falcon.Response,
                resource: object,
                req_succeeded: bool,  # noqa: FBT001
            ) -> None:
                call_log.append("process_response_called")
                super().process_response(req, resp, resource, req_succeeded)

        class LoggingResource:
            def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
                call_log.append("resource_called")
                resp.media = {"status": "ok"}

        app = falcon.App(middleware=[TrackingMiddleware()])
        app.add_route("/test", LoggingResource())
        client = falcon.testing.TestClient(app)
        client.simulate_get("/test")

        assert "resource_called" in call_log
        assert "process_response_called" in call_log
