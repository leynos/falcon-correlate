"""Unit tests for CorrelationIDMiddleware."""

from __future__ import annotations

import inspect
from http import HTTPStatus

import falcon
import falcon.testing
import pytest

from falcon_correlate import CorrelationIDConfig, CorrelationIDMiddleware
from falcon_correlate.middleware import default_uuid7_generator


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


class TestCorrelationIDHeaderRetrieval:
    """Tests for correlation ID header retrieval."""

    class CorrelationEchoResource:
        """Resource that echoes correlation ID context in the response."""

        def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
            """Return correlation ID context in the response body."""
            correlation_id = getattr(req.context, "correlation_id", None)
            resp.media = {
                "correlation_id": correlation_id,
                "has_correlation_id": hasattr(req.context, "correlation_id"),
            }

    def _client_with_resource(self) -> falcon.testing.TestClient:
        """Create a test client with the correlation echo resource."""
        middleware = CorrelationIDMiddleware()
        app = falcon.App(middleware=[middleware])
        app.add_route("/correlation", self.CorrelationEchoResource())
        return falcon.testing.TestClient(app)

    def test_header_value_is_stored_in_request_context(self) -> None:
        """Verify a present header is stored on req.context."""
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


class TestCorrelationIDMiddlewareConfiguration:
    """Tests for CorrelationIDMiddleware configuration options."""

    # Default value tests

    def test_default_header_name(self) -> None:
        """Verify default header_name is X-Correlation-ID."""
        middleware = CorrelationIDMiddleware()
        assert middleware.header_name == "X-Correlation-ID"

    def test_default_trusted_sources_is_empty_frozenset(self) -> None:
        """Verify default trusted_sources is an empty frozenset."""
        middleware = CorrelationIDMiddleware()
        assert middleware.trusted_sources == frozenset()
        assert isinstance(middleware.trusted_sources, frozenset)

    def test_default_generator_is_default_uuid7_generator(self) -> None:
        """Verify default generator is default_uuid7_generator."""
        middleware = CorrelationIDMiddleware()
        assert middleware.generator is default_uuid7_generator

    def test_default_uuid7_generator_raises_not_implemented_error(self) -> None:
        """Verify default_uuid7_generator currently raises NotImplementedError.

        This documents the interim behaviour until UUIDv7 generation is implemented.
        """
        with pytest.raises(NotImplementedError) as exc_info:
            default_uuid7_generator()

        assert "not yet implemented" in str(exc_info.value)

    def test_default_validator_is_none(self) -> None:
        """Verify default validator is None."""
        middleware = CorrelationIDMiddleware()
        assert middleware.validator is None

    def test_default_echo_header_in_response_is_true(self) -> None:
        """Verify default echo_header_in_response is True."""
        middleware = CorrelationIDMiddleware()
        assert middleware.echo_header_in_response is True

    # Custom configuration tests

    def test_custom_header_name(self) -> None:
        """Verify custom header_name is stored."""
        middleware = CorrelationIDMiddleware(header_name="X-Request-ID")
        assert middleware.header_name == "X-Request-ID"

    def test_custom_trusted_sources_from_list(self) -> None:
        """Verify trusted_sources from list is stored as frozenset."""
        sources = ["127.0.0.1", "10.0.0.1"]
        middleware = CorrelationIDMiddleware(trusted_sources=sources)
        assert middleware.trusted_sources == frozenset(sources)

    def test_custom_trusted_sources_from_tuple(self) -> None:
        """Verify trusted_sources from tuple is stored as frozenset."""
        sources = ("127.0.0.1", "192.168.1.1")
        middleware = CorrelationIDMiddleware(trusted_sources=sources)
        assert middleware.trusted_sources == frozenset(sources)

    def test_custom_trusted_sources_from_set(self) -> None:
        """Verify trusted_sources from set is stored as frozenset."""
        sources = {"127.0.0.1", "10.0.0.1"}
        middleware = CorrelationIDMiddleware(trusted_sources=sources)
        assert middleware.trusted_sources == frozenset(sources)

    def test_custom_generator(self) -> None:
        """Verify custom generator is stored."""

        def custom_gen() -> str:
            return "custom-id"

        middleware = CorrelationIDMiddleware(generator=custom_gen)
        assert middleware.generator is custom_gen

    def test_custom_validator(self) -> None:
        """Verify custom validator is stored."""

        def custom_validator(value: str) -> bool:
            return len(value) > 0

        middleware = CorrelationIDMiddleware(validator=custom_validator)
        assert middleware.validator is custom_validator

    def test_echo_header_in_response_false(self) -> None:
        """Verify echo_header_in_response can be set to False."""
        middleware = CorrelationIDMiddleware(echo_header_in_response=False)
        assert middleware.echo_header_in_response is False

    # Validation and error handling tests

    def test_empty_header_name_raises_value_error(self) -> None:
        """Verify empty header_name raises ValueError."""
        with pytest.raises(ValueError, match="header_name must not be empty"):
            CorrelationIDMiddleware(header_name="")

    def test_whitespace_header_name_raises_value_error(self) -> None:
        """Verify whitespace-only header_name raises ValueError."""
        with pytest.raises(ValueError, match="header_name must not be empty"):
            CorrelationIDMiddleware(header_name="   ")

    def test_empty_trusted_source_raises_value_error(self) -> None:
        """Verify empty string in trusted_sources raises ValueError."""
        with pytest.raises(
            ValueError,
            match="trusted_sources must not contain empty strings",
        ):
            CorrelationIDMiddleware(trusted_sources=["127.0.0.1", ""])

    def test_whitespace_trusted_source_raises_value_error(self) -> None:
        """Verify whitespace-only string in trusted_sources raises ValueError."""
        with pytest.raises(
            ValueError,
            match="trusted_sources must not contain empty strings",
        ):
            CorrelationIDMiddleware(trusted_sources=["127.0.0.1", "   "])

    def test_non_callable_generator_raises_type_error(self) -> None:
        """Verify non-callable generator raises TypeError."""
        with pytest.raises(TypeError, match="generator must be callable"):
            CorrelationIDMiddleware(generator="not-callable")  # type: ignore[arg-type]

    def test_non_callable_validator_raises_type_error(self) -> None:
        """Verify non-callable validator raises TypeError."""
        with pytest.raises(TypeError, match="validator must be callable"):
            CorrelationIDMiddleware(validator="not-callable")  # type: ignore[arg-type]

    def test_unknown_kwarg_raises_type_error(self) -> None:
        """Verify unknown keyword arguments raise TypeError with helpful message."""
        with pytest.raises(TypeError) as excinfo:
            CorrelationIDMiddleware(foo=1)  # type: ignore[call-arg]

        message = str(excinfo.value)
        assert "foo" in message
        assert "Unknown keyword arguments" in message

    def test_config_and_kwargs_conflict_raises_value_error(self) -> None:
        """Verify providing both config and other kwargs raises ValueError."""
        config = CorrelationIDConfig()

        with pytest.raises(
            ValueError,
            match="Cannot specify both 'config' and individual parameters",
        ):
            CorrelationIDMiddleware(
                config=config,
                header_name="X-Request-ID",
            )

    # Immutability tests

    def test_trusted_sources_is_immutable(self) -> None:
        """Verify trusted_sources cannot be modified after creation."""
        sources = ["127.0.0.1"]
        middleware = CorrelationIDMiddleware(trusted_sources=sources)
        # Modifying original list should not affect middleware
        sources.append("10.0.0.1")
        assert middleware.trusted_sources == frozenset(["127.0.0.1"])

    # Combined configuration tests

    def test_all_parameters_can_be_set(self) -> None:
        """Verify all parameters can be set together."""

        def gen() -> str:
            return "id"

        def val(s: str) -> bool:
            return True

        middleware = CorrelationIDMiddleware(
            header_name="X-Custom-ID",
            trusted_sources=["10.0.0.1"],
            generator=gen,
            validator=val,
            echo_header_in_response=False,
        )
        assert middleware.header_name == "X-Custom-ID"
        assert middleware.trusted_sources == frozenset(["10.0.0.1"])
        assert middleware.generator is gen
        assert middleware.validator is val
        assert middleware.echo_header_in_response is False

    # Config-based construction tests

    def test_config_based_construction_uses_given_config(self) -> None:
        """Verify supplying a CorrelationIDConfig sets and exposes the same config."""
        cfg = CorrelationIDConfig(
            header_name="X-Request-ID",
            echo_header_in_response=False,
            trusted_sources=frozenset({"127.0.0.1", "10.0.0.1"}),
        )

        middleware = CorrelationIDMiddleware(config=cfg)

        # The middleware should hold a reference to the exact config object
        assert middleware.config is cfg

        # And its exposed properties should reflect the config values
        assert middleware.header_name == cfg.header_name
        assert middleware.echo_header_in_response == cfg.echo_header_in_response
        assert middleware.trusted_sources == cfg.trusted_sources

    def test_config_from_kwargs_equivalence(self) -> None:
        """Verify CorrelationIDConfig.from_kwargs matches direct construction."""
        header_name = "X-Request-ID"
        trusted_sources_list = ["127.0.0.1", "10.0.0.1"]
        echo_header_in_response = False

        cfg_direct = CorrelationIDConfig(
            header_name=header_name,
            trusted_sources=frozenset(trusted_sources_list),
            echo_header_in_response=echo_header_in_response,
        )
        cfg_from_kwargs = CorrelationIDConfig.from_kwargs(
            header_name=header_name,
            trusted_sources=trusted_sources_list,
            echo_header_in_response=echo_header_in_response,
        )

        # from_kwargs should produce an equivalent configuration
        assert cfg_from_kwargs.header_name == cfg_direct.header_name
        assert (
            cfg_from_kwargs.echo_header_in_response
            == cfg_direct.echo_header_in_response
        )
        assert cfg_from_kwargs.trusted_sources == cfg_direct.trusted_sources


class TestCorrelationIDConfigValidation:
    """Direct unit tests for CorrelationIDConfig validation."""

    def test_config_empty_header_name_raises_value_error(self) -> None:
        """Verify empty header_name on CorrelationIDConfig raises ValueError."""
        with pytest.raises(ValueError, match="header_name must not be empty"):
            CorrelationIDConfig(header_name="")

    def test_config_whitespace_header_name_raises_value_error(self) -> None:
        """Verify whitespace-only header_name raises ValueError."""
        with pytest.raises(ValueError, match="header_name must not be empty"):
            CorrelationIDConfig(header_name="   ")

    def test_config_empty_trusted_source_raises_value_error(self) -> None:
        """Verify empty string in trusted_sources raises ValueError."""
        with pytest.raises(
            ValueError,
            match="trusted_sources must not contain empty strings",
        ):
            CorrelationIDConfig(trusted_sources=frozenset(["127.0.0.1", ""]))

    def test_config_whitespace_trusted_source_raises_value_error(self) -> None:
        """Verify whitespace-only string in trusted_sources raises ValueError."""
        with pytest.raises(
            ValueError,
            match="trusted_sources must not contain empty strings",
        ):
            CorrelationIDConfig(trusted_sources=frozenset(["127.0.0.1", "   "]))

    def test_config_non_callable_generator_raises_type_error(self) -> None:
        """Verify non-callable generator on CorrelationIDConfig raises TypeError."""
        with pytest.raises(TypeError, match="generator must be callable"):
            CorrelationIDConfig(generator="not-a-callable")  # type: ignore[arg-type]

    def test_config_non_callable_validator_raises_type_error(self) -> None:
        """Verify non-callable validator on CorrelationIDConfig raises TypeError."""
        with pytest.raises(TypeError, match="validator must be callable"):
            CorrelationIDConfig(validator="not-a-callable")  # type: ignore[arg-type]


class TestPublicExports:
    """Tests for package public exports."""

    def test_public_exports_in_all(self) -> None:
        """Verify expected names are present in __all__."""
        import falcon_correlate

        assert "CorrelationIDMiddleware" in falcon_correlate.__all__
        assert "CorrelationIDConfig" in falcon_correlate.__all__
        assert "default_uuid7_generator" in falcon_correlate.__all__

    def test_default_uuid7_generator_importable_from_root(self) -> None:
        """Verify default_uuid7_generator can be imported from package root."""
        from falcon_correlate import default_uuid7_generator as gen

        with pytest.raises(NotImplementedError):
            gen()
