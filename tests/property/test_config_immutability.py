"""Property tests for correlation ID configuration immutability."""

from __future__ import annotations

import collections.abc as cabc
import itertools
import typing as typ

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from falcon_correlate import CorrelationIDConfig

type _TrustedSourcesInput = (
    list[str]
    | tuple[str, ...]
    | set[str]
    | frozenset[str]
    | cabc.Generator[str, None, None]
)


@st.composite
def trusted_sources_inputs(
    draw: st.DrawFn,
) -> _TrustedSourcesInput:
    """Generate supported trusted-source iterable shapes."""
    sources = draw(
        st.lists(
            st.ip_addresses().map(str),
            max_size=12,
        )
    )
    iterable_type = draw(st.sampled_from(("list", "tuple", "set", "frozenset", "gen")))

    match iterable_type:
        case "list":
            return sources
        case "tuple":
            return tuple(sources)
        case "set":
            return set(sources)
        case "frozenset":
            return frozenset(sources)
        case "gen":
            return (source for source in sources)

    typ.assert_never(iterable_type)


@given(trusted_sources=trusted_sources_inputs())
@settings(max_examples=50)
def test_trusted_sources_are_always_frozen(
    trusted_sources: _TrustedSourcesInput,
) -> None:
    """All accepted trusted-source iterables are stored as a frozenset."""
    config_input: cabc.Iterable[str] = trusted_sources
    expected_input: cabc.Iterable[str] = trusted_sources
    if isinstance(trusted_sources, cabc.Iterator):
        iterator_sources = typ.cast("cabc.Iterator[str]", trusted_sources)
        expected_input, config_input = itertools.tee(iterator_sources)

    expected_sources = frozenset(expected_input)
    config = CorrelationIDConfig(trusted_sources=config_input)

    assert type(config.trusted_sources) is frozenset, (
        "CorrelationIDConfig.trusted_sources must be stored as a frozenset; "
        f"got {type(config.trusted_sources).__name__}"
    )
    assert config.trusted_sources == expected_sources, (
        "CorrelationIDConfig.trusted_sources must preserve input contents; "
        f"expected {expected_sources!r}, got {config.trusted_sources!r}"
    )


@given(trusted_sources=st.text())
@settings(max_examples=50)
def test_trusted_sources_reject_plain_strings(trusted_sources: str) -> None:
    """A bare string is not a trusted-source iterable."""
    with pytest.raises(TypeError, match="iterable of strings"):
        CorrelationIDConfig(trusted_sources=trusted_sources)
