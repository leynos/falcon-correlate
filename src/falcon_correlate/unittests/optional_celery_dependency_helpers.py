"""Validate test-suite behaviour when the optional Celery dependency is absent.

Celery support is optional for library consumers, but this repository installs
Celery in the normal development environment so the integration tests can run.
These tests exercise the missing-dependency path without uninstalling Celery by
launching child Python processes with a temporary ``sitecustomize.py`` import
hook that blocks only ``celery`` and ``celery.*``.

The subprocess boundary matters because pytest evaluates module-level
``pytest.importorskip("celery")`` guards during collection. Running pytest in a
child process verifies the same collection behaviour a downstream test suite
would see: Celery-dependent unit and Behaviour-Driven Development (BDD) step
modules are skipped, while non-Celery tests continue to run.

Compile-time validation strategy
---------------------------------
This project does not use Rust-style ``trybuild`` tests. Compile-time
correctness is validated by two complementary mechanisms:

1. **Static type checking** — ``make typecheck`` runs mypy over the entire
   source tree, including this module, and must report zero errors before
   merge.

2. **Import-time subprocess tests** —
   ``test_package_and_celery_module_import_without_celery`` launches child
   Python processes and asserts that ``falcon_correlate`` and
   ``falcon_correlate.celery`` import without error under Celery-blocked
   conditions, covering the import path that would raise at collection time in
   a downstream test suite.
"""

from __future__ import annotations

import os
import re
import subprocess  # noqa: S404 - tests intentionally spawn isolated Python subprocesses.
import sys
import typing as typ
from pathlib import Path

import pytest

if typ.TYPE_CHECKING:
    import collections.abc as cabc

_CELERY_TEST_GLOBS = (
    "src/falcon_correlate/unittests/test_celery_*.py",
    "tests/bdd/test_celery_*_steps.py",
)
_MINIMUM_CELERY_TEST_MODULE_COUNT = 6
_PYTEST_DURATION_PATTERN = re.compile(
    r"\d+\.\d+s(?: \(\d+:\d{2}:\d{2}\))?",
)
_PYTEST_PROGRESS_PATTERN = re.compile(
    r"^(?P<progress>[.s]+)\s+\[100%\]$",
    re.MULTILINE,
)
_CELERY_BLOCKED_PYTEST_TIMEOUT_SECONDS = 120

pytestmark = pytest.mark.timeout(_CELERY_BLOCKED_PYTEST_TIMEOUT_SECONDS)


def _find_project_root(start: Path) -> Path:
    """Return the nearest ancestor containing the repository project marker."""
    start_dir = start.resolve().parent if start.is_file() else start.resolve()
    for candidate in (start_dir, *start_dir.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise RuntimeError


_PROJECT_ROOT = _find_project_root(Path(__file__))


class _PytestRun(typ.NamedTuple):
    """Captured child pytest result and expected skip output."""

    result: subprocess.CompletedProcess[str]
    normalized_stdout: str
    expected_stdout: str


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


def _discover_celery_test_paths(project_root: Path) -> tuple[Path, ...]:
    """Return current Celery-dependent unit and BDD step modules."""
    paths = {
        path
        for pattern in _CELERY_TEST_GLOBS
        for path in project_root.glob(pattern)
        if path.is_file()
    }
    return tuple(sorted(paths))


def _pythonpath_with_import_blocker(
    sitecustomize_dir: Path,
    environ: cabc.Mapping[str, str],
) -> str:
    """Return a PYTHONPATH with the import blocker taking precedence."""
    existing_pythonpath = environ.get("PYTHONPATH")
    paths = [str(sitecustomize_dir)]
    if existing_pythonpath:
        paths.append(existing_pythonpath)
    return os.pathsep.join(paths)


def _blocked_celery_environment(
    sitecustomize_dir: Path,
    environ: cabc.Mapping[str, str],
) -> dict[str, str]:
    """Build a child-process environment with the Celery import blocker first."""
    return {
        **environ,
        "PYTHONPATH": _pythonpath_with_import_blocker(sitecustomize_dir, environ),
    }


def _run_python_with_celery_blocked(
    sitecustomize_dir: Path,
    environ: cabc.Mapping[str, str],
    cwd: Path,
    *args: str,
) -> subprocess.CompletedProcess[str]:
    """Run a Python child process where importing Celery raises ImportError."""
    return subprocess.run(  # noqa: S603
        [sys.executable, *args],
        check=False,
        cwd=cwd,
        env=_blocked_celery_environment(sitecustomize_dir, environ),
        text=True,
        capture_output=True,
        timeout=_CELERY_BLOCKED_PYTEST_TIMEOUT_SECONDS,
    )


def _relative_paths(paths: cabc.Iterable[Path], project_root: Path) -> tuple[str, ...]:
    """Return paths relative to the repository root for subprocess pytest."""
    return tuple(str(path.relative_to(project_root)) for path in paths)


def _normalize_pytest_output(output: str) -> str:
    """Redact nondeterministic pytest duration fields from quiet output."""
    normalized_progress = _PYTEST_PROGRESS_PATTERN.sub(
        r"\g<progress> [100%]",
        output.strip(),
    )
    return _PYTEST_DURATION_PATTERN.sub("<duration>", normalized_progress)


def _run_celery_tests_with_celery_blocked(
    sitecustomize_dir: Path,
    sentinel_test: Path,
    celery_test_paths: tuple[Path, ...],
    project_root: Path,
) -> _PytestRun:
    """Run selected Celery tests in a child process with Celery unavailable."""
    result = _run_python_with_celery_blocked(
        sitecustomize_dir,
        os.environ,
        project_root,
        "-m",
        "pytest",
        "-q",
        str(sentinel_test),
        *_relative_paths(celery_test_paths, project_root),
    )
    expected_stdout = f""". [100%]
1 passed, {len(celery_test_paths)} skipped in <duration>"""
    return _PytestRun(
        result=result,
        normalized_stdout=_normalize_pytest_output(result.stdout),
        expected_stdout=expected_stdout,
    )
