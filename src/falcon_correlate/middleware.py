"""Falcon Correlation ID middleware implementation."""

from __future__ import annotations

import contextvars
import ipaddress
import logging
import typing as typ
import uuid

from .middleware_config import (
    DEFAULT_HEADER_NAME,
    VALID_CONFIG_KWARGS,
    CorrelationIDConfig,
)
from .middleware_utils import (
    CORRELATION_ID_RESET_TOKEN_ATTR,
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
    import collections.abc as cabc

    import falcon

    from .middleware_config import CorrelationIDConfigKwargs

    class _RequestLike(typ.Protocol):
        """Small request surface shared by Falcon WSGI and ASGI."""

        context: typ.Any
        remote_addr: str

        def get_header(self, name: str) -> str | None:
            """Return a request header by name."""

    class _ResponseLike(typ.Protocol):
        """Small response surface shared by Falcon WSGI and ASGI."""

        def set_header(self, name: str, value: str) -> None:
            """Set a response header."""


logger = logging.getLogger(__name__)

_CORRELATION_ID_RESET_TOKEN_ATTR = CORRELATION_ID_RESET_TOKEN_ATTR


class _CorrelationIDMiddlewareBase:
    """Shared lifecycle logic for Falcon correlation ID middleware variants."""

    __slots__ = ("_config",)

    def __init__(
        self,
        *,
        config: CorrelationIDConfig | None = None,
        **kwargs: object,
    ) -> None:
        """Initialise the correlation ID middleware with configuration options."""
        if config is not None:
            if kwargs:
                msg = "Cannot specify both 'config' and individual parameters"
                raise ValueError(msg)
            self._config = config
        else:
            unknown_keys = set(kwargs.keys()) - VALID_CONFIG_KWARGS
            if unknown_keys:
                msg = f"Unknown keyword arguments: {', '.join(sorted(unknown_keys))}"
                raise TypeError(msg)
            # Cast to TypedDict after validating keys - runtime will verify values
            typed_kwargs = typ.cast("CorrelationIDConfigKwargs", kwargs)
            self._config = CorrelationIDConfig.from_kwargs(**typed_kwargs)

    # @CodeScene(disable:"Bumpy Road Ahead")
    @property
    def config(self) -> CorrelationIDConfig:
        """The middleware configuration."""
        return self._config

    @property
    def header_name(self) -> str:
        """The HTTP header name for correlation IDs."""
        return self._config.header_name

    @property
    def trusted_sources(self) -> frozenset[str]:
        """The set of trusted IP addresses."""
        return typ.cast("frozenset[str]", self._config.trusted_sources)

    @property
    def generator(self) -> cabc.Callable[[], str]:
        """The correlation ID generator function."""
        return self._config.generator

    @property
    def validator(self) -> cabc.Callable[[str], bool] | None:
        """The correlation ID validator function, or None if not set."""
        return self._config.validator

    @property
    def echo_header_in_response(self) -> bool:
        """Whether to echo the correlation ID in response headers."""
        return self._config.echo_header_in_response

    def _get_incoming_header_value(self, req: _RequestLike) -> str | None:
        """Return the incoming correlation ID header value, if present.

        Leading and trailing whitespace is stripped; empty or whitespace-only
        values are treated as missing.
        """
        incoming = req.get_header(self.header_name)
        if incoming is None:
            return None

        incoming = incoming.strip()
        if not incoming:
            return None

        return incoming

    def _is_trusted_source(self, remote_addr: str | None) -> bool:
        """Check if remote_addr is from a trusted source.

        Parameters
        ----------
        remote_addr : str | None
            The IP address of the request source, from req.remote_addr.

        Returns
        -------
        bool
            True if remote_addr matches any trusted source, False otherwise.

        """
        if not remote_addr:
            return False

        if not self._config._parsed_networks:
            return False

        try:
            addr = ipaddress.ip_address(remote_addr)
        except ValueError:
            # Malformed address, cannot be trusted
            return False

        return any(addr in network for network in self._config._parsed_networks)

    def _is_valid_id(self, value: str) -> bool:
        """Return whether *value* passes the configured validator, if any."""
        if self._config.validator is None:
            return True
        try:
            result = self._config.validator(value)
        except Exception:  # noqa: BLE001 - user-supplied; cannot narrow
            logger.warning(
                "Validator raised an exception for correlation ID, treating as invalid",
                exc_info=True,
            )
            return False
        return result

    def _process_request(self, req: _RequestLike) -> None:
        """Establish request-local correlation ID state."""
        incoming = self._get_incoming_header_value(req)

        if incoming is not None and self._is_trusted_source(req.remote_addr):
            if self._is_valid_id(incoming):
                correlation_id = incoming
            else:
                logger.debug(
                    "Correlation ID failed validation, generating new ID",
                )
                correlation_id = self._config.generator()
        else:
            correlation_id = self._config.generator()

        req.context.correlation_id = correlation_id
        reset_token = correlation_id_var.set(correlation_id)
        setattr(req.context, CORRELATION_ID_RESET_TOKEN_ATTR, reset_token)

    def _echo_correlation_id_header(
        self,
        req: _RequestLike,
        resp: _ResponseLike,
    ) -> None:
        """Write the active correlation ID to the configured response header.

        Does nothing when echoing is disabled or the correlation ID is absent.
        Re-raises any exception from ``resp.set_header`` so that the caller's
        ``finally`` block still runs.
        """
        if not self._config.echo_header_in_response:
            logger.debug("Correlation ID response header echo disabled")
            return

        correlation_id = getattr(req.context, "correlation_id", None)
        if correlation_id is None:
            logger.debug("Correlation ID response header echo skipped; ID absent")
            return

        try:
            resp.set_header(self._config.header_name, correlation_id)
        except Exception:
            logger.warning(
                "Failed to echo correlation ID response header",
                exc_info=True,
            )
            raise
        logger.debug("Correlation ID response header echoed")

    def _reset_correlation_id_context(  # noqa: PLR6301 - helper must remain an instance method.
        self,
        req: _RequestLike,
        reset_token: object,
    ) -> None:
        """Clear request reset token state and restore ContextVar state."""
        setattr(req.context, CORRELATION_ID_RESET_TOKEN_ATTR, None)

        if not isinstance(reset_token, contextvars.Token):
            return

        if reset_token.var is not correlation_id_var:
            logger.debug("Ignoring mismatched correlation ID reset token")
            return

        try:
            correlation_id_var.reset(reset_token)
        except ValueError:
            logger.debug(
                "Ignoring invalid correlation ID reset token",
                exc_info=True,
            )

    def _process_response(self, req: _RequestLike, resp: _ResponseLike) -> None:
        """Echo the response header if configured, then clear request state."""
        reset_token = getattr(req.context, CORRELATION_ID_RESET_TOKEN_ATTR, None)
        try:
            if (
                isinstance(reset_token, contextvars.Token)
                and reset_token.var is correlation_id_var
            ):
                self._echo_correlation_id_header(req, resp)
            else:
                logger.debug(
                    "Correlation ID response header echo skipped; "
                    "middleware token absent",
                )
        finally:
            self._reset_correlation_id_context(req, reset_token)


class CorrelationIDMiddleware(_CorrelationIDMiddlewareBase):
    """Middleware for managing correlation IDs in Falcon WSGI applications.

    This middleware handles the lifecycle of correlation IDs, extracting
    them from incoming request headers or generating new ones, making
    them available throughout the request lifecycle, and optionally
    echoing them in response headers.

    Parameters
    ----------
    config : CorrelationIDConfig | None
        A pre-built configuration object. If provided, no other keyword
        arguments may be specified. Defaults to ``None``.
    **kwargs
        Individual configuration parameters. Valid keys are: ``header_name``,
        ``trusted_sources``, ``generator``, ``validator``, and
        ``echo_header_in_response``. See :meth:`CorrelationIDConfig.from_kwargs`
        for parameter details.

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
    Basic usage with a Falcon WSGI application::

        import falcon
        from falcon_correlate import CorrelationIDMiddleware

        middleware = CorrelationIDMiddleware()
        app = falcon.App(middleware=[middleware])

    Custom configuration::

        middleware = CorrelationIDMiddleware(
            header_name="X-Request-ID",
            trusted_sources=["10.0.0.1", "192.168.1.1"],
            echo_header_in_response=True,
        )

    Using a configuration object::

        from falcon_correlate import CorrelationIDConfig

        config = CorrelationIDConfig(
            header_name="X-Request-ID",
            trusted_sources=frozenset(["10.0.0.1"]),
        )
        middleware = CorrelationIDMiddleware(config=config)

    """

    def process_request(self, req: falcon.Request, resp: falcon.Response) -> None:
        """Process an incoming request to establish correlation ID context.

        This method is called before routing the request to a resource.
        It will retrieve or generate a correlation ID and store it in
        the request context and `correlation_id_var`. If the source is trusted,
        an incoming header is present, and the ID passes validation, the
        incoming ID is used; otherwise a new ID is generated.

        Parameters
        ----------
        req : falcon.Request
            The incoming request object.
        resp : falcon.Response
            The response object (not yet populated).

        Raises
        ------
        Exception
            Any exception raised by the configured generator will propagate
            to the caller. Custom generators are responsible for their own
            error handling; the middleware does not catch generator exceptions.

        """
        self._process_request(req)

    # Falcon middleware hook requires this exact signature (request, response,
    # resource, req_succeeded); disabling argument-count warnings for framework
    # callback. FIXME: https://github.com/leynos/falcon-correlate/issues/38
    # pylint: disable-next=too-many-arguments,too-many-positional-arguments
    def process_response(
        self,
        req: falcon.Request,
        resp: falcon.Response,
        resource: object,
        req_succeeded: bool,  # noqa: FBT001 - Falcon WSGI middleware interface requirement
    ) -> None:
        """Post-process the response and clean up request-scoped context.

        This method is called after the resource responder has been invoked.
        When response-header echoing is enabled, it writes
        `req.context.correlation_id` to the configured response header before
        cleanup happens. It then resets `correlation_id_var` to the state that
        existed before `process_request` set it for the current request.

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


from .middleware_asgi import CorrelationIDMiddlewareASGI  # noqa: E402
