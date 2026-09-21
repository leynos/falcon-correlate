"""Contract tests for CI and Makefile tool-version synchronisation."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE_PATH = REPOSITORY_ROOT / "Makefile"
WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
PYPROJECT_PATH = REPOSITORY_ROOT / "pyproject.toml"
TOOL_NAMES = ("ruff", "ty", "mbake")
LINT_TOOLCHAIN_VARIABLES = (
    "PYLINT_PYPY_VERSION",
    "PYLINT_PYTHON_VERSION",
    "PYLINT_VERSION",
    "ASTROID_VERSION",
    "DF12_PYTHON",
    "DF12_PYTHON_LINTS_REF",
)


def _makefile_versions() -> dict[str, str]:
    """Return the pinned CLI tool versions from the Makefile."""
    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    versions = {
        name.lower(): version
        for name, version in re.findall(
            r"^(RUFF|TY|MBAKE)_VERSION \?= ([^\s]+)$", makefile, flags=re.MULTILINE
        )
    }
    assert set(versions) == set(TOOL_NAMES), (
        f"Makefile must pin exactly {TOOL_NAMES}, got {versions!r}"
    )
    return versions


def _ci_versions() -> dict[str, str]:
    """Return the pinned CLI tool versions from the CI lint job."""
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert isinstance(workflow, dict), "CI workflow must parse to a mapping"
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict), "CI workflow must declare jobs"
    lint_job = jobs.get("lint")
    assert isinstance(lint_job, dict), "CI workflow must declare a lint job"
    steps = lint_job.get("steps")
    assert isinstance(steps, list), "CI lint job must declare steps"
    install_step = next(
        (
            step
            for step in steps
            if isinstance(step, dict) and step.get("name") == "Install CLI tools"
        ),
        None,
    )
    assert isinstance(install_step, dict), "CI lint job must install CLI tools"
    command = install_step.get("run")
    assert isinstance(command, str), "CI tool installation step must run a command"
    versions = dict(re.findall(r"uv tool install (ruff|ty|mbake)==([^\s]+)", command))
    assert set(versions) == set(TOOL_NAMES), (
        f"CI must pin exactly {TOOL_NAMES}, got {versions!r}"
    )
    return versions


def test_ci_tool_versions_match_makefile() -> None:
    """CI uses the CLI tool versions pinned by the Makefile."""
    assert _ci_versions() == _makefile_versions(), (
        "CI tool versions must match the Makefile pins"
    )


def _makefile_lint_toolchain() -> dict[str, str]:
    """Return the Pylint toolchain pins from the Makefile."""
    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    pattern = "|".join(LINT_TOOLCHAIN_VARIABLES)
    versions = dict(
        re.findall(rf"^({pattern}) \?= ([^\s]+)$", makefile, flags=re.MULTILINE)
    )
    assert set(versions) == set(LINT_TOOLCHAIN_VARIABLES), (
        f"Makefile must pin exactly {LINT_TOOLCHAIN_VARIABLES}, got {versions!r}"
    )
    return versions


def _ci_lint_toolchain() -> dict[str, str]:
    """Return the Pylint toolchain pins from the CI lint-job environment."""
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert isinstance(workflow, dict), "CI workflow must parse to a mapping"
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict), "CI workflow must declare jobs"
    lint_job = jobs.get("lint")
    assert isinstance(lint_job, dict), "CI workflow must declare a lint job"
    environment = lint_job.get("env")
    assert isinstance(environment, dict), "CI lint job must define its environment"
    versions = {
        name: value
        for name in LINT_TOOLCHAIN_VARIABLES
        if isinstance(value := environment.get(name), str)
    }
    assert set(versions) == set(LINT_TOOLCHAIN_VARIABLES), (
        f"CI must pin exactly {LINT_TOOLCHAIN_VARIABLES}, got {versions!r}"
    )
    return versions


def _development_pylint_versions() -> dict[str, str]:
    """Return the explicit Pylint and Astroid development dependencies."""
    pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    dependencies = pyproject["dependency-groups"]["dev"]
    assert isinstance(dependencies, list), "Development dependencies must be a list"
    versions = {
        dependency.split("==", maxsplit=1)[0].upper() + "_VERSION": dependency.split(
            "==", maxsplit=1
        )[1]
        for dependency in dependencies
        if dependency.startswith(("pylint==", "astroid=="))
    }
    assert set(versions) == {"PYLINT_VERSION", "ASTROID_VERSION"}, (
        "Development dependencies must pin Pylint and Astroid"
    )
    return versions


def test_pylint_toolchain_pins_match_ci_and_dependencies() -> None:
    """Keep Pylint and interpreter pins consistent across lint entry points."""
    makefile = _makefile_lint_toolchain()
    assert _ci_lint_toolchain() == makefile, (
        "CI Pylint toolchain pins must match the Makefile"
    )
    assert _development_pylint_versions() == {
        name: makefile[name] for name in ("PYLINT_VERSION", "ASTROID_VERSION")
    }, "Development dependencies must match the Makefile Pylint and Astroid pins"
