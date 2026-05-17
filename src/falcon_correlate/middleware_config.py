"""Configuration objects for Falcon correlation middleware.

This module defines the frozen dataclass and factory that encapsulate
``CorrelationIDMiddleware`` configuration. Its key exports are
``CorrelationIDConfig``, ``CorrelationIDConfig.from_kwargs``,
``DEFAULT_HEADER_NAME``, and ``VALID_CONFIG_KWARGS``.

``middleware.py`` imports this module to validate and freeze middleware
settings, while this module depends on ``middleware_utils.py`` for the default
correlation ID generator and validator boundary.
"""

from __future__ import annotations

import dataclasses
import ipaddress
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    class CorrelationIDConfigKwargs(typ.TypedDict, total=False):
        """Type definition for CorrelationIDConfig keyword arguments."""

        header_name: str
        trusted_sources: cabc.Iterable[str] | None
        generator: cabc.Callable[[], str] | None
        validator: cabc.Callable[[str], bool] | None
        echo_header_in_response: bool


from .middleware_utils import default_uuid7_generator

DEFAULT_HEADER_NAME = "X-Correlation-ID"

# Type alias for parsed network objects
_NetworkType = ipaddress.IPv4Network | ipaddress.IPv6Network


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
    trusted_sources: cabc.Iterable[str] = dataclasses.field(default_factory=frozenset)
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
        if isinstance(self.trusted_sources, str):
            msg = "trusted_sources must be an iterable of strings, not a string"
            raise TypeError(msg)
        object.__setattr__(self, "trusted_sources", frozenset(self.trusted_sources))
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
            if not isinstance(source, str):
                msg = "trusted_sources must contain strings"
                raise TypeError(msg)
            self._validate_source_not_empty(source)
            parsed.append(self._parse_network(source))

        # Use object.__setattr__ to set frozen field
        object.__setattr__(self, "_parsed_networks", tuple(parsed))

    @staticmethod
    def _validate_source_not_empty(source: str) -> None:
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

    @staticmethod
    def _parse_network(source: str) -> _NetworkType:
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
    # pylint: disable-next=too-many-arguments  # from_kwargs mirrors middleware constructor compatibility. FIXME: https://github.com/leynos/falcon-correlate/issues/36
    def from_kwargs(  # noqa: PLR0913 -- from_kwargs preserves the public factory API.
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
        if trusted_sources is None:
            frozen_trusted_sources = frozenset()
        elif isinstance(trusted_sources, str):
            msg = "trusted_sources must be an iterable of strings, not a str"
            raise TypeError(msg)
        else:
            frozen_trusted_sources = frozenset(trusted_sources)

        return cls(
            header_name=header_name,
            trusted_sources=frozen_trusted_sources,
            generator=generator if generator is not None else default_uuid7_generator,
            validator=validator,
            echo_header_in_response=echo_header_in_response,
        )


VALID_CONFIG_KWARGS = frozenset(
    field.name for field in dataclasses.fields(CorrelationIDConfig) if field.init
)
