"""Falcon ASGI correlation ID middleware implementation.

This module exposes the async Falcon middleware hooks while reusing the WSGI
middleware lifecycle implemented by ``_CorrelationIDMiddlewareBase`` in
``middleware.py``. That split keeps ASGI integration focused on coroutine hook
signatures and shares request selection, ContextVar state, response-header
echoing, and cleanup with the WSGI variant.
"""

from __future__ import annotations

import typing as typ

from .middleware import _CorrelationIDMiddlewareBase

if typ.TYPE_CHECKING:
    import falcon.asgi


class CorrelationIDMiddlewareASGI(_CorrelationIDMiddlewareBase):
    """Middleware for managing correlation IDs in Falcon ASGI applications.

    This middleware handles the lifecycle of correlation IDs for
    `falcon.asgi.App`, extracting them from incoming request headers or
    generating new ones, making them available throughout the request
    lifecycle, and optionally echoing them in response headers. The public
    hooks are coroutines, while request selection, response-header echoing, and
    context cleanup are shared with the WSGI middleware through
    `_CorrelationIDMiddlewareBase`.

    Parameters
    ----------
    config : CorrelationIDConfig | None
        A pre-built configuration object. If provided, no other keyword
        arguments may be specified. Defaults to ``None``.
    **kwargs
        Individual configuration parameters. Valid keys are: ``header_name``,
        ``trusted_sources``, ``generator``, ``validator``, and
        ``echo_header_in_response``. See
        :meth:`CorrelationIDConfig.from_kwargs` for parameter details.

    Attributes
    ----------
    config : CorrelationIDConfig
        The resolved immutable middleware configuration.
    header_name : str
        The configured HTTP header used for incoming and outgoing correlation
        IDs.
    trusted_sources : frozenset[str]
        Trusted IP addresses or CIDR ranges that may provide incoming IDs.
    generator : Callable[[], str]
        Function used to generate a new correlation ID.
    validator : Callable[[str], bool] | None
        Optional validator for incoming correlation IDs.
    echo_header_in_response : bool
        Whether to echo middleware-owned correlation IDs in response headers.

    Raises
    ------
    ValueError
        If both ``config`` and other keyword arguments are provided, or if
        ``header_name`` is empty or ``trusted_sources`` contains empty strings.
    TypeError
        If unknown keyword arguments are provided, or if ``generator`` or
        ``validator`` is provided but not callable.

    Examples
    --------
    Basic usage with a Falcon ASGI application::

        import falcon.asgi
        from falcon_correlate import CorrelationIDMiddlewareASGI

        middleware = CorrelationIDMiddlewareASGI()
        app = falcon.asgi.App(middleware=[middleware])

    Custom configuration::

        middleware = CorrelationIDMiddlewareASGI(
            header_name="X-Request-ID",
            trusted_sources=["10.0.0.1", "192.168.1.1"],
            echo_header_in_response=True,
        )

    Lifecycle
    ---------
    `process_request` selects a trusted and valid incoming correlation ID or
    generates a new one, then stores it on `req.context.correlation_id` and
    `correlation_id_var`. `process_response` can echo that middleware-owned ID
    to the configured response header before cleaning up the request-scoped
    context. The detailed lifecycle logic lives in
    `_CorrelationIDMiddlewareBase`.

    """

    async def process_request(
        self,
        req: falcon.asgi.Request,
        resp: falcon.asgi.Response,
    ) -> None:
        """Process an incoming ASGI request to establish correlation ID context."""
        self._process_request(req)

    # Falcon ASGI middleware hook requires this exact signature.
    # See https://github.com/leynos/falcon-correlate/issues/38
    # pylint: disable-next=too-many-arguments,too-many-positional-arguments
    async def process_response(
        self,
        req: falcon.asgi.Request,
        resp: falcon.asgi.Response,
        resource: object,
        req_succeeded: bool,  # noqa: FBT001 - Falcon ASGI middleware interface requirement
    ) -> None:
        """Post-process an ASGI response and clean up request-scoped context."""
        self._process_response(req, resp)


__all__ = ["CorrelationIDMiddlewareASGI"]
