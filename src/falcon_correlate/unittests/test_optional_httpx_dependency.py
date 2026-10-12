"""Validate package imports when the optional HTTPX dependency is absent."""

from __future__ import annotations

import os
import subprocess  # ruff: ignore[suspicious-subprocess-import] -- subprocess isolates import availability.
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_HTTPX_BLOCKED_IMPORT_TIMEOUT_SECONDS = 120
_PYTEST_ENVIRONMENT_PREFIX = "PYTEST_"
_HTTPX_IMPORT_BLOCKER = """
import importlib.abc
import importlib.machinery
import sys


class _BlockHttpxFinder(importlib.abc.MetaPathFinder):
    def find_spec(
        self,
        fullname: str,
        path: object | None,
        target: object | None = None,
    ) -> importlib.machinery.ModuleSpec | None:
        if fullname == "httpx" or fullname.startswith("httpx."):
            raise ModuleNotFoundError("No module named 'httpx'", name=fullname)
        return None


sys.meta_path.insert(0, _BlockHttpxFinder())
"""

pytestmark = pytest.mark.timeout(_HTTPX_BLOCKED_IMPORT_TIMEOUT_SECONDS)


def _run_python_with_httpx_blocked(
    code: str,
) -> subprocess.CompletedProcess[str]:
    """Run a Python child process with HTTPX imports blocked."""
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(_PYTEST_ENVIRONMENT_PREFIX)
    }
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed child interpreter and script.
        [sys.executable, "-c", f"{_HTTPX_IMPORT_BLOCKER}\n{code}"],
        check=False,
        cwd=_PROJECT_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        timeout=_HTTPX_BLOCKED_IMPORT_TIMEOUT_SECONDS,
    )


@pytest.mark.parametrize(
    "module_name",
    [
        pytest.param("falcon_correlate", id="package-root"),
        pytest.param("falcon_correlate.httpx", id="httpx-adapter"),
    ],
)
def test_package_modules_import_without_httpx(module_name: str) -> None:
    """Package entry points should load without the optional HTTPX package."""
    result = _run_python_with_httpx_blocked(
        f"import importlib; importlib.import_module({module_name!r})",
    )

    assert result.returncode == 0, (
        f"{module_name} should import when HTTPX is unavailable.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_httpx_import_blocker_rejects_httpx() -> None:
    """The subprocess import hook should make HTTPX unavailable."""
    result = _run_python_with_httpx_blocked("import httpx")

    assert result.returncode != 0, "HTTPX should fail to import under the blocker."
    assert "No module named 'httpx'" in result.stderr, (
        "HTTPX should fail with a missing-dependency error."
    )
