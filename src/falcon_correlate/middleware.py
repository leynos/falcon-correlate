"""Falcon Correlation ID middleware implementation."""

from __future__ import annotations

import dataclasses
import ipaddress
import logging
import typing as typ
import uuid

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    import falcon

# Type alias for parsed network objects
_NetworkType = ipaddress.IPv4Network | ipaddress.IPv6Network

DEFAULT_HEADER_NAME = "X-Correlation-ID"

logger = logging.getLogger(__name__)


def default_uuid7_generator() -> str:
    """Generate a UUIDv7 correlation ID.

    Uses the standard library ``uuid.uuid7()`` when available and falls back
    to ``uuid_utils.uuid7()`` when the runtime lacks ``uuid.uuid7()``.

    Returns
    -------
    str
        A UUIDv7 hex string representation.

    """
    uuid7 = getattr(uuid, "uuid7", None)
    if uuid7 is not None:
        return uuid7().hex

    import uuid_utils

    return uuid_utils.uuid7().hex


# Maximum length for a valid UUID string (hyphenated format: 8-4-4-4-12)
_MAX_UUID_LENGTH = 36
# Minimum length for a valid UUID string (hex-only format: 32 characters)
_MIN_UUID_LENGTH = 32
# Expected hyphen positions in 8-4-4-4-12 format (indices 8, 13, 18, 23)
_HYPHEN_POSITIONS = frozenset({8, 13, 18, 23})
# Valid UUID versions per RFC 4122 and RFC 9562
_VALID_UUID_VERSIONS = frozenset({1, 2, 3, 4, 5, 6, 7, 8})


def _has_valid_hyphen_placement(value: str) -> bool:
    """Check that hyphens appear exactly at positions 8, 13, 18, 23 and nowhere else."""
    for i, char in enumerate(value):
        if char == "-":
            if i not in _HYPHEN_POSITIONS:
                return False
        elif i in _HYPHEN_POSITIONS:
            # Expected a hyphen but found a different character
            return False
    return True


def default_uuid_validator(value: str) -> bool:
    """Validate that a string is a valid UUID (versions 1-8).

    Accepts both hyphenated (8-4-4-4-12) and hex-only (32-character) UUID
    formats. Case-insensitive. Rejects UUIDs with non-standard version nibbles.
    Enforces strict hyphen placement at positions 8, 13, 18, and 23 for
    36-character inputs.

    Parameters
    ----------
    value : str
        The string to validate.

    Returns
    -------
    bool
        ``True`` if the value is a valid UUID (version 1-8), ``False`` otherwise.

    Examples
    --------
    >>> default_uuid_validator("550e8400-e29b-41d4-a716-446655440000")
    True
    >>> default_uuid_validator("550e8400e29b41d4a716446655440000")
    True
    >>> default_uuid_validator("not-a-uuid")
    False

    """
    # Early exit for empty strings
    if not value:
        return False

    # Early exit for out-of-range length strings
    length = len(value)
    if length > _MAX_UUID_LENGTH or length < _MIN_UUID_LENGTH:
        return False

    # Reject strings in the 33-35 character "gap" (neither hex-only nor valid
    # hyphenated format)
    if _MIN_UUID_LENGTH < length < _MAX_UUID_LENGTH:
        return False

    # For 36-character strings, enforce strict 8-4-4-4-12 hyphen placement
    if length == _MAX_UUID_LENGTH and not _has_valid_hyphen_placement(value):
        return False

    try:
        parsed = uuid.UUID(value)
    except ValueError:
        return False
    else:
        # Enforce valid UUID version (1-8)
        return parsed.version in _VALID_UUID_VERSIONS


@dataclasses.dataclass(frozen=True)
class CorrelationIDConfig:
    """Configuration for CorrelationIDMiddleware.

    This immutable configuration object encapsulates all settings for the
    correlation ID middleware, providing validation and sensible defaults.

    Parameters
    ----------
    header_name : str
        The HTTP header name for correlation IDs. Defaults to ``X-Correlation-ID``.
    trusted_sources : frozenset[str]
        IP addresses considered trusted. Defaults to empty frozenset.
    generator : Callable[[], str]
        Function to generate new correlation IDs. Defaults to
        ``default_uuid7_generator``.
    validator : Callable[[str], bool] | None
        Optional function to validate incoming IDs. Defaults to ``None``.
    echo_header_in_response : bool
        Whether to echo the ID in response headers. Defaults to ``True``.

    Raises
    ------
    ValueError
        If ``header_name`` is empty or ``trusted_sources`` contains empty strings.
    TypeError
        If ``generator`` or ``validator`` is not callable.

    """

    header_name: str = DEFAULT_HEADER_NAME
    trusted_sources: frozenset[str] = dataclasses.field(default_factory=frozenset)
    generator: cabc.Callable[[], str] = default_uuid7_generator
    validator: cabc.Callable[[str], bool] | None = None
    echo_header_in_response: bool = True
    _parsed_networks: tuple[_NetworkType, ...] = dataclasses.field(
        default=(),
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        """Validate configuration after initialisation."""
        self._validate_header_name()
        self._validate_trusted_sources()
        self._validate_generator()
        self._validate_validator()

    def _validate_header_name(self) -> None:
        """Validate that header_name is not empty."""
        if not self.header_name or not self.header_name.strip():
            msg = "header_name must not be empty"
            raise ValueError(msg)

    def _validate_trusted_sources(self) -> None:
        """Validate trusted_sources and parse IP/CIDR notations.

        Each entry in trusted_sources must be a valid IP address or CIDR
        notation. Parsed networks are stored in _parsed_networks for efficient
        matching at request time.
        """
        parsed: list[_NetworkType] = []
        for source in self.trusted_sources:
            self._validate_source_not_empty(source)
            parsed.append(self._parse_network(source))

        # Use object.__setattr__ to set frozen field
        object.__setattr__(self, "_parsed_networks", tuple(parsed))

    def _validate_source_not_empty(self, source: str) -> None:
        """Validate that a trusted source string is not empty or whitespace.

        Parameters
        ----------
        source : str
            The trusted source string to validate.

        Raises
        ------
        ValueError
            If ``source`` is empty or contains only whitespace characters.

        """
        if not source or not source.strip():
            msg = "trusted_sources must not contain empty strings"
            raise ValueError(msg)

    def _parse_network(self, source: str) -> _NetworkType:
        """Parse an IP address or CIDR notation into a network object.

        Parameters
        ----------
        source : str
            The IP address or CIDR notation string to parse.

        Returns
        -------
        IPv4Network | IPv6Network
            The parsed network object.

        Raises
        ------
        ValueError
            If ``source`` has host bits set (for CIDR notation) or is not a
            valid IP address or CIDR notation.

        """
        try:
            network = ipaddress.ip_network(source, strict=False)
        except ValueError as err:
            msg = f"Invalid IP address or CIDR notation: '{source}'"
            raise ValueError(msg) from err

        # If CIDR notation was provided, check for host bits explicitly
        if "/" in source:
            addr_str, _, _ = source.partition("/")
            try:
                ip = ipaddress.ip_address(addr_str)
            except ValueError as err:
                msg = f"Invalid IP address or CIDR notation: '{source}'"
                raise ValueError(msg) from err
            if ip != network.network_address:
                msg = f"Invalid CIDR notation '{source}': has host bits set"
                raise ValueError(msg)

        return network

    def _validate_generator(self) -> None:
        """Validate that generator is callable."""
        if not callable(self.generator):
            msg = "generator must be callable"
            raise TypeError(msg)

    def _validate_validator(self) -> None:
        """Validate that validator is callable if provided."""
        if self.validator is not None and not callable(self.validator):
            msg = "validator must be callable"
            raise TypeError(msg)

    # @CodeScene(disable:"Excess Number of Function Arguments")
    @classmethod
    def from_kwargs(  # noqa: PLR0913
        cls,
        *,
        header_name: str = DEFAULT_HEADER_NAME,
        trusted_sources: cabc.Iterable[str] | None = None,
        generator: cabc.Callable[[], str] | None = None,
        validator: cabc.Callable[[str], bool] | None = None,
        echo_header_in_response: bool = True,
    ) -> CorrelationIDConfig:
        """Create a configuration from individual keyword arguments.

        This factory method handles conversion of ``trusted_sources`` to a
        frozenset and applies the default generator if none is provided.

        Parameters
        ----------
        header_name : str
            The HTTP header name. Defaults to ``X-Correlation-ID``.
        trusted_sources : Iterable[str] | None
            IP addresses to trust. Converted to frozenset.
        generator : Callable[[], str] | None
            ID generator function. Defaults to ``default_uuid7_generator``.
        validator : Callable[[str], bool] | None
            ID validation function.
        echo_header_in_response : bool
            Whether to echo ID in response.

        Returns
        -------
        CorrelationIDConfig
            A new configuration instance.

        """
        return cls(
            header_name=header_name,
            trusted_sources=(
                frozenset(trusted_sources) if trusted_sources else frozenset()
            ),
            generator=generator if generator is not None else default_uuid7_generator,
            validator=validator,
            echo_header_in_response=echo_header_in_response,
        )


# Derive valid kwargs from dataclass fields to ensure synchronisation
_VALID_CONFIG_KWARGS = frozenset(
    field.name for field in dataclasses.fields(CorrelationIDConfig)
)


class CorrelationIDMiddleware:
    """Middleware for managing correlation IDs in Falcon applications.

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
            unknown_keys = set(kwargs.keys()) - _VALID_CONFIG_KWARGS
            if unknown_keys:
                msg = f"Unknown keyword arguments: {', '.join(sorted(unknown_keys))}"
                raise TypeError(msg)
            self._config = CorrelationIDConfig.from_kwargs(**kwargs)  # type: ignore[arg-type]

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
        return self._config.trusted_sources

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

    def _get_incoming_header_value(self, req: falcon.Request) -> str | None:
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
        """Check incoming ID against the configured validator.

        Returns ``True`` if no validator is configured or if the validator
        accepts the value.

        Parameters
        ----------
        value : str
            The incoming correlation ID string to validate.

        Returns
        -------
        bool
            ``True`` if the ID is valid or no validator is set,
            ``False`` if the validator rejects the ID.

        """
        if self._config.validator is None:
            return True
        return self._config.validator(value)

    def process_request(self, req: falcon.Request, resp: falcon.Response) -> None:
        """Process an incoming request to establish correlation ID context.

        This method is called before routing the request to a resource.
        It will retrieve or generate a correlation ID and store it in
        the request context. If the source is trusted, an incoming header
        is present, and the ID passes validation, the incoming ID is used;
        otherwise a new ID is generated.

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
        incoming = self._get_incoming_header_value(req)

        if incoming is not None and self._is_trusted_source(req.remote_addr):
            if self._is_valid_id(incoming):
                req.context.correlation_id = incoming
            else:
                logger.debug(
                    "Correlation ID failed validation, generating new ID: %s",
                    incoming,
                )
                req.context.correlation_id = self._config.generator()
        else:
            req.context.correlation_id = self._config.generator()

    def process_response(
        self,
        req: falcon.Request,
        resp: falcon.Response,
        resource: object,
        req_succeeded: bool,  # noqa: FBT001, TD001, TD002, TD003  # FIXME: Falcon WSGI middleware interface requirement
    ) -> None:
        """Post-process the response to add correlation ID header and cleanup.

        This method is called after the resource responder has been invoked.
        It will add the correlation ID to response headers and clean up
        any request-scoped context.

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
