"""Shared Falcon ASGI resources for tests."""

from __future__ import annotations

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
