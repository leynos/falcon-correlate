"""Shared Falcon ASGI resources for tests."""

from __future__ import annotations

import asyncio
import typing as typ

from falcon_correlate import correlation_id_var

if typ.TYPE_CHECKING:
    import falcon.asgi


class ASGICorrelationEchoResource:
    """Falcon ASGI resource that echoes correlation state for tests.

    `ASGICorrelationEchoResource` reads the correlation ID that middleware
    stores on `req.context` and the active value returned by
    `correlation_id_var.get()`. Tests use the resource to prove that ASGI
    application code can observe the same correlation ID through both access
    paths during a request.

    Examples
    --------
    A Falcon ASGI test can mount the resource and inspect the JSON response::

        app.add_route("/correlation", ASGICorrelationEchoResource())
        result = client.simulate_get("/correlation")
        assert result.json["context_correlation_id"] == "request-id"

    """

    async def on_get(
        self,
        req: falcon.asgi.Request,
        resp: falcon.asgi.Response,
    ) -> None:
        """Return correlation IDs visible to application code.

        Parameters
        ----------
        req : falcon.asgi.Request
            Incoming Falcon ASGI request with middleware-populated
            `req.context.correlation_id`.
        resp : falcon.asgi.Response
            Outgoing Falcon ASGI response whose `resp.media` mapping is set by
            this handler.

        Returns
        -------
        None
            The method mutates `resp.media` and does not return a value.

        Notes
        -----
        `on_get` reads `correlation_id_var.get()` before middleware response
        cleanup, so the returned `contextvar_correlation_id` proves the
        request-local context variable is available inside ASGI resources.

        Examples
        --------
        When middleware has established the ID `request-id`, `resp.media` is::

            {
                "context_correlation_id": "request-id",
                "contextvar_correlation_id": "request-id",
            }

        """
        resp.media = {
            "context_correlation_id": req.context.correlation_id,
            "contextvar_correlation_id": correlation_id_var.get(),
        }


class ASGIInterleavedCorrelationResource:
    """Falcon ASGI resource that waits for concurrent requests to overlap."""

    def __init__(self, *, expected_requests: int) -> None:
        """Initialise the request barrier for the expected concurrency level."""
        self._expected_requests = expected_requests
        self._arrived_requests = 0
        self._all_requests_arrived = asyncio.Event()
        self._lock = asyncio.Lock()

    async def on_get(
        self,
        req: falcon.asgi.Request,
        resp: falcon.asgi.Response,
    ) -> None:
        """Return correlation state observed before and after request overlap."""
        contextvar_before_wait = correlation_id_var.get()

        async with self._lock:
            self._arrived_requests += 1
            if self._arrived_requests == self._expected_requests:
                self._all_requests_arrived.set()

        await asyncio.wait_for(self._all_requests_arrived.wait(), timeout=2.0)
        await asyncio.sleep(0)

        resp.media = {
            "context_correlation_id": req.context.correlation_id,
            "contextvar_correlation_id": contextvar_before_wait,
            "contextvar_correlation_id_after_wait": correlation_id_var.get(),
        }
