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

    def _verify_middleware_hook_called(
        self,
        middleware: CorrelationIDMiddleware,
        call_log: list[str],
        expected_calls: list[str],
    ) -> None:
        """Verify middleware hooks are called during request processing.

        Creates a Falcon app with the given middleware, adds a simple resource
        that logs when called, makes a GET request, and verifies that all
        expected calls appear in the call log.

        Parameters
        ----------
        middleware : CorrelationIDMiddleware
            The middleware instance to test (typically a tracking subclass).
        call_log : list[str]
            A list that will be populated with call events by the middleware
            and resource.
        expected_calls : list[str]
            List of call event strings that should appear in the call_log
            after the request completes.

        """

        class LoggingResource:
            def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
                call_log.append("resource_called")
                resp.media = {"status": "ok"}

        app = falcon.App(middleware=[middleware])
        app.add_route("/test", LoggingResource())
        client = falcon.testing.TestClient(app)
        client.simulate_get("/test")

        for expected_call in expected_calls:
            assert expected_call in call_log

    def _create_tracking_middleware(
        self,
        call_log: list[str],
        hook_name: str,
        call_name: str,
    ) -> CorrelationIDMiddleware:
        """Create middleware that tracks a specific hook invocation.

        Parameters
        ----------
        call_log : list[str]
            List to append call events to.
        hook_name : str
            Name of the hook to track ('process_request' or 'process_response').
        call_name : str
            Name to append to call_log when hook is invoked.

        Returns
        -------
        CorrelationIDMiddleware
            Middleware instance that logs the specified hook invocation.

        """
        if hook_name == "process_request":

            class RequestTrackingMiddleware(CorrelationIDMiddleware):
                """Middleware that tracks process_request calls."""

                def process_request(
                    self,
                    req: falcon.Request,
                    resp: falcon.Response,
                ) -> None:
                    call_log.append(call_name)
                    super().process_request(req, resp)

            return RequestTrackingMiddleware()

        class ResponseTrackingMiddleware(CorrelationIDMiddleware):
            """Middleware that tracks process_response calls."""

            def process_response(
                self,
                req: falcon.Request,
                resp: falcon.Response,
                resource: object,
                req_succeeded: bool,  # noqa: FBT001, TD001, TD002, TD003  # FIXME: Falcon WSGI middleware interface requirement
            ) -> None:
                call_log.append(call_name)
                super().process_response(req, resp, resource, req_succeeded)

        return ResponseTrackingMiddleware()

    @pytest.mark.parametrize(
        ("hook_name", "call_name", "expected_order"),
        [
            (
                "process_request",
                "process_request_called",
                ["process_request_called", "resource_called"],
            ),
            (
                "process_response",
                "process_response_called",
                ["resource_called", "process_response_called"],
            ),
        ],
        ids=["process_request", "process_response"],
    )
    def test_middleware_hook_is_called(
        self,
        hook_name: str,
        call_name: str,
        expected_order: list[str],
    ) -> None:
        """Verify middleware hooks are invoked during request processing.

        Parameters
        ----------
        hook_name : str
            Name of the hook being tested ('process_request' or 'process_response').
        call_name : str
            Name logged when the hook is invoked.
        expected_order : list[str]
            Expected sequence of calls in the call log.

        """
        call_log: list[str] = []

        middleware = self._create_tracking_middleware(call_log, hook_name, call_name)

        self._verify_middleware_hook_called(
            middleware=middleware,
            call_log=call_log,
            expected_calls=expected_order,
        )
