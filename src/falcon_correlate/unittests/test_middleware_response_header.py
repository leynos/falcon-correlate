"""Unit tests for middleware response correlation ID headers."""

from __future__ import annotations

import typing as typ

from falcon_correlate import CorrelationIDMiddleware

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    import falcon


class TestCorrelationIDResponseHeader:
    """Tests for response-header echoing in the WSGI middleware."""

    def test_process_response_echoes_correlation_id_when_enabled(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
        request_response_factory: cabc.Callable[
            ..., tuple[falcon.Request, falcon.Response]
        ],
    ) -> None:
        """Verify response processing echoes the active correlation ID by default."""
        middleware = CorrelationIDMiddleware(trusted_sources=["127.0.0.1"])

        def _inner() -> None:
            req, resp = request_response_factory(correlation_id="trusted-id")

            middleware.process_request(req, resp)
            middleware.process_response(
                req,
                resp,
                resource=None,
                req_succeeded=True,
            )

            assert resp.get_header("X-Correlation-ID") == "trusted-id"

        isolated_context(_inner)

    def test_process_response_omits_correlation_id_when_echo_disabled(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
        request_response_factory: cabc.Callable[
            ..., tuple[falcon.Request, falcon.Response]
        ],
    ) -> None:
        """Verify response processing honours disabled response-header echoing."""
        middleware = CorrelationIDMiddleware(
            trusted_sources=["127.0.0.1"],
            echo_header_in_response=False,
        )

        def _inner() -> None:
            req, resp = request_response_factory(correlation_id="trusted-id")

            middleware.process_request(req, resp)
            middleware.process_response(
                req,
                resp,
                resource=None,
                req_succeeded=True,
            )

            assert resp.get_header("X-Correlation-ID") is None

        isolated_context(_inner)
