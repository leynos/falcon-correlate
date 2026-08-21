"""Contract tests for the blocking Skylos dead-code lint gate."""

from __future__ import annotations

import shutil
import subprocess  # noqa: S404 - this contract test executes Make without a shell.
import tomllib
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_skylos_configuration_is_strict_and_has_an_empty_allow_list() -> None:
    """Keep the initial Skylos policy strict and ready for documented exceptions."""
    config = tomllib.loads(
        (_PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    skylos = config["tool"]["skylos"]

    assert skylos["gate"]["strict"] is True
    assert skylos["whitelist"]["names"] == []
    assert skylos["whitelist"]["documented"] == {}


def test_make_lint_runs_a_local_blocking_skylos_scan() -> None:
    """Keep the Skylos invocation deterministic and non-interactive."""
    make_executable = shutil.which("make")
    assert make_executable is not None, "Expected make to be available."

    result = subprocess.run(  # noqa: S603 - this test executes Make without a shell.
        [make_executable, "--no-print-directory", "--dry-run", "lint"],
        cwd=_PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.count("skylos --config-file pyproject.toml") == 1
    command = " ".join(result.stdout.splitlines()).replace("\\", "")
    assert "src/falcon_correlate --exclude unittests" in command
    required_arguments = (
        "--category",
        "dead_code",
        "--gate",
        "--format",
        "concise",
        "--no-upload",
        "--no-provenance",
        "--no-grep-verify",
    )
    assert all(argument in command.split() for argument in required_arguments)


def test_skylos_allow_requires_a_name_and_reason() -> None:
    """Keep named Skylos exceptions documented and narrow."""
    makefile = (_PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")

    assert "skylos-allow: ## Document one named Skylos exception" in makefile
    assert "SKYLOS_NAME = $(value NAME)" in makefile
    assert "SKYLOS_REASON = $(value REASON)" in makefile
    assert 'whitelist "$${SKYLOS_NAME}" --reason "$${SKYLOS_REASON}"' in makefile
