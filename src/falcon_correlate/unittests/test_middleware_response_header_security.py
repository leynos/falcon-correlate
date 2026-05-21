"""Security-focused tests for response header echoing."""

from __future__ import annotations

import logging
import typing as typ

from falcon_correlate import CorrelationIDMiddleware

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    import falcon
    import pytest

_LOGGER_NAME = "falcon_correlate.middleware"


class TestCorrelationIDResponseHeaderSecurity:
    """Tests for response-header echo trust boundaries."""

    def test_process_response_skips_echo_without_middleware_token(
        self,
        caplog: pytest.LogCaptureFixture,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
        request_response_factory: cabc.Callable[
            ..., tuple[falcon.Request, falcon.Response]
        ],
    ) -> None:
        """Verify response echo requires middleware-owned request state."""
        middleware = CorrelationIDMiddleware()
        caplog.set_level(logging.DEBUG, logger=_LOGGER_NAME)

        def _inner() -> None:
            """Exercise response processing with a spoofed request context ID."""
            req, resp = request_response_factory()
            req.context.correlation_id = "spoofed-id"

            middleware.process_response(
                req,
                resp,
                resource=None,
                req_succeeded=True,
            )

            assert resp.get_header("X-Correlation-ID") is None, (
                "expected X-Correlation-ID header to be absent for spoofed "
                f"context ID but got {resp.get_header('X-Correlation-ID')!r}"
            )

        isolated_context(_inner)
        assert (
            "Correlation ID response header echo skipped; middleware token absent"
            in caplog.text
        ), (
            "expected caplog.text to contain middleware-token skip message but got "
            f"{caplog.text!r}"
        )
