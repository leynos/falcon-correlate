"""Minimal Falcon WSGI example for the quickstart guide.

This module holds the smallest runnable application shown in
``docs/quickstart.md``. The tests import it to prove the guide's minimal route
still returns the documented response and correlation ID header.
"""

from __future__ import annotations

# [quickstart:minimal-imports]
import falcon

from falcon_correlate import CorrelationIDMiddleware

# [/quickstart:minimal-imports]


# [quickstart:minimal-resource]
class HelloResource:
    """Return a small JSON response.

    Examples
    --------
    >>> resource = HelloResource()
    >>> resource.message
    'hello'
    """

    message: str = "hello"

    def on_get(self, _req: falcon.Request, resp: falcon.Response) -> None:
        """Handle ``GET /hello``.

        Parameters
        ----------
        _req : falcon.Request
            The incoming Falcon request.
        resp : falcon.Response
            The Falcon response to populate.

        Returns
        -------
        None
            This handler only mutates ``resp``.

        Examples
        --------
        >>> resource = HelloResource()
        >>> hasattr(resource, "on_get")
        True
        """
        resp.media = {"message": self.message}


# [/quickstart:minimal-resource]


# [quickstart:minimal-app]
app: falcon.App = falcon.App(middleware=[CorrelationIDMiddleware()])
app.add_route("/hello", HelloResource())
# [/quickstart:minimal-app]
