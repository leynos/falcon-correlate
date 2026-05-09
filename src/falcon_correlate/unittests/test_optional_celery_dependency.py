"""Validation for Celery remaining an optional test dependency."""

from __future__ import annotations

import os
import subprocess
import sys
import typing as typ

if typ.TYPE_CHECKING:
    from pathlib import Path

_CELERY_TEST_PATHS = (
    "src/falcon_correlate/unittests/test_celery_publish_signal.py",
    "src/falcon_correlate/unittests/test_celery_worker_signal.py",
    "src/falcon_correlate/unittests/test_celery_configuration.py",
    "tests/bdd/test_celery_publish_signal_steps.py",
    "tests/bdd/test_celery_worker_signal_steps.py",
    "tests/bdd/test_celery_configuration_steps.py",
)


def _write_celery_import_blocker(sitecustomize_dir: Path) -> Path:
    """Write a child-process hook that makes only Celery imports unavailable."""
    sitecustomize = sitecustomize_dir / "sitecustomize.py"
    sitecustomize.write_text(
        """
from __future__ import annotations

import importlib.abc
import importlib.machinery


class _BlockCeleryFinder(importlib.abc.MetaPathFinder):
    def find_spec(
        self,
        fullname: str,
        path: object | None,
        target: object | None = None,
    ) -> importlib.machinery.ModuleSpec | None:
        if fullname == "celery" or fullname.startswith("celery."):
            raise ModuleNotFoundError("No module named 'celery'", name=fullname)
        return None


import sys

sys.meta_path.insert(0, _BlockCeleryFinder())
""".lstrip(),
        encoding="utf-8",
    )
    return sitecustomize


def _write_child_sentinel_test(tmp_path: Path) -> Path:
    """Write a passing test so pytest exits successfully when Celery tests skip."""
    sentinel = tmp_path / "test_non_celery_sentinel.py"
    sentinel.write_text(
        "def test_non_celery_suite_still_runs():\n    assert True\n",
        encoding="utf-8",
    )
    return sentinel


def _pythonpath_with_import_blocker(sitecustomize_dir: Path) -> str:
    """Return a PYTHONPATH with the import blocker taking precedence."""
    existing_pythonpath = os.environ.get("PYTHONPATH")
    paths = [str(sitecustomize_dir)]
    if existing_pythonpath:
        paths.append(existing_pythonpath)
    return os.pathsep.join(paths)


def _run_with_celery_blocked(
    tmp_path: Path,
    *args: str,
) -> subprocess.CompletedProcess[str]:
    """Run a Python child process where importing Celery raises ImportError."""
    _write_celery_import_blocker(tmp_path)
    env = {
        **os.environ,
        "PYTHONPATH": _pythonpath_with_import_blocker(tmp_path),
    }
    return subprocess.run(  # noqa: S603
        [sys.executable, *args],
        check=False,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )


def test_package_and_celery_module_import_without_celery(
    tmp_path: Path,
) -> None:
    """The package and optional Celery module should import without Celery."""
    result = _run_with_celery_blocked(
        tmp_path,
        "-c",
        (
            "import importlib; "
            "import falcon_correlate; "
            "importlib.import_module('falcon_correlate.celery')"
        ),
    )

    assert result.returncode == 0, result.stderr


def test_celery_dependent_tests_skip_when_celery_is_unavailable(
    tmp_path: Path,
) -> None:
    """Celery-only unit and BDD tests should skip, not fail collection."""
    sentinel_test = _write_child_sentinel_test(tmp_path)
    result = _run_with_celery_blocked(
        tmp_path,
        "-m",
        "pytest",
        "-q",
        str(sentinel_test),
        *_CELERY_TEST_PATHS,
    )
    combined_output = f"{result.stdout}\n{result.stderr}"

    assert result.returncode == 0, combined_output
    assert "1 passed" in combined_output
    assert "skipped" in combined_output
    assert "ERROR" not in combined_output
    assert "FAILED" not in combined_output
