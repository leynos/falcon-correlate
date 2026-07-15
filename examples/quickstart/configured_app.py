"""Configured Falcon WSGI example for the quickstart guide.

This module extends the minimal quickstart app with documented middleware
configuration. The guide and tests use it to show how the configurable header
name, trusted sources, and response echo settings fit into the same runnable
example.
"""

from __future__ import annotations

import falcon

from examples.quickstart.minimal_app import HelloResource

# [quickstart:configured-imports]
from falcon_correlate import CorrelationIDConfig, CorrelationIDMiddleware

# [/quickstart:configured-imports]

# [quickstart:configured-config]
config = CorrelationIDConfig(
    header_name="X-Correlation-ID",
    trusted_sources=frozenset({"127.0.0.1"}),
    echo_header_in_response=True,
)
# [/quickstart:configured-config]


# [quickstart:configured-app]
def build_app(app_config: CorrelationIDConfig) -> falcon.App:
    """Create the configured Falcon app.

    Parameters
    ----------
    app_config : CorrelationIDConfig
        Correlation-ID middleware configuration for the app.

    Returns
    -------
    falcon.App
        The configured Falcon application.

    Examples
    --------
    >>> configured = build_app(config)
    >>> isinstance(configured, falcon.App)
    True
    """
    configured_app = falcon.App(
        middleware=[CorrelationIDMiddleware(config=app_config)],
    )
    configured_app.add_route("/hello", HelloResource())
    return configured_app


app: falcon.App = build_app(config)
# [/quickstart:configured-app]
