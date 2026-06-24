"""Configured Falcon WSGI app from the quickstart guide."""

from __future__ import annotations

import falcon

from examples.quickstart.minimal_app import HelloResource
from falcon_correlate import CorrelationIDConfig, CorrelationIDMiddleware

# [quickstart:configured-config]
config = CorrelationIDConfig(
    header_name="X-Correlation-ID",
    trusted_sources=frozenset({"127.0.0.1"}),
    echo_header_in_response=True,
)
# [/quickstart:configured-config]


# [quickstart:configured-app]
app: falcon.App = falcon.App(
    middleware=[CorrelationIDMiddleware(config=config)],
)
app.add_route("/hello", HelloResource())
# [/quickstart:configured-app]
