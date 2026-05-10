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
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys
import typing as typ

import pytest

_PROJECT_ROOT = pathlib.Path(__file__).parents[3]
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


def _write_celery_import_blocker(sitecustomize_dir: pathlib.Path) -> pathlib.Path:
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


def _write_child_sentinel_test(tmp_path: pathlib.Path) -> pathlib.Path:
    """Write a passing test so pytest exits successfully when Celery tests skip."""
    sentinel = tmp_path / "test_non_celery_sentinel.py"
    sentinel.write_text(
        "def test_non_celery_suite_still_runs():\n    assert True\n",
        encoding="utf-8",
    )
    return sentinel


def _discover_celery_test_paths() -> tuple[pathlib.Path, ...]:
    """Return current Celery-dependent unit and BDD step modules."""
    paths = {
        path
        for pattern in _CELERY_TEST_GLOBS
        for path in _PROJECT_ROOT.glob(pattern)
        if path.is_file()
    }
    return tuple(sorted(paths))


def _pythonpath_with_import_blocker(
    sitecustomize_dir: pathlib.Path,
    environ: typ.Mapping[str, str],
) -> str:
    """Return a PYTHONPATH with the import blocker taking precedence."""
    existing_pythonpath = environ.get("PYTHONPATH")
    paths = [str(sitecustomize_dir)]
    if existing_pythonpath:
        paths.append(existing_pythonpath)
    return os.pathsep.join(paths)


def _blocked_celery_environment(
    sitecustomize_dir: pathlib.Path,
    environ: typ.Mapping[str, str],
) -> dict[str, str]:
    """Build a child-process environment with the Celery import blocker first."""
    return {
        **environ,
        "PYTHONPATH": _pythonpath_with_import_blocker(sitecustomize_dir, environ),
    }


def _run_python_with_celery_blocked(
    sitecustomize_dir: pathlib.Path,
    environ: typ.Mapping[str, str],
    *args: str,
) -> subprocess.CompletedProcess[str]:
    """Run a Python child process where importing Celery raises ImportError."""
    _write_celery_import_blocker(sitecustomize_dir)
    return subprocess.run(  # noqa: S603
        [sys.executable, *args],
        check=False,
        env=_blocked_celery_environment(sitecustomize_dir, environ),
        text=True,
        capture_output=True,
        timeout=30,
    )


def _relative_paths(paths: typ.Iterable[pathlib.Path]) -> tuple[str, ...]:
    """Return paths relative to the repository root for subprocess pytest."""
    return tuple(str(path.relative_to(_PROJECT_ROOT)) for path in paths)


def _normalise_pytest_output(output: str) -> str:
    """Redact nondeterministic pytest duration fields from quiet output."""
    normalised_progress = _PYTEST_PROGRESS_PATTERN.sub(
        r"\g<progress> [100%]",
        output.strip(),
    )
    return _PYTEST_DURATION_PATTERN.sub("<duration>", normalised_progress)


def test_celery_test_path_discovery_covers_guarded_modules() -> None:
    """Every discovered Celery test module should use the import-skip guard."""
    celery_test_paths = _discover_celery_test_paths()

    assert len(celery_test_paths) >= _MINIMUM_CELERY_TEST_MODULE_COUNT
    assert all(
        'pytest.importorskip("celery")' in path.read_text(encoding="utf-8")
        for path in celery_test_paths
    )


def test_blocked_celery_environment_prepends_existing_pythonpath(
    tmp_path: pathlib.Path,
) -> None:
    """The import blocker should lead PYTHONPATH without discarding callers."""
    env = _blocked_celery_environment(
        tmp_path,
        {"PYTHONPATH": f"/already{os.pathsep}/present", "KEEP": "1"},
    )

    assert env["KEEP"] == "1"
    assert env["PYTHONPATH"] == f"{tmp_path}{os.pathsep}/already{os.pathsep}/present"


@pytest.mark.parametrize(
    "module_name",
    [
        pytest.param("falcon_correlate"),
        pytest.param("falcon_correlate.celery"),
    ],
)
def test_package_and_celery_module_import_without_celery(
    tmp_path: pathlib.Path,
    module_name: str,
) -> None:
    """Package modules should import independently when Celery is unavailable."""
    result = _run_python_with_celery_blocked(
        tmp_path,
        os.environ,
        "-c",
        f"import importlib; importlib.import_module({module_name!r})",
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "module_name",
    [
        pytest.param("celery"),
        pytest.param("celery.signals"),
    ],
)
def test_celery_import_blocker_rejects_celery_modules(
    tmp_path: pathlib.Path,
    module_name: str,
) -> None:
    """The subprocess hook should block top-level and nested Celery imports."""
    result = _run_python_with_celery_blocked(
        tmp_path,
        os.environ,
        "-c",
        f"import importlib; importlib.import_module({module_name!r})",
    )

    blocked_name = module_name.split(".", maxsplit=1)[0]
    assert result.returncode != 0
    assert f"No module named '{blocked_name}'" in result.stderr


def test_celery_dependent_tests_skip_when_celery_is_unavailable(
    tmp_path: pathlib.Path,
) -> None:
    """Celery-only unit and BDD tests should match the skip snapshot."""
    sentinel_test = _write_child_sentinel_test(tmp_path)
    celery_test_paths = _discover_celery_test_paths()
    result = _run_python_with_celery_blocked(
        tmp_path,
        os.environ,
        "-m",
        "pytest",
        "-q",
        str(sentinel_test),
        *_relative_paths(celery_test_paths),
    )
    normalised_output = _normalise_pytest_output(result.stdout)
    expected_output = f""". [100%]
1 passed, {len(celery_test_paths)} skipped in <duration>"""

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert result.stderr == ""
    assert normalised_output == expected_output
