"""Share the Falcon inbound boundary for the HTTPX BDD workflows.

These helpers are scoped to the wrapper and transport features. Wrapper steps
keep their HTTPX patches active around dispatch; transport steps use real
clients backed by recording transports.
"""

from __future__ import annotations

import typing as typ

import falcon
import falcon.asgi
import falcon.testing

from falcon_correlate import CorrelationIDMiddleware, CorrelationIDMiddlewareASGI
from falcon_correlate.middleware import DEFAULT_HEADER_NAME
from falcon_correlate.middleware_config import CorrelationIDConfig


def build_test_client(
    mode: typ.Literal["sync", "async"],
    resource: object,
    *,
    generated_id: str | None = None,
) -> falcon.testing.TestClient:
    """Build a WSGI or ASGI Falcon client with trusted-source middleware.

    Parameters
    ----------
    mode : {"sync", "async"}
        Select the WSGI application or the ASGI application.
    resource : object
        Falcon resource to register at the shared HTTPX route.
    generated_id : str | None, optional
        Fixed correlation ID returned by the middleware generator. Use the
        default generator when ``None``.

    Returns
    -------
    falcon.testing.TestClient
        Client bound to the configured Falcon application.
    """
    if generated_id is None:
        config = CorrelationIDConfig.from_kwargs(
            trusted_sources=["127.0.0.1"],
        )
    else:
        config = CorrelationIDConfig.from_kwargs(
            trusted_sources=["127.0.0.1"],
            generator=lambda: generated_id,
        )

    match mode:
        case "sync":
            middleware = CorrelationIDMiddleware(config=config)
            app = falcon.App(middleware=[middleware])
        case "async":
            middleware = CorrelationIDMiddlewareASGI(config=config)
            app = falcon.asgi.App(middleware=[middleware])

    app.add_route("/httpx", resource)
    return falcon.testing.TestClient(app)


def dispatch_inbound_request(
    client: falcon.testing.TestClient,
    correlation_id: str | None = None,
) -> falcon.testing.Result:
    """Dispatch a real Falcon request to the shared HTTPX BDD route.

    Parameters
    ----------
    client : falcon.testing.TestClient
        Client returned by ``build_test_client``.
    correlation_id : str | None, optional
        Inbound correlation ID header value. Omit the header when ``None``.

    Returns
    -------
    falcon.testing.Result
        Falcon response for the simulated request.
    """
    if correlation_id is None:
        return client.simulate_get("/httpx")

    return client.simulate_get(
        "/httpx",
        headers={DEFAULT_HEADER_NAME: correlation_id},
    )
