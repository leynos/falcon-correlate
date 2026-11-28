"""Tests for Celery result-backend verdict classification and caching."""

from __future__ import annotations

import logging
import types
import typing as typ

import pytest

try:
    from celery import Celery
except ModuleNotFoundError as error:  # pragma: no cover - blocked child only
    if error.name != "celery":
        raise
    _HAS_CELERY = False
else:
    _HAS_CELERY = True

pytestmark = pytest.mark.skipif(
    not _HAS_CELERY,
    reason="celery is not installed",
)

from falcon_correlate import (  # ruff: ignore[module-import-not-at-top-of-file] -- dependency probe first.
    celery as falcon_celery,
)
from falcon_correlate.celery import (  # ruff: ignore[module-import-not-at-top-of-file] -- dependency probe first.
    _app_backend_uses_rpc,
    _cache_app_backend_rpc_verdict,
)
from falcon_correlate.unittests.celery_backend_test_doubles import (  # ruff: ignore[module-import-not-at-top-of-file] -- dependency probe first.
    AppWithoutBackend,
    MalformedCeleryApp,
    RaisingBackendPropertyApp,
    RaisingUriBackend,
    StringableUri,
    StubCeleryApp,
    celery_debug_messages,
)


def test_backend_uri_failure_is_unknown_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A backend error must not be mistaken for a non-RPC verdict."""
    with caplog.at_level(logging.DEBUG, logger="falcon_correlate.celery"):
        backend_uses_rpc = _app_backend_uses_rpc(MalformedCeleryApp())

    assert backend_uses_rpc is None, (
        "an inspection exception must remain distinct from a non-RPC verdict"
    )
    assert celery_debug_messages(caplog) == [
        "Unable to inspect Celery result backend URI; preserving task ID."
    ], "a failed backend lookup should emit the documented diagnostic"
    failure_record = next(
        record for record in caplog.records if record.name == "falcon_correlate.celery"
    )
    # ``logger.debug(..., exc_info=False)`` stores ``False`` rather than
    # ``None`` on the record, so require the captured traceback tuple itself.
    assert isinstance(failure_record.exc_info, tuple), (
        "the diagnostic should retain the inspection traceback"
    )


def test_backend_uri_failure_with_task_name_logs_publishing_context(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A publishing task name should be included in the diagnostic."""
    with caplog.at_level(logging.DEBUG, logger="falcon_correlate.celery"):
        backend_uses_rpc = _app_backend_uses_rpc(
            MalformedCeleryApp(),
            task_name="publishing-task",
        )

    assert backend_uses_rpc is None, "a named task inspection failure is inconclusive"
    assert celery_debug_messages(caplog) == [
        (
            "Unable to inspect Celery result backend URI for publishing task "
            "'publishing-task'; preserving task ID."
        )
    ], "the failure diagnostic should name the publishing task"


def test_backend_uri_failure_with_non_string_task_name_omits_context(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Only string task names belong in the diagnostic message."""
    with caplog.at_level(logging.DEBUG, logger="falcon_correlate.celery"):
        backend_uses_rpc = _app_backend_uses_rpc(
            MalformedCeleryApp(),
            task_name=object(),
        )

    assert backend_uses_rpc is None, (
        "a non-string task name inspection failure is inconclusive"
    )
    assert celery_debug_messages(caplog) == [
        "Unable to inspect Celery result backend URI; preserving task ID."
    ], "a non-string task name should not appear in the diagnostic"


def test_missing_backend_attribute_is_a_non_rpc_verdict() -> None:
    """Missing optional backend members retain the defensive false result."""
    app_without_backend = typ.cast("typ.Any", AppWithoutBackend())
    assert _app_backend_uses_rpc(app_without_backend) is False, (
        "an app without backend configuration should be treated as non-RPC"
    )


def test_backend_without_as_uri_is_a_non_rpc_verdict() -> None:
    """A backend that exposes no URI accessor is treated as non-RPC."""
    app = StubCeleryApp(types.SimpleNamespace())

    assert _app_backend_uses_rpc(typ.cast("typ.Any", app)) is False, (
        "a missing as_uri member must not make inspection inconclusive"
    )


def test_backend_with_non_callable_as_uri_is_a_non_rpc_verdict() -> None:
    """A non-callable URI member is not evidence of an RPC backend."""
    app = StubCeleryApp(types.SimpleNamespace(as_uri="rpc://"))

    assert _app_backend_uses_rpc(typ.cast("typ.Any", app)) is False, (
        "a non-callable as_uri must not be mistaken for an RPC backend"
    )


@pytest.mark.parametrize(
    ("uri", "expected_uses_rpc"),
    [
        pytest.param("rpc://", True, id="bare-rpc-scheme"),
        pytest.param("rpc://result-queue", True, id="rpc-scheme-with-queue"),
        pytest.param("RPC://result-queue", False, id="scheme-is-case-sensitive"),
        pytest.param("xrpc://result-queue", False, id="rpc-suffix-not-a-prefix"),
        pytest.param("rpc:/result-queue", False, id="incomplete-scheme"),
        pytest.param("cache+memory://", False, id="non-rpc-scheme"),
    ],
)
def test_backend_uri_scheme_classification(
    uri: str,
    *,
    expected_uses_rpc: bool,
) -> None:
    """Only URIs beginning with the exact RPC scheme are RPC backends."""
    app = StubCeleryApp(types.SimpleNamespace(as_uri=lambda: uri))

    assert _app_backend_uses_rpc(typ.cast("typ.Any", app)) is expected_uses_rpc, (
        "the URI scheme should decide whether the backend is RPC"
    )


def test_backend_uri_is_stringified_before_scheme_classification() -> None:
    """A URI object should be rendered before the scheme check."""
    backend = types.SimpleNamespace(as_uri=lambda: StringableUri("rpc://queue"))
    app = StubCeleryApp(backend)

    assert _app_backend_uses_rpc(typ.cast("typ.Any", app)) is True, (
        "a stringified rpc:// URI should classify as RPC"
    )


def test_backend_property_failure_is_unknown() -> None:
    """An unreadable backend member makes inspection inconclusive."""
    assert _app_backend_uses_rpc(RaisingBackendPropertyApp()) is None, (
        "an unreadable backend member must stay inconclusive"
    )


def test_backend_uri_accessor_failure_is_unknown() -> None:
    """An unreadable URI accessor makes inspection inconclusive."""
    app = StubCeleryApp(RaisingUriBackend())

    assert _app_backend_uses_rpc(typ.cast("typ.Any", app)) is None, (
        "an unreadable URI accessor must stay inconclusive"
    )


def test_backend_verdict_cache_is_per_application() -> None:
    """Each application keeps its own backend verdict."""
    rpc_app = Celery(
        "verdict-cache-rpc-app",
        backend="rpc://",
        broker="memory://",
        set_as_current=False,
    )
    non_rpc_app = Celery(
        "verdict-cache-non-rpc-app",
        backend="cache+memory://",
        broker="memory://",
        set_as_current=False,
    )

    assert _cache_app_backend_rpc_verdict(rpc_app) is True, (
        "the RPC app should keep its own verdict"
    )
    assert _cache_app_backend_rpc_verdict(non_rpc_app) is False, (
        "a second app must not inherit the first app's verdict"
    )
    assert _cache_app_backend_rpc_verdict(rpc_app) is True, (
        "the cached RPC verdict should be stable"
    )
    assert _cache_app_backend_rpc_verdict(non_rpc_app) is False, (
        "the cached non-RPC verdict should be stable"
    )


def test_cache_forwards_task_name_and_retries_unknown_verdict(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed inspection keeps its task context and stays retryable."""
    app = typ.cast("typ.Any", MalformedCeleryApp())

    with caplog.at_level(logging.DEBUG, logger="falcon_correlate.celery"):
        first_verdict = _cache_app_backend_rpc_verdict(app, task_name="cache-task")

    assert first_verdict is None, "a failed inspection should stay inconclusive"
    assert celery_debug_messages(caplog) == [
        (
            "Unable to inspect Celery result backend URI for publishing task "
            "'cache-task'; preserving task ID."
        )
    ], "the cache path should forward the task name to the diagnostic"
    assert app not in falcon_celery._configured_app_backend_rpc_verdicts, (
        "an inconclusive verdict must not be cached"
    )

    app.backend = types.SimpleNamespace(as_uri=lambda: "rpc://")

    assert _cache_app_backend_rpc_verdict(app, task_name="cache-task") is True, (
        "the retry should record the now-definite RPC verdict"
    )
    assert falcon_celery._configured_app_backend_rpc_verdicts[app] is True, (
        "the retried verdict should be stored on the app"
    )
