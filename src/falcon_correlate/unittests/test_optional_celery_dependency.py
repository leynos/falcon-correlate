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
_PYTEST_DURATION_PATTERN = re.compile(r"\d+\.\d+s")
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


@pytest.fixture(scope="module")
def celery_blocked_pytest_run(
    tmp_path_factory: pytest.TempPathFactory,
) -> _PytestRun:
    """Run the Celery skip subprocess once for shared assertions."""
    tmp_path = tmp_path_factory.mktemp("celery-blocked-suite")
    _write_celery_import_blocker(tmp_path)
    sentinel_test = _write_child_sentinel_test(tmp_path)
    celery_test_paths = _discover_celery_test_paths(_PROJECT_ROOT)
    return _run_celery_tests_with_celery_blocked(
        tmp_path,
        sentinel_test,
        celery_test_paths,
        _PROJECT_ROOT,
    )


@pytest.fixture(scope="module")
def project_root() -> Path:
    """Return the repository root for query helper injection."""
    return _PROJECT_ROOT


def test_celery_test_path_discovery_finds_expected_minimum(
    project_root: Path,
) -> None:
    """Enough Celery test modules must be discovered for meaningful checks."""
    celery_test_paths = _discover_celery_test_paths(project_root)
    assert len(celery_test_paths) >= _MINIMUM_CELERY_TEST_MODULE_COUNT, (
        "Celery test discovery should find enough guarded modules for "
        "missing-dependency skip validation."
    )


def test_blocked_celery_environment_prepends_existing_pythonpath(
    tmp_path: Path,
) -> None:
    """The import blocker should lead PYTHONPATH without discarding callers."""
    env = _blocked_celery_environment(
        tmp_path,
        {"PYTHONPATH": f"/already{os.pathsep}/present", "KEEP": "1"},
    )

    assert env["KEEP"] == "1", "Blocked environment should preserve unrelated keys."
    assert env["PYTHONPATH"] == (
        f"{tmp_path}{os.pathsep}/already{os.pathsep}/present"
    ), "Blocked environment should prepend the import blocker to PYTHONPATH."


def test_blocked_celery_environment_sets_pythonpath_when_missing(
    tmp_path: Path,
) -> None:
    """The import blocker should set PYTHONPATH when it is missing."""
    env = _blocked_celery_environment(
        tmp_path,
        {"KEEP": "1"},
    )

    assert env["KEEP"] == "1", "Blocked environment should preserve unrelated keys."
    assert env["PYTHONPATH"] == str(tmp_path), (
        "Blocked environment should set PYTHONPATH to the import blocker."
    )


@pytest.mark.parametrize(
    "module_name",
    [
        pytest.param("falcon_correlate"),
        pytest.param("falcon_correlate.celery"),
    ],
)
def test_package_and_celery_module_import_without_celery(
    tmp_path: Path,
    module_name: str,
) -> None:
    """Package modules should import independently when Celery is unavailable."""
    _write_celery_import_blocker(tmp_path)
    result = _run_python_with_celery_blocked(
        tmp_path,
        os.environ,
        _PROJECT_ROOT,
        "-c",
        f"import importlib; importlib.import_module({module_name!r})",
    )

    assert result.returncode == 0, (
        f"{module_name} should import when Celery is unavailable.\n{result.stderr}"
    )


@pytest.mark.parametrize(
    "module_name",
    [
        pytest.param("celery"),
        pytest.param("celery.signals"),
    ],
)
def test_celery_import_blocker_rejects_celery_modules(
    tmp_path: Path,
    module_name: str,
) -> None:
    """The subprocess hook should block top-level and nested Celery imports."""
    _write_celery_import_blocker(tmp_path)
    result = _run_python_with_celery_blocked(
        tmp_path,
        os.environ,
        _PROJECT_ROOT,
        "-c",
        f"import importlib; importlib.import_module({module_name!r})",
    )

    blocked_name = module_name.split(".", maxsplit=1)[0]
    assert result.returncode != 0, (
        f"{module_name} should fail to import when the Celery blocker is active."
    )
    assert f"No module named '{blocked_name}'" in result.stderr, (
        f"{module_name} should fail with a missing-Celery import error."
    )


def test_celery_tests_emit_no_error_markers_when_celery_is_unavailable(
    celery_blocked_pytest_run: _PytestRun,
) -> None:
    """Celery-only tests should not report collection or execution errors."""
    assert "ERROR" not in celery_blocked_pytest_run.result.stderr, (
        "Missing-Celery pytest run should not report collection errors."
    )
    assert "FAILED" not in celery_blocked_pytest_run.result.stderr, (
        "Missing-Celery pytest run should not report failed tests."
    )


def test_celery_tests_exit_successfully_when_celery_is_unavailable(
    celery_blocked_pytest_run: _PytestRun,
) -> None:
    """Celery-only tests should exit successfully when a sentinel test runs."""
    assert celery_blocked_pytest_run.result.returncode == 0, (
        "Missing-Celery pytest run should exit successfully with skipped "
        "Celery tests and a passing sentinel.\n"
        f"{celery_blocked_pytest_run.result.stdout}\n"
        f"{celery_blocked_pytest_run.result.stderr}"
    )


def test_celery_tests_report_correct_skip_count_when_celery_is_unavailable(
    celery_blocked_pytest_run: _PytestRun,
) -> None:
    """Celery-only tests should match the skip-count snapshot."""
    assert (
        celery_blocked_pytest_run.normalized_stdout
        == celery_blocked_pytest_run.expected_stdout
    ), "Missing-Celery pytest output should match the expected skip-count snapshot."
