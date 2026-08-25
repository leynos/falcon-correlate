"""Falcon WSGI correlation ID middleware and public middleware exports."""

from __future__ import annotations

import typing as typ
import uuid

from .middleware_asgi import CorrelationIDMiddlewareASGI
from .middleware_base import (
    _CORRELATION_ID_RESET_TOKEN_ATTR as _CORRELATION_ID_RESET_TOKEN_ATTR,
)
from .middleware_base import _CorrelationIDMiddlewareBase
from .middleware_config import DEFAULT_HEADER_NAME, CorrelationIDConfig
from .middleware_utils import (
    RECOMMENDED_LOG_FORMAT,
    ContextualLogFilter,
    correlation_id_var,
    default_uuid7_generator,
    default_uuid_validator,
    user_id_var,
)

__all__ = [
    "DEFAULT_HEADER_NAME",
    "RECOMMENDED_LOG_FORMAT",
    "ContextualLogFilter",
    "CorrelationIDConfig",
    "CorrelationIDMiddleware",
    "CorrelationIDMiddlewareASGI",
    "correlation_id_var",
    "default_uuid7_generator",
    "default_uuid_validator",
    "user_id_var",
    "uuid",
]

if typ.TYPE_CHECKING:
    import falcon


class CorrelationIDMiddleware(_CorrelationIDMiddlewareBase):
    """Manage correlation IDs in Falcon WSGI applications.

    The constructor follows ``_CorrelationIDMiddlewareBase.__init__`` and
    accepts either a complete configuration object or individual options.

    Parameters
    ----------
    config : CorrelationIDConfig | None, optional
        Frozen configuration object. Cannot be combined with individual
        options.
    correlation_id_context_var : contextvars.ContextVar, optional
        Context variable used for request-scoped correlation IDs. Defaults to
        ``correlation_id_var``.
    **kwargs : object
        Individual configuration options passed to
        ``CorrelationIDConfig.from_kwargs``: ``header_name``,
        ``trusted_sources``, ``generator``, ``validator``, and
        ``echo_header_in_response``.

    Raises
    ------
    ValueError
        If ``config`` is combined with individual options, or an option
        value is rejected by ``CorrelationIDConfig.from_kwargs``.
    TypeError
        If an unknown keyword option is supplied, or an option type is
        rejected by ``CorrelationIDConfig.from_kwargs``.

    Notes
    -----
    Falcon calls ``process_request`` before routing. The middleware accepts a
    validated incoming ID only from a trusted source; otherwise it generates
    one, stores it in ``req.context.correlation_id``, and sets the configured
    context variable. Falcon calls ``process_response`` after the resource
    responder; the middleware optionally echoes the ID in the configured
    response header and then resets the request-scoped context.

    """

    def process_request(
        self,
        req: falcon.Request,
        resp: falcon.Response,
    ) -> None:
        """Process an incoming request to establish correlation ID context.

        This method is called before routing the request to a resource. It
        will retrieve or generate a correlation ID and store it in the request
        context and the configured `correlation_id_context_var`. If the source
        is trusted, an incoming header is present, and the ID passes
        validation, the incoming ID is used; otherwise a new ID is generated.

        Parameters
        ----------
        req : falcon.Request
            The incoming request object.
        resp : falcon.Response
            The response object (not yet populated).

        Raises
        ------
        Exception
            If the configured correlation ID generator raises an exception.

        """  # ruff: ignore[docstring-extraneous-exception] - generator exceptions are delegated.
        self._process_request(req)

    # Falcon middleware hook requires this exact callback signature; see #38.
    # pylint: disable-next=too-many-arguments,too-many-positional-arguments
    def process_response(
        self,
        req: falcon.Request,
        resp: falcon.Response,
        resource: object,
        req_succeeded: bool,  # ruff: ignore[boolean-type-hint-positional-argument] - Falcon WSGI middleware interface requirement
    ) -> None:
        """Post-process the response and clean up request-scoped context.

        This method is called after the resource responder has been invoked. When
        response-header echoing is enabled, it writes `req.context.correlation_id`
        to the configured response header before cleanup happens. It then resets
        the configured `correlation_id_context_var` to the state that existed
        before `process_request` set it for the current request.

        Parameters
        ----------
        req : falcon.Request
            The request object.
        resp : falcon.Response
            The response object.
        resource : object
            The resource instance that handled the request, or None if an
            error occurred before routing.
        req_succeeded : bool
            True if no exceptions were raised during request processing.

        """
        self._process_response(req, resp)
