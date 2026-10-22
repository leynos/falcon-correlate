"""Verify Celery signal registration requires explicit configuration."""

from __future__ import annotations

import json
import os
import textwrap

import pytest

from falcon_correlate.unittests.optional_celery_dependency_helpers import (
    _PROJECT_ROOT,
    _run_python,
)

_IMPORT_PROBE = textwrap.dedent(
    """
    import json
    import sys

    mode = sys.argv[1]
    celery_modules_before_import = {
        name for name in sys.modules if name == "celery" or name.startswith("celery.")
    }
    if mode == "package":
        import falcon_correlate
    elif mode == "module":
        import falcon_correlate.celery as integration
    else:
        raise ValueError(f"unsupported import mode: {mode}")

    celery_modules_imported_by_integration = sorted(
        name
        for name in sys.modules
        if (name == "celery" or name.startswith("celery."))
        and name not in celery_modules_before_import
    )

    import celery.signals as signals
    from celery import Celery
    import falcon_correlate.celery as integration

    signal_handlers = {
        "before_task_publish": (
            signals.before_task_publish,
            integration.propagate_correlation_id_to_celery,
            integration._BEFORE_TASK_PUBLISH_DISPATCH_UID,
        ),
        "task_prerun": (
            signals.task_prerun,
            integration.setup_correlation_id_in_worker,
            integration._TASK_PRERUN_DISPATCH_UID,
        ),
        "task_postrun": (
            signals.task_postrun,
            integration.clear_correlation_id_in_worker,
            integration._TASK_POSTRUN_DISPATCH_UID,
        ),
    }

    def receiver_counts(signal, handler, dispatch_uid):
        receivers = signal.receivers
        return {
            "package_receivers": sum(
                getattr(receiver, "__module__", "").startswith("falcon_correlate")
                for _, receiver in receivers
            ),
            "dispatch_uid_receivers": sum(
                lookup_key[0] == dispatch_uid
                for lookup_key, _ in receivers
            ),
            "handler_identity_receivers": sum(
                receiver is handler for _, receiver in receivers
            ),
        }

    def all_counts():
        return {
            name: receiver_counts(signal, handler, dispatch_uid)
            for name, (signal, handler, dispatch_uid) in signal_handlers.items()
        }

    result = {
        "mode": mode,
        "celery_modules_imported_by_integration": (
            celery_modules_imported_by_integration
        ),
        "before": all_counts(),
    }
    if mode == "package":
        app = Celery("probe")
        result["first_call_returns_app"] = (
            integration.configure_celery_correlation(app) is app
        )
        result["after_first_call"] = all_counts()
        result["second_call_returns_app"] = (
            integration.configure_celery_correlation(app) is app
        )
        result["after_second_call"] = all_counts()

    print(json.dumps(result, sort_keys=True), flush=True)
    """
)


def _run_import_probe(mode: str) -> dict[str, object]:
    """Run one import scenario in an unmodified fresh Python interpreter."""
    result = _run_python(os.environ, _PROJECT_ROOT, "-c", _IMPORT_PROBE, mode)
    failure_message = (
        f"import probe failed for {mode}: stdout={result.stdout!r}, "
        f"stderr={result.stderr!r}"
    )
    assert result.returncode == 0, failure_message
    payload = json.loads(result.stdout)
    assert isinstance(payload, dict), "expected the child probe to print a JSON object"
    return payload


def _assert_no_receivers(counts: object) -> None:
    """Assert all supported signals start without integration receivers."""
    expected_counts = {
        "before_task_publish": {
            "package_receivers": 0,
            "dispatch_uid_receivers": 0,
            "handler_identity_receivers": 0,
        },
        "task_prerun": {
            "package_receivers": 0,
            "dispatch_uid_receivers": 0,
            "handler_identity_receivers": 0,
        },
        "task_postrun": {
            "package_receivers": 0,
            "dispatch_uid_receivers": 0,
            "handler_identity_receivers": 0,
        },
    }
    assert counts == expected_counts, (
        f"unexpected receivers before configuration: {counts!r}"
    )


def _assert_one_receiver_per_signal(counts: object, stage: str) -> None:
    """Assert each stable dispatch UID identifies its handler exactly once."""
    expected_counts = {
        signal_name: {
            "package_receivers": 1,
            "dispatch_uid_receivers": 1,
            "handler_identity_receivers": 1,
        }
        for signal_name in (
            "before_task_publish",
            "task_prerun",
            "task_postrun",
        )
    }
    assert counts == expected_counts, (
        f"{stage}: unexpected signal receivers: {counts!r}"
    )


def test_package_import_and_configuration_control_signal_registration() -> None:
    """Package import is inert; explicit configuration connects all receivers."""
    pytest.importorskip("celery")
    result = _run_import_probe("package")

    assert result["mode"] == "package", "package probe should report package mode"
    assert result["celery_modules_imported_by_integration"] == [], (
        "package import should not load Celery modules"
    )
    _assert_no_receivers(result["before"])
    _assert_one_receiver_per_signal(result["after_first_call"], "first call")
    _assert_one_receiver_per_signal(result["after_second_call"], "second call")
    assert result["first_call_returns_app"] is True, (
        "first configuration call should return the same app"
    )
    assert result["second_call_returns_app"] is True, (
        "repeated configuration call should return the same app"
    )


def test_direct_celery_module_import_does_not_connect_signal_receivers() -> None:
    """Directly importing the integration module leaves Celery signals alone."""
    pytest.importorskip("celery")
    result = _run_import_probe("module")

    assert result["mode"] == "module", "module probe should report module mode"
    assert result["celery_modules_imported_by_integration"] == [], (
        "direct integration import should not load Celery modules"
    )
    _assert_no_receivers(result["before"])
