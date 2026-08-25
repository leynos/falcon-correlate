"""Contract tests for CI and Makefile tool-version synchronisation."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE_PATH = REPOSITORY_ROOT / "Makefile"
WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
TOOL_NAMES = ("ruff", "ty")


def _makefile_versions() -> dict[str, str]:
    """Return the pinned Ruff and Ty versions from the Makefile."""
    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    versions = {
        name.lower(): version
        for name, version in re.findall(
            r"^(RUFF|TY)_VERSION \?= ([^\s]+)$", makefile, flags=re.MULTILINE
        )
    }
    assert set(versions) == set(TOOL_NAMES), (
        f"Makefile must pin exactly {TOOL_NAMES}, got {versions!r}"
    )
    return versions


def _ci_versions() -> dict[str, str]:
    """Return the pinned Ruff and Ty versions from the CI lint job."""
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
    versions = dict(re.findall(r"uv tool install (ruff|ty)==([^\s]+)", command))
    assert set(versions) == set(TOOL_NAMES), (
        f"CI must pin exactly {TOOL_NAMES}, got {versions!r}"
    )
    return versions


def test_ci_tool_versions_match_makefile() -> None:
    """CI uses the Ruff and Ty versions pinned by the Makefile."""
    assert _ci_versions() == _makefile_versions(), (
        "CI Ruff and Ty versions must match the Makefile pins"
    )
