"""Shared request and response lifecycle for Falcon middleware adapters.

``_CorrelationIDMiddlewareBase`` resolves configuration, accepts an incoming
correlation ID only from a trusted source and after validation, and stores the
ID in ``req.context`` and the configured ``ContextVar``. Its response hook
optionally echoes the ID in the configured header and always resets the
request-local context.

``CorrelationIDMiddleware`` in ``middleware.py`` and
``CorrelationIDMiddlewareASGI`` in ``middleware_asgi.py`` delegate their Falcon
hooks to ``_process_request`` and ``_process_response``. Diagnostics retain the
``falcon_correlate.middleware`` logger namespace so existing tests and
application logging configuration continue to match them.

Examples
--------
Adapter hooks use the shared lifecycle like this::

    self._process_request(req)
    self._process_response(req, resp)
"""

from __future__ import annotations

import contextvars
import ipaddress
import logging
import typing as typ

from .middleware_config import CorrelationIDConfig
from .middleware_metrics import (
    CorrelationIDSelectionEvent,
    IncomingIDOutcome,
    SourceTrust,
)
from .middleware_utils import (
    CORRELATION_ID_RESET_TOKEN_ATTR as _CORRELATION_ID_RESET_TOKEN_ATTR,
)
from .middleware_utils import correlation_id_var

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from ._protocols import _RequestLike, _ResponseLike
    from .middleware_config import CorrelationIDConfigKwargs

# Preserve the established logger namespace after extracting the shared base.
logger = logging.getLogger("falcon_correlate.middleware")


def _validation_outcome(
    result: object,
    *,
    validator_raised: bool,
) -> IncomingIDOutcome:
    """Map one validator result to its selection outcome."""
    if validator_raised:
        return IncomingIDOutcome.rejected_validator_error
    return IncomingIDOutcome.accepted if result else IncomingIDOutcome.rejected_invalid


class _CorrelationIDMiddlewareBase:
    """Shared lifecycle logic for Falcon correlation ID middleware variants."""

    __slots__ = ("_config", "_correlation_id_var")

    def __init__(
        self,
        *,
        config: CorrelationIDConfig | None = None,
        correlation_id_context_var: contextvars.ContextVar[
            typ.Any
        ] = correlation_id_var,
        **kwargs: object,
    ) -> None:
        """Initialize the correlation ID middleware with configuration options.

        Raises
        ------
        ValueError
            If a configuration object and individual options are both supplied.
        TypeError
            If an unknown individual option is supplied.

        """  # ruff: ignore[docstring-extraneous-exception] - from_kwargs raises it.
        self._correlation_id_var = correlation_id_context_var
        if config is not None and kwargs:
            msg = "Cannot specify both 'config' and individual parameters"
            raise ValueError(msg)
        if config is not None:
            self._config = config
            return

        # The factory owns runtime key validation; the cast carries its typing.
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

    def _log_context(self, correlation_id: object) -> dict[str, object]:
        """Build structured log context for middleware diagnostics."""
        return {
            "correlation_id": correlation_id,
            "header_name": self._config.header_name,
        }

    def _get_incoming_header_value(self, req: _RequestLike) -> str | None:
        """Return the stripped incoming correlation ID header value."""
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

    def _validate_id(self, value: str) -> tuple[object, bool]:
        """Return the validator result and whether it raised an exception."""
        if self._config.validator is None:
            return True, False
        try:
            return self._config.validator(value), False
        except Exception:
            logger.warning(
                "Validator raised an exception for correlation ID, treating as invalid",
                extra=self._log_context(value),
                exc_info=True,
            )
            return False, True

    def _record_selection(self, event: CorrelationIDSelectionEvent) -> None:
        """Send a selection event while keeping recorder failures isolated."""
        recorder = self._config.metrics_recorder
        if recorder is None:
            return
        try:
            recorder(event)
        except Exception:
            logger.warning(
                "Metrics recorder raised an exception, ignoring",
                exc_info=True,
                extra={"header_name": self._config.header_name},
            )

    def _generate_id(self) -> str:
        """Generate a new ID, logging and propagating generator failures."""
        try:
            return self._config.generator()
        except Exception:
            logger.error(
                "Correlation ID generator raised an exception",
                exc_info=True,
                extra={"header_name": self._config.header_name},
            )
            raise

    def _classify_incoming(
        self,
        req: _RequestLike,
        incoming: str | None,
    ) -> tuple[IncomingIDOutcome, SourceTrust]:
        """Classify the incoming ID and preserve existing validation logs."""
        if incoming is None:
            return IncomingIDOutcome.missing, SourceTrust.not_evaluated
        if not self._is_trusted_source(req.remote_addr):
            return IncomingIDOutcome.untrusted, SourceTrust.untrusted

        validation_result, validator_raised = self._validate_id(incoming)
        outcome = _validation_outcome(
            validation_result,
            validator_raised=validator_raised,
        )
        return outcome, SourceTrust.trusted

    def _process_request(self, req: _RequestLike) -> None:
        """Establish request-local correlation ID state."""
        incoming = self._get_incoming_header_value(req)
        outcome, trust = self._classify_incoming(req, incoming)
        if outcome in {
            IncomingIDOutcome.rejected_invalid,
            IncomingIDOutcome.rejected_validator_error,
        }:
            logger.debug(
                "Correlation ID failed validation, generating new ID",
                extra=self._log_context(incoming),
            )

        self._record_selection(
            CorrelationIDSelectionEvent(
                outcome=outcome,
                trust=trust,
                header_name=self._config.header_name,
            ),
        )
        correlation_id = (
            self._generate_id()
            if outcome is not IncomingIDOutcome.accepted
            else typ.cast("str", incoming)
        )

        req.context.correlation_id = correlation_id
        reset_token = self._correlation_id_var.set(correlation_id)
        setattr(req.context, _CORRELATION_ID_RESET_TOKEN_ATTR, reset_token)

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
            logger.debug(
                "Correlation ID response header echo disabled",
                extra=self._log_context(getattr(req.context, "correlation_id", None)),
            )
            return

        correlation_id = getattr(req.context, "correlation_id", None)
        if correlation_id is None:
            logger.debug(
                "Correlation ID response header echo skipped; ID absent",
                extra=self._log_context(None),
            )
            return

        try:
            resp.set_header(self._config.header_name, correlation_id)
        except Exception:
            logger.warning(
                "Failed to echo correlation ID response header",
                extra=self._log_context(correlation_id),
                exc_info=True,
            )
            raise
        logger.debug(
            "Correlation ID response header echoed",
            extra=self._log_context(correlation_id),
        )

    def _reset_correlation_id_context(
        self,
        req: _RequestLike,
        reset_token: object,
    ) -> None:
        """Clear request reset token state and restore ContextVar state."""
        setattr(req.context, _CORRELATION_ID_RESET_TOKEN_ATTR, None)

        if not isinstance(reset_token, contextvars.Token):
            return

        if reset_token.var is not self._correlation_id_var:
            logger.debug(
                "Ignoring mismatched correlation ID reset token",
                extra=self._log_context(getattr(req.context, "correlation_id", None)),
            )
            return

        # Token is invariant, so narrow the isinstance result to the stored
        # var's parameter; the identity check above guarantees the match.
        token = typ.cast("contextvars.Token[typ.Any]", reset_token)
        try:
            self._correlation_id_var.reset(token)
        except ValueError:
            logger.debug(
                "Ignoring invalid correlation ID reset token",
                extra=self._log_context(getattr(req.context, "correlation_id", None)),
                exc_info=True,
            )

    def _process_response(self, req: _RequestLike, resp: _ResponseLike) -> None:
        """Echo the response header if configured, then clear request state."""
        reset_token = getattr(req.context, _CORRELATION_ID_RESET_TOKEN_ATTR, None)
        try:
            if (
                isinstance(reset_token, contextvars.Token)
                and reset_token.var is self._correlation_id_var
            ):
                self._echo_correlation_id_header(req, resp)
            else:
                logger.debug(
                    "Correlation ID response header echo skipped; "
                    "middleware token absent",
                    extra=self._log_context(
                        getattr(req.context, "correlation_id", None)
                    ),
                )
        finally:
            self._reset_correlation_id_context(req, reset_token)
