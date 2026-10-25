"""Contracts for the pull-request build and import check."""

from __future__ import annotations

import os
import subprocess  # ruff: ignore[suspicious-subprocess-import] - executes a checked-in workflow step.
import typing as typ

import pytest

from tests.workflow_contracts.workflow_documents import (
    WORKFLOWS_DIR,
    parse_workflow,
)

if typ.TYPE_CHECKING:
    from pathlib import Path

WORKFLOW_PATH = WORKFLOWS_DIR / "ci.yml"
WORKFLOW = parse_workflow(WORKFLOW_PATH.read_text(encoding="utf-8"), "ci.yml")
BUILD_JOB = WORKFLOW["jobs"]["build"]
ACTION_PATH = WORKFLOW_PATH.parents[1] / "actions" / "pure-python-wheel" / "action.yml"
ACTION = parse_workflow(
    ACTION_PATH.read_text(encoding="utf-8"), "pure-python-wheel/action.yml"
)


def _run_step(name: str) -> dict[str, object]:
    """Return a named run step from the CI build job."""
    return next(step for step in BUILD_JOB["steps"] if step.get("name") == name)


@pytest.mark.parametrize(
    ("sdist_count", "wheel_count", "expected_returncode"),
    [(0, 1, 1), (1, 1, 0), (2, 1, 1), (1, 0, 1), (1, 2, 1)],
    ids=[
        "missing-sdist",
        "exactly-one-of-each",
        "duplicate-sdist",
        "missing-wheel",
        "duplicate-wheel",
    ],
)
def test_build_check_requires_exactly_one_sdist(
    tmp_path: Path,
    sdist_count: int,
    wheel_count: int,
    expected_returncode: int,
) -> None:
    """The PR build refuses missing or duplicated distributions."""
    dist = tmp_path / "dist"
    dist.mkdir()
    for index in range(wheel_count):
        (dist / f"falcon_correlate-0.2.0-{index}.whl").touch()
    for index in range(sdist_count):
        (dist / f"falcon_correlate-0.2.0-{index}.tar.gz").touch()

    step = _run_step("Require exactly one sdist and one wheel")
    environment = os.environ.copy()
    environment["DIST_DIR"] = str(dist)
    result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - workflow run body is checked in.
        ["/usr/bin/bash", "-c", str(step["run"])],
        capture_output=True,
        check=False,
        env=environment,
        text=True,
    )

    assert result.returncode == expected_returncode, (
        f"expected exit {expected_returncode}, got {result.returncode}: {result.stderr}"
    )
    if expected_returncode != 0:
        expected_message = (
            "Expected exactly one source distribution."
            if sdist_count != 1
            else "Expected exactly one pure Python wheel."
        )
        assert expected_message in result.stderr, (
            "a rejected build must explain which distribution count was wrong"
        )


def test_import_check_excludes_optional_dependencies() -> None:
    """The clean wheel check imports the base package without either extra."""
    step = _run_step("Check the wheel imports without extras")
    script = str(step["run"])

    required_checks = (
        "import falcon_correlate",
        '"celery" not in sys.modules',
        '"httpx" not in sys.modules',
        "uv venv --clear",
    )
    missing_checks = [check for check in required_checks if check not in script]
    assert not missing_checks, (
        f"the clean import check is missing required statements: {missing_checks}"
    )


def test_build_job_is_a_read_only_pull_request_lane() -> None:
    """The build job runs on PRs with a bounded, least-privilege scope."""
    triggers = WORKFLOW.get("on", WORKFLOW.get(True))
    assert isinstance(triggers, dict), "CI must declare its trigger mapping"
    assert "pull_request" in triggers, "the build lane must run on pull requests"
    assert BUILD_JOB["permissions"] == {"contents": "read"}, (
        "the build lane must have read-only contents access"
    )
    assert type(BUILD_JOB["timeout-minutes"]) is int, (
        "the build lane must declare an integer timeout"
    )
    assert "if" not in BUILD_JOB, "the build lane must not use a job-level condition"


def test_build_action_uses_one_static_distribution_directory() -> None:
    """Keep the build destination and upload allowlist aligned at ``dist``."""
    steps = ACTION["runs"]["steps"]
    build_step = next(
        step for step in steps if step.get("name") == "Build sdist and wheel"
    )
    upload_step = next(
        step for step in steps if step.get("name") == "Upload sdist and wheel artefact"
    )

    assert build_step["env"] == {"OUT_DIR": "dist"}, (
        "the build action must use its statically checked artifact directory"
    )
    assert upload_step["with"]["path"].splitlines() == [
        "dist/*.whl",
        "dist/*.tar.gz",
    ], "the artifact upload must include both distributions from the build directory"
    assert "out-dir" not in ACTION["inputs"], (
        "the build action must not expose an output directory it cannot upload"
    )
