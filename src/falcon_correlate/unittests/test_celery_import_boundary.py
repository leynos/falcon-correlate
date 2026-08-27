"""Regression tests for Celery's explicit import and registration boundary."""

from __future__ import annotations

import subprocess  # noqa: S404 - test intentionally isolates global signal state.
import sys

import pytest

from falcon_correlate.unittests.optional_celery_dependency_helpers import (
    _CELERY_BLOCKED_PYTEST_TIMEOUT_SECONDS,
    _PROJECT_ROOT,
)

try:
    import celery  # noqa: F401 - the import probes whether this Celery test can run.
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


def test_package_import_defers_celery_and_signal_registration() -> None:
    """Package import must not load Celery or mutate its global signals."""
    script = """
import sys

import falcon_correlate

assert "celery" not in sys.modules

from celery import Celery
from celery.signals import before_task_publish, task_postrun, task_prerun
from falcon_correlate.celery import (
    _BEFORE_TASK_PUBLISH_DISPATCH_UID,
    _TASK_POSTRUN_DISPATCH_UID,
    _TASK_PRERUN_DISPATCH_UID,
    configure_celery_correlation,
)


def has_receiver(signal, dispatch_uid):
    return any(lookup_key[0] == dispatch_uid for lookup_key, _ in signal.receivers)


signals = (
    (before_task_publish, _BEFORE_TASK_PUBLISH_DISPATCH_UID),
    (task_prerun, _TASK_PRERUN_DISPATCH_UID),
    (task_postrun, _TASK_POSTRUN_DISPATCH_UID),
)
assert not any(has_receiver(signal, dispatch_uid) for signal, dispatch_uid in signals)

configure_celery_correlation(Celery("celery-import-boundary", broker="memory://"))

assert all(has_receiver(signal, dispatch_uid) for signal, dispatch_uid in signals)
"""
    result = subprocess.run(  # noqa: S603 - test intentionally runs Python itself.
        [sys.executable, "-c", script],
        check=False,
        cwd=_PROJECT_ROOT,
        text=True,
        capture_output=True,
        timeout=_CELERY_BLOCKED_PYTEST_TIMEOUT_SECONDS,
    )

    assert result.returncode == 0, (
        "Package import should defer Celery loading and signal registration.\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
