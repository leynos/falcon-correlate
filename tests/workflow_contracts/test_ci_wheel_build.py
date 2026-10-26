"""Contracts for the pull-request build and import check."""

from __future__ import annotations

import os
import shutil
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
ACTION_PATH = WORKFLOW_PATH.parents[1] / "actions" / "pure-python-wheel" / "action.yml"


@pytest.fixture(scope="module")
def workflow() -> dict[str, typ.Any]:
    """Read CI workflow YAML when the tests need its parsed structure."""
    return parse_workflow(WORKFLOW_PATH.read_text(encoding="utf-8"), "ci.yml")


@pytest.fixture(scope="module")
def build_job(workflow: dict[str, typ.Any]) -> dict[str, typ.Any]:
    """Return the CI build job from the parsed workflow fixture."""
    return workflow["jobs"]["build"]


@pytest.fixture(scope="module")
def action() -> dict[str, typ.Any]:
    """Read the pure-Python composite action when its contract is needed."""
    return parse_workflow(
        ACTION_PATH.read_text(encoding="utf-8"), "pure-python-wheel/action.yml"
    )


def _run_step(build_job: dict[str, typ.Any], name: str) -> dict[str, typ.Any]:
    """Return a named run step from the CI build job."""
    return next(step for step in build_job["steps"] if step.get("name") == name)


def _run_build_verification(
    dist: Path, build_job: dict[str, typ.Any]
) -> subprocess.CompletedProcess[str]:
    """Execute the checked-in distribution verification step."""
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("the checked-in workflow step requires Bash")
    step = _run_step(build_job, "Require exactly one sdist and one wheel")
    environment = os.environ.copy()
    environment["DIST_DIR"] = str(dist)
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - workflow run body is checked in.
        [bash, "-c", str(step["run"])],
        capture_output=True,
        check=False,
        env=environment,
        text=True,
    )


@pytest.mark.parametrize(
    ("distribution_counts", "expected_returncode"),
    [((0, 1), 1), ((1, 1), 0), ((2, 1), 1), ((1, 0), 1), ((1, 2), 1)],
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
    build_job: dict[str, typ.Any],
    distribution_counts: tuple[int, int],
    expected_returncode: int,
) -> None:
    """The PR build refuses missing or duplicated distributions."""
    sdist_count, wheel_count = distribution_counts
    dist = tmp_path / "dist"
    dist.mkdir()
    wheel_names = (
        "falcon_correlate-0.2.0-py3-none-any.whl",
        "falcon_correlate-0.2.0-cp313-cp313-manylinux_2_28_x86_64.whl",
    )
    for name in wheel_names[:wheel_count]:
        (dist / name).touch()
    for index in range(sdist_count):
        (dist / f"falcon_correlate-0.2.0-{index}.tar.gz").touch()

    result = _run_build_verification(dist, build_job)

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


def test_build_check_rejects_platform_specific_wheels(
    tmp_path: Path, build_job: dict[str, typ.Any]
) -> None:
    """The pure-Python lane refuses a wheel tied to one operating system."""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "falcon_correlate-0.2.0.tar.gz").touch()
    (dist / "falcon_correlate-0.2.0-cp313-cp313-manylinux_2_28_x86_64.whl").touch()

    result = _run_build_verification(dist, build_job)

    assert result.returncode == 1, "a platform-specific wheel must be rejected"
    assert (
        "Expected a platform-independent wheel with a none-any tag." in result.stderr
    ), "the rejection must identify the missing pure-Python compatibility tag"


def test_import_check_excludes_optional_dependencies(
    build_job: dict[str, typ.Any],
) -> None:
    """The clean wheel check imports the base package without either extra."""
    step = _run_step(build_job, "Check the wheel imports without extras")
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


def test_build_job_is_a_read_only_pull_request_lane(
    workflow: dict[str, typ.Any], build_job: dict[str, typ.Any]
) -> None:
    """The build job runs on PRs with a bounded, least-privilege scope."""
    triggers = workflow.get("on", workflow.get(True))
    assert isinstance(triggers, dict), "CI must declare its trigger mapping"
    assert "pull_request" in triggers, "the build lane must run on pull requests"
    assert build_job["permissions"] == {"contents": "read"}, (
        "the build lane must have read-only contents access"
    )
    assert type(build_job["timeout-minutes"]) is int, (
        "the build lane must declare an integer timeout"
    )
    assert "if" not in build_job, "the build lane must not use a job-level condition"


def test_build_action_uses_one_static_distribution_directory(
    action: dict[str, typ.Any],
) -> None:
    """Keep the build destination and upload allowlist aligned at ``dist``."""
    steps = action["runs"]["steps"]
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
    assert "out-dir" not in action["inputs"], (
        "the build action must not expose an output directory it cannot upload"
    )
