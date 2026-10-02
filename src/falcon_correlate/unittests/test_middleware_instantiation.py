"""Unit tests for CorrelationIDMiddleware instantiation and interface."""

from __future__ import annotations

import inspect

from falcon_correlate import CorrelationIDMiddleware


class TestCorrelationIDMiddlewareInstantiation:
    """Tests for CorrelationIDMiddleware instantiation."""

    def test_can_instantiate_middleware(self) -> None:
        """Verify the middleware can be instantiated."""
        middleware = CorrelationIDMiddleware()
        assert middleware is not None, "expected middleware not to be None"

    def test_middleware_is_class_instance(self) -> None:
        """Verify the middleware is an instance of CorrelationIDMiddleware."""
        middleware = CorrelationIDMiddleware()
        failure_message = (
            "expected condition: isinstance(middleware, CorrelationIDMiddl..."
        )
        assert isinstance(middleware, CorrelationIDMiddleware), failure_message


class TestCorrelationIDMiddlewareInterface:
    """Tests for CorrelationIDMiddleware method interface."""

    def test_has_process_request_method(self) -> None:
        """Verify process_request method exists."""
        middleware = CorrelationIDMiddleware()
        failure_message = "expected hasattr(middleware, 'process_request') to be truthy"
        assert hasattr(middleware, "process_request"), failure_message
        failure_message = "expected callable(middleware.process_request) to be truthy"
        assert callable(middleware.process_request), failure_message

    def test_has_process_response_method(self) -> None:
        """Verify process_response method exists."""
        middleware = CorrelationIDMiddleware()
        failure_message = (
            "expected hasattr(middleware, 'process_response') to be truthy"
        )
        assert hasattr(middleware, "process_response"), failure_message
        failure_message = "expected callable(middleware.process_response) to be truthy"
        assert callable(middleware.process_response), failure_message

    def test_process_request_signature(self) -> None:
        """Verify process_request has correct parameter names."""
        middleware = CorrelationIDMiddleware()
        sig = inspect.signature(middleware.process_request)
        param_names = list(sig.parameters.keys())
        failure_message = "expected param_names to equal ['req', 'resp']"
        assert param_names == ["req", "resp"], failure_message

    def test_process_response_signature(self) -> None:
        """Verify process_response has correct parameter names."""
        middleware = CorrelationIDMiddleware()
        sig = inspect.signature(middleware.process_response)
        param_names = list(sig.parameters.keys())
        failure_message = (
            "expected condition: param_names == ['req', 'resp', 'resource'..."
        )
        assert param_names == ["req", "resp", "resource", "req_succeeded"], (
            failure_message
        )
