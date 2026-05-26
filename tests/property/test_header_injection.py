"""Property tests for httpx correlation ID header injection.

These properties exercise the relationship between ``correlation_id_var``,
``request_with_correlation_id``, and ``httpx.request`` without making network
calls. Generated header dictionaries cover caller-supplied headers while the
shared ``isolated_context`` fixture prevents ``ContextVar`` state from leaking
between Hypothesis examples.

The core invariants are that a set context injects ``X-Correlation-ID`` when
the caller did not provide one, an unset context does not inject anything, and
an explicit caller-supplied correlation header is preserved.
"""

from __future__ import annotations

import dataclasses
import string
import typing as typ

import httpx
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from falcon_correlate import correlation_id_var, request_with_correlation_id
from falcon_correlate.middleware import DEFAULT_HEADER_NAME

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    import pytest


_HEADER_NAME_ALPHABET = string.ascii_letters + string.digits + "-_"
_HEADER_VALUE_ALPHABET = string.ascii_letters + string.digits + string.punctuation + " "

_correlation_ids = st.text(
    alphabet=_HEADER_VALUE_ALPHABET,
    min_size=1,
    max_size=64,
)
_header_dicts = st.dictionaries(
    st.text(alphabet=_HEADER_NAME_ALPHABET, min_size=1, max_size=32),
    st.text(alphabet=_HEADER_VALUE_ALPHABET, max_size=64),
    max_size=12,
)
_preservation_cases = st.tuples(
    _correlation_ids,
    _correlation_ids,
    _header_dicts,
).filter(lambda case: case[0] != case[1])


@given(
    correlation_id=_correlation_ids,
    headers=_header_dicts,
)
@settings(
    max_examples=50,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_injects_context_correlation_id_when_header_is_absent(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    monkeypatch: pytest.MonkeyPatch,
    correlation_id: str,
    headers: dict[str, str],
) -> None:
    """A set context always forwards a correlation ID header."""
    headers = _without_correlation_id_header(headers)
    captured = _capture_httpx_request(monkeypatch)

    def run_request() -> None:
        correlation_id_var.set(correlation_id)
        request_with_correlation_id("GET", "https://example.test/", headers=headers)

    isolated_context(run_request)

    assert captured.headers[DEFAULT_HEADER_NAME] == correlation_id, (
        "test_injects_context_correlation_id_when_header_is_absent expected "
        "request_with_correlation_id to forward correlation_id_var through "
        f"{DEFAULT_HEADER_NAME} after _without_correlation_id_header and "
        "_capture_httpx_request"
    )


@given(headers=_header_dicts)
@settings(
    max_examples=50,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_does_not_inject_header_when_context_is_unset(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    monkeypatch: pytest.MonkeyPatch,
    headers: dict[str, str],
) -> None:
    """An unset context never adds a correlation ID header."""
    headers = _without_correlation_id_header(headers)
    captured = _capture_httpx_request(monkeypatch)
    executed = False

    def run_request() -> None:
        nonlocal executed
        request_with_correlation_id(
            "GET",
            "https://example.test/",
            headers=headers,
        )
        executed = True

    isolated_context(run_request)

    assert executed is True
    assert DEFAULT_HEADER_NAME not in captured.headers, (
        "test_does_not_inject_header_when_context_is_unset expected "
        "_capture_httpx_request to observe no correlation ID header when "
        "isolated_context leaves correlation_id_var unset"
    )


@given(
    case=_preservation_cases,
)
@settings(
    max_examples=50,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_preserves_caller_supplied_correlation_id_header(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    monkeypatch: pytest.MonkeyPatch,
    case: tuple[str, str, dict[str, str]],
) -> None:
    """Caller-supplied correlation ID headers are never overwritten."""
    correlation_id, caller_correlation_id, headers = case
    headers = _without_correlation_id_header(headers)
    headers[DEFAULT_HEADER_NAME] = caller_correlation_id
    captured = _capture_httpx_request(monkeypatch)

    def run_request() -> None:
        correlation_id_var.set(correlation_id)
        request_with_correlation_id("GET", "https://example.test/", headers=headers)

    isolated_context(run_request)

    assert captured.headers[DEFAULT_HEADER_NAME] == caller_correlation_id, (
        "test_preserves_caller_supplied_correlation_id_header expected "
        f"{DEFAULT_HEADER_NAME} supplied by the caller to win even when "
        "correlation_id_var is set before request_with_correlation_id"
    )


@dataclasses.dataclass(slots=True)
class _CapturedRequest:
    """Captured request state from the mocked httpx call."""

    headers: httpx.Headers = dataclasses.field(default_factory=httpx.Headers)


def _capture_httpx_request(monkeypatch: pytest.MonkeyPatch) -> _CapturedRequest:
    """Patch ``httpx.request`` and capture forwarded headers."""
    captured = _CapturedRequest()

    def request(
        _method: str,
        _url: str,
        *,
        headers: dict[str, str] | httpx.Headers | None,
        **_kwargs: object,
    ) -> httpx.Response:
        captured.headers = httpx.Headers(headers)
        return httpx.Response(200)

    monkeypatch.setattr(httpx, "request", request)
    return captured


def _without_correlation_id_header(headers: dict[str, str]) -> dict[str, str]:
    """Return headers without any case variant of the correlation ID header."""
    return {
        key: value
        for key, value in headers.items()
        if key.lower() != DEFAULT_HEADER_NAME.lower()
    }
