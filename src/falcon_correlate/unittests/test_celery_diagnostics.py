"""Explicit Celery activation diagnostics without optional dependencies."""

from __future__ import annotations

import concurrent.futures
import gc
import logging
import threading
import typing as typ
import weakref
from types import SimpleNamespace
from unittest import mock

import pytest

import falcon_correlate.celery as celery_integration
from falcon_correlate.celery import configure_celery_correlation

if typ.TYPE_CHECKING:
    from falcon_correlate.celery import _CeleryAppLike


class _Backend:
    """Backend double whose URI must never appear in activation records."""

    def as_uri(self) -> str:
        """Return a URI containing an intentionally sensitive test marker."""
        return "redis://secret-user:secret-password@example.invalid/0"


class _App:
    """Hashable, weak-referenceable publisher with a normal bound method."""

    def __init__(self) -> None:
        """Give each application its own backend double."""
        self.backend = _Backend()

    def send_task(self, *_: object, **__: object) -> None:
        """Stand in for a synchronous Celery publisher."""

    def __repr__(self) -> str:
        """Return a sensitive marker to detect accidental app rendering."""
        return "app-with-secret-user-and-secret-password"


@pytest.fixture
def signal_module(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Replace only the lazy celery.signals import with independent signals."""
    signals = SimpleNamespace(
        before_task_publish=SimpleNamespace(connect=mock.Mock(return_value=False)),
        task_prerun=SimpleNamespace(connect=mock.Mock(return_value=False)),
        task_postrun=SimpleNamespace(connect=mock.Mock(return_value=False)),
    )
    original_import = celery_integration.importlib.import_module

    def import_with_signals(name: str, package: str | None = None) -> object:
        """Keep unrelated imports intact while supplying the signal double."""
        if name == "celery.signals":
            return signals
        return original_import(name, package)

    monkeypatch.setattr(
        celery_integration.importlib, "import_module", import_with_signals
    )
    return signals


def _configuration_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    """Return records emitted at the explicit configuration boundary."""
    return [
        record
        for record in caplog.records
        if getattr(record, "operation", None) == "configure_celery_correlation"
    ]


def test_complete_configuration_reports_safe_structured_info(
    signal_module: SimpleNamespace,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Successful activation has stable fields without app or backend secrets."""
    app = _App()
    with caplog.at_level(logging.INFO, logger="falcon_correlate.celery"):
        returned_app = configure_celery_correlation(app)

    assert returned_app is app, "Configuration should return the original app."
    records = _configuration_records(caplog)
    assert len(records) == 1, "Complete setup should emit one activation record."
    record = records[0]
    assert record.levelno == logging.INFO, "Complete setup should log at INFO."
    expected_fields = {
        "operation": "configure_celery_correlation",
        "registration_state": "active",
        "before_task_publish_state": "connected",
        "task_prerun_state": "connected",
        "task_postrun_state": "connected",
        "publisher_context_state": "configured",
        "backend_rpc_verdict": "unknown",
    }
    assert {key: getattr(record, key) for key in expected_fields} == expected_fields, (
        "Activation records should contain the bounded expected fields."
    )
    assert "secret-user" not in repr(record.__dict__), (
        "Activation records must not include user credentials."
    )
    assert "secret-password" not in repr(record.__dict__), (
        "Activation records must not include password values."
    )
    assert "example.invalid" not in repr(record.__dict__), (
        "Activation records must not include backend addresses."
    )
    assert record.exc_info is None, "Activation records must omit exception details."
    signal_module.before_task_publish.connect.assert_called_once()


@pytest.mark.parametrize(
    "scenario",
    [
        pytest.param(
            ("before_task_publish", "missing", "signal_missing"),
            id="missing-publish-signal",
        ),
        pytest.param(
            ("task_prerun", "non_callable", "connect_not_callable"),
            id="non-callable-prerun",
        ),
        pytest.param(
            ("task_postrun", "rejected", "receiver_rejected"),
            id="rejected-postrun",
        ),
    ],
)
def test_partial_signal_configuration_reports_warning(
    signal_module: SimpleNamespace,
    caplog: pytest.LogCaptureFixture,
    scenario: tuple[str, str, str],
) -> None:
    """A partial registration reports exactly which signal could not connect."""
    signal_name, failure, expected_state = scenario
    match failure:
        case "missing":
            delattr(signal_module, signal_name)
        case "non_callable":
            getattr(signal_module, signal_name).connect = None
        case "rejected":
            getattr(signal_module, signal_name).connect.side_effect = ValueError(
                "secret-password from rejected receiver"
            )

    configure_celery_correlation(_App())

    records = _configuration_records(caplog)
    assert len(records) == 1, "Partial setup should emit one activation record."
    record = records[0]
    assert record.levelno == logging.WARNING, "Partial setup should log at WARNING."
    assert getattr(record, "registration_state", None) == "incomplete", (
        "Partial signal setup should be marked incomplete."
    )
    assert getattr(record, f"{signal_name}_state") == expected_state, (
        "The failed signal should report its specific connection outcome."
    )
    for other_signal in {"before_task_publish", "task_prerun", "task_postrun"} - {
        signal_name
    }:
        assert getattr(record, f"{other_signal}_state") == "connected", (
            "Unaffected signals should still report successful connection."
        )
    assert "secret-password" not in repr(record.__dict__), (
        "Activation records must not include rejected receiver details."
    )


def test_unavailable_celery_signals_reports_warning(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Missing Celery remains optional but explicit setup explains inactivity."""
    original_import = celery_integration.importlib.import_module

    def import_without_signals(name: str, package: str | None = None) -> object:
        """Block only the optional signal import."""
        if name == "celery.signals":
            msg = "celery.signals unavailable"
            raise ImportError(msg)
        return original_import(name, package)

    monkeypatch.setattr(
        celery_integration.importlib, "import_module", import_without_signals
    )

    configure_celery_correlation(_App())

    records = _configuration_records(caplog)
    assert len(records) == 1, "Unavailable signals should emit one activation record."
    record = records[0]
    assert record.levelno == logging.WARNING, (
        "Unavailable Celery should log at WARNING."
    )
    assert getattr(record, "registration_state", None) == "incomplete", (
        "Unavailable signals should be marked as incomplete setup."
    )
    assert all(
        getattr(record, f"{name}_state") == "celery_signals_unavailable"
        for name in ("before_task_publish", "task_prerun", "task_postrun")
    ), "Every signal should report that Celery signals are unavailable."


@pytest.mark.parametrize(
    "publisher_state", ["send_task_unavailable", "assignment_rejected"]
)
def test_unavailable_publisher_context_reports_warning(
    signal_module: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    publisher_state: str,
) -> None:
    """Connected signals must not falsely imply publisher context was installed."""
    app = _App()
    if publisher_state == "send_task_unavailable":
        monkeypatch.setattr(app, "send_task", None)
    else:

        def reject_assignment(self: _App, name: str, value: object) -> None:
            """Model a publisher whose attributes cannot be assigned."""
            msg = "secret-password in an assignment failure"
            raise AttributeError(msg)

        monkeypatch.setattr(_App, "__setattr__", reject_assignment)

    configure_celery_correlation(typ.cast("_CeleryAppLike", app))

    records = _configuration_records(caplog)
    assert len(records) == 1, "Unavailable publisher context should log once."
    record = records[0]
    assert record.levelno == logging.WARNING, (
        "Unavailable publisher context logs WARNING."
    )
    assert getattr(record, "registration_state", None) == "incomplete", (
        "Unavailable publisher context should mark setup as incomplete."
    )
    assert getattr(record, "publisher_context_state", None) == publisher_state, (
        "The record should identify the publisher-context outcome."
    )
    assert getattr(record, "before_task_publish_state", None) == "connected", (
        "Publisher failure should not hide a successful publish signal connection."
    )
    assert "secret-password" not in repr(record.__dict__), (
        "Activation records must not include assignment exception details."
    )


def test_backend_verdict_is_deferred_until_publishing(
    signal_module: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Activation leaves Celery's lazy backend alone and reports it as unknown."""
    app = _App()
    inspection = mock.Mock(wraps=app.backend.as_uri)
    monkeypatch.setattr(app.backend, "as_uri", inspection)

    with caplog.at_level(logging.INFO, logger="falcon_correlate.celery"):
        configure_celery_correlation(app)

    records = _configuration_records(caplog)
    assert len(records) == 1, "Backend inspection should emit one activation record."
    record = records[0]
    assert record.levelno == logging.INFO, "Valid signal setup should log at INFO."
    assert getattr(record, "registration_state", None) == "active", (
        "Backend uncertainty should not mark registered signals as incomplete."
    )
    assert getattr(record, "backend_rpc_verdict", None) == "unknown", (
        "Activation should report an uninspected backend verdict."
    )
    inspection.assert_not_called()


def test_failed_configuration_can_report_success_on_retry(
    signal_module: SimpleNamespace,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A deduplicated failure must not suppress later successful activation."""
    app = _App()
    connection = signal_module.task_prerun.connect
    connection.side_effect = ValueError("rejected")

    with caplog.at_level(logging.INFO, logger="falcon_correlate.celery"):
        configure_celery_correlation(app)
        configure_celery_correlation(app)
        connection.side_effect = None
        configure_celery_correlation(app)
        configure_celery_correlation(app)

    records = _configuration_records(caplog)
    assert [record.levelno for record in records] == [logging.WARNING, logging.INFO], (
        "A later successful retry should be logged after the initial warning."
    )
    assert [getattr(record, "registration_state", None) for record in records] == [
        "incomplete",
        "active",
    ], "Retries should report incomplete and then active registration states."


def test_repeated_configuration_reports_each_app_once(
    signal_module: SimpleNamespace,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Deduplication is local to an app and does not silence another app."""
    apps = (_App(), _App())
    with caplog.at_level(logging.INFO, logger="falcon_correlate.celery"):
        for app in apps:
            configure_celery_correlation(app)
            configure_celery_correlation(app)

    assert len(_configuration_records(caplog)) == len(apps), (
        "Each app should emit one activation record despite repeated setup."
    )


def test_configuration_diagnostics_do_not_retain_application(
    signal_module: SimpleNamespace,
) -> None:
    """Diagnostic history must disappear with the weak-referenceable app."""
    app = _App()
    reference = weakref.ref(app)
    configure_celery_correlation(app)

    del app
    gc.collect()

    assert reference() is None, "Diagnostics must not retain configured applications."


def test_concurrent_incomplete_configuration_reports_once(
    signal_module: SimpleNamespace,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Concurrent retries of the same failure produce a single warning."""
    app = _App()
    signal_module.task_postrun.connect = None
    barrier = threading.Barrier(4)

    def configure_from_thread() -> None:
        """Start each configuration at the same barrier."""
        barrier.wait(timeout=5)
        configure_celery_correlation(app)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(configure_from_thread) for _ in range(4)]
        for future in futures:
            future.result(timeout=5)

    records = _configuration_records(caplog)
    assert len(records) == 1, "Concurrent identical failures should be deduplicated."
    assert records[0].levelno == logging.WARNING, (
        "Concurrent incomplete setup should produce a warning."
    )
    assert getattr(records[0], "task_postrun_state", None) == "connect_not_callable", (
        "The concurrent warning should report the unavailable task-postrun signal."
    )
