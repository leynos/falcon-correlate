"""Property tests for the CorrelationIDConfig keyword factory."""

from __future__ import annotations

import string
import typing as typ

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from falcon_correlate import CorrelationIDConfig

if typ.TYPE_CHECKING:
    import collections.abc as cabc


_UNKNOWN_KEY_SUFFIXES = st.lists(
    st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=12),
    min_size=2,
    max_size=8,
    unique=True,
)


@given(unknown_suffixes=_UNKNOWN_KEY_SUFFIXES)
@settings(max_examples=50)
def test_unknown_keyword_names_are_reported_in_sorted_order(
    unknown_suffixes: list[str],
) -> None:
    """Unknown keyword names are sorted regardless of insertion order."""
    unknown_keywords = {f"unknown_{suffix}": 1 for suffix in unknown_suffixes}
    factory = typ.cast(
        "cabc.Callable[..., CorrelationIDConfig]",
        CorrelationIDConfig.from_kwargs,
    )

    with pytest.raises(TypeError) as exc_info:
        factory(**unknown_keywords)

    expected_message = (
        f"Unknown keyword arguments: {', '.join(sorted(unknown_keywords))}"
    )
    assert str(exc_info.value) == expected_message, (
        "CorrelationIDConfig.from_kwargs must report every unknown keyword "
        "in sorted order; "
        f"expected {expected_message!r}, got {str(exc_info.value)!r}"
    )
