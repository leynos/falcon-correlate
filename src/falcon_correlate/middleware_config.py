"""Configuration objects for Falcon correlation middleware.

This module defines the frozen dataclass and factory that encapsulate
``CorrelationIDMiddleware`` configuration. Its key exports are
``CorrelationIDConfig``, ``CorrelationIDConfig.from_kwargs``,
``DEFAULT_HEADER_NAME``, and ``VALID_CONFIG_KWARGS``.

``middleware.py`` imports this module to validate and freeze middleware
settings, while this module depends on ``middleware_utils.py`` for
``default_uuid7_generator`` and ``default_uuid_validator``.
"""

from __future__ import annotations

import dataclasses
import ipaddress
import logging
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

logger = logging.getLogger(__name__)

DEFAULT_HEADER_NAME = "X-Correlation-ID"

# Type alias for parsed network objects
_NetworkType = ipaddress.IPv4Network | ipaddress.IPv6Network


def _format_rejected_value(value: object, *, type_only: bool = False) -> str:
    """Render string values safely and other values by type name."""
    if type_only:
        return type(value).__qualname__
    match value:
        case str() as string_value:
            return repr(string_value)
        case _:
            return type(value).__qualname__


def _log_validation_failure(
    field: str,
    value: object,
    *,
    type_only: bool = False,
) -> None:
    """Log one safe diagnostic for a rejected configuration value."""
    rejected_value = _format_rejected_value(value, type_only=type_only)
    logger.debug(
        "Correlation ID configuration validation failed for %s: rejected value %s",
        field,
        rejected_value,
        extra={
            "config_field": field,
            "config_rejected_value": rejected_value,
        },
    )


@dataclasses.dataclass(frozen=True, slots=True)
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
        """Validate configuration after initialization.

        Raises
        ------
        ValueError
            If ``header_name`` is empty or whitespace-only, or any trusted
            source is empty, whitespace-only, or malformed.
        TypeError
            If ``trusted_sources`` is a string or contains non-string values, or
            if ``generator`` or ``validator`` is not callable.

        """  # ruff: ignore[docstring-extraneous-exception] - validators raise indirectly.
        if isinstance(self.trusted_sources, str):
            _log_validation_failure("trusted_sources", self.trusted_sources)
            msg = "trusted_sources must be an iterable of strings, not a string"
            raise TypeError(msg)
        object.__setattr__(self, "trusted_sources", frozenset(self.trusted_sources))
        self._validate_header_name()
        self._validate_trusted_sources()
        self._validate_generator()
        self._validate_validator()

    def _validate_header_name(self) -> None:
        """Validate that header_name is not empty or whitespace."""
        if not self.header_name or not self.header_name.strip():
            _log_validation_failure("header_name", self.header_name)
            msg = "header_name must not be empty"
            raise ValueError(msg)

    def _validate_trusted_sources(self) -> None:
        """Validate trusted_sources and parse them into network objects."""
        parsed: list[_NetworkType] = []
        for source in self.trusted_sources:
            if not isinstance(source, str):
                _log_validation_failure("trusted_sources", source)
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
            _log_validation_failure("trusted_sources", source)
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
            If ``source`` has host bits set, or is not a valid IP address or
            CIDR notation.

        """
        try:
            return ipaddress.ip_network(source, strict=True)
        except ValueError as err:
            if "/" in source and "has host bits set" in str(err):
                msg = f"Invalid CIDR notation '{source}': has host bits set"
            else:
                msg = f"Invalid IP address or CIDR notation: '{source}'"
            _log_validation_failure("trusted_sources", source)
            raise ValueError(msg) from err

    def _validate_generator(self) -> None:
        """Validate that generator is callable."""
        if not callable(self.generator):
            _log_validation_failure("generator", self.generator, type_only=True)
            msg = "generator must be callable"
            raise TypeError(msg)

    def _validate_validator(self) -> None:
        """Validate that validator is callable when provided."""
        if self.validator is not None and not callable(self.validator):
            _log_validation_failure("validator", self.validator, type_only=True)
            msg = "validator must be callable"
            raise TypeError(msg)

    @staticmethod
    def _normalize_trusted_sources(
        trusted_sources: cabc.Iterable[str] | None,
    ) -> frozenset[str]:
        """Normalize optional trusted sources into an immutable set.

        Parameters
        ----------
        trusted_sources : Iterable[str] | None
            Trusted-source strings supplied to the public factory.

        Returns
        -------
        frozenset[str]
            The frozen trusted-source collection.

        Raises
        ------
        TypeError
            If ``trusted_sources`` is a bare string rather than an iterable of
            source strings.

        """
        if trusted_sources is None:
            return frozenset()
        if isinstance(trusted_sources, str):
            _log_validation_failure("trusted_sources", trusted_sources)
            msg = "trusted_sources must be an iterable of strings, not a str"
            raise TypeError(msg)
        return frozenset(trusted_sources)

    @staticmethod
    def _resolve_generator(
        generator: cabc.Callable[[], str] | None,
    ) -> cabc.Callable[[], str]:
        """Return the configured generator or the default UUIDv7 generator."""
        if generator is None:
            return default_uuid7_generator
        return generator

    @classmethod
    def from_kwargs(
        cls,
        **kwargs: typ.Unpack[CorrelationIDConfigKwargs],
    ) -> CorrelationIDConfig:
        """Create a validated configuration from middleware keyword arguments.

        Parameters
        ----------
        kwargs : Unpack[CorrelationIDConfigKwargs]
            Accepted keys are ``header_name`` (default
            ``DEFAULT_HEADER_NAME``), ``trusted_sources`` (default ``None``,
            normalized to an empty ``frozenset``), ``generator`` (default
            ``None``, resolved to ``default_uuid7_generator``), ``validator``
            (default ``None``, passed through unchanged), and
            ``echo_header_in_response`` (default ``True``).

        Returns
        -------
        CorrelationIDConfig
            A new configuration instance.

        Raises
        ------
        TypeError
            If an unknown keyword is supplied; ``trusted_sources`` is a string
            or contains a non-string member; or ``generator`` or ``validator``
            is not callable.
        ValueError
            If ``header_name`` is empty or whitespace-only, or a trusted
            source is empty, whitespace-only, or malformed.

        Examples
        --------
        >>> config = CorrelationIDConfig.from_kwargs()
        >>> config.header_name
        'X-Correlation-ID'
        >>> config.trusted_sources
        frozenset()

        """  # ruff: ignore[docstring-extraneous-exception] - cls validates inputs.
        unknown = set(kwargs) - VALID_CONFIG_KWARGS
        if unknown:
            msg = f"Unknown keyword arguments: {', '.join(sorted(unknown))}"
            raise TypeError(msg)

        return cls(
            header_name=kwargs.get("header_name", DEFAULT_HEADER_NAME),
            trusted_sources=cls._normalize_trusted_sources(
                kwargs.get("trusted_sources")
            ),
            generator=cls._resolve_generator(kwargs.get("generator")),
            validator=kwargs.get("validator"),
            echo_header_in_response=kwargs.get("echo_header_in_response", True),
        )


VALID_CONFIG_KWARGS = frozenset(
    field.name for field in dataclasses.fields(CorrelationIDConfig) if field.init
)
