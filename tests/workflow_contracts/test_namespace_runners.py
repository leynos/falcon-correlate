"""Contract tests for Falcon Correlate's Namespace runner assignments.

The workflows are repository-owned infrastructure rather than application code.
These tests parse their declarative configuration and inspect the dry-run
``make`` recipe so a valid-but-wrong GitHub-hosted runner, a missing actionlint
label, or a direct ``ty`` invocation fails the normal test gate.
"""

from __future__ import annotations

import shutil
import subprocess  # noqa: S404 - this test deliberately validates the Makefile CLI boundary.
import typing as typ
from pathlib import Path
from types import MappingProxyType

import yaml

if typ.TYPE_CHECKING:
    import collections.abc as cabc

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIRECTORY = REPOSITORY_ROOT / ".github" / "workflows"
NAMESPACE_RUNNER = "namespace-profile-default"
MIGRATED_JOBS: typ.Final[cabc.Mapping[str, tuple[str, ...]]] = MappingProxyType({
    "ci.yml": ("lint", "test"),
    "coverage-main.yml": ("coverage-upload",),
    "get-codescene-sha.yml": ("refresh-sha",),
    "release.yml": ("pure-wheel", "release"),
})


def _as_mapping(value: object, message: str) -> dict[object, object]:
    """Assert ``value`` is a mapping and narrow its static type."""
    assert isinstance(value, dict), message
    return typ.cast("dict[object, object]", value)


def _workflow_jobs(filename: str) -> dict[object, object]:
    """Return the parsed jobs mapping for one repository-owned workflow."""
    workflow_path = WORKFLOWS_DIRECTORY / filename
    workflow = _as_mapping(
        yaml.safe_load(workflow_path.read_text(encoding="utf-8")),
        f"{filename} must parse to a mapping",
    )
    return _as_mapping(workflow.get("jobs"), f"{filename} must declare jobs")


def test_migrated_jobs_use_the_shared_namespace_runner() -> None:
    """Keep every migrated repository-owned Linux job on Namespace."""
    for filename, job_names in MIGRATED_JOBS.items():
        jobs = _workflow_jobs(filename)
        for job_name in job_names:
            job = _as_mapping(jobs.get(job_name), f"{filename} must declare {job_name}")
            assert job.get("runs-on") == NAMESPACE_RUNNER, (
                f"{filename}:{job_name} must run on {NAMESPACE_RUNNER!r}, "
                f"got {job.get('runs-on')!r}"
            )


def test_wheel_matrix_keeps_its_caller_selected_runner() -> None:
    """Keep native wheel builds on their matrix-selected hosted platforms."""
    jobs = _workflow_jobs("build-wheels.yml")
    build = _as_mapping(jobs.get("build"), "build-wheels.yml must declare build")
    assert build.get("runs-on") == "${{ matrix.os }}", (
        "build-wheels.yml:build must retain its caller-selected "
        f"matrix runner, got {build.get('runs-on')!r}"
    )


def test_actionlint_knows_namespace_runner_labels() -> None:
    """Keep actionlint aware of both shared Namespace labels."""
    config_path = REPOSITORY_ROOT / ".github" / "actionlint.yaml"
    config = _as_mapping(
        yaml.safe_load(config_path.read_text(encoding="utf-8")),
        "actionlint configuration must parse to a mapping",
    )
    self_hosted = _as_mapping(
        config.get("self-hosted-runner"),
        "actionlint configuration must declare self-hosted runner labels",
    )
    labels = self_hosted.get("labels")
    assert labels == [NAMESPACE_RUNNER, f"{NAMESPACE_RUNNER}-arm64"], (
        "actionlint must recognise the default and ARM64 Namespace labels, "
        f"got {labels!r}"
    )


def test_typecheck_uses_the_configured_uv_environment() -> None:
    """Run both ty commands through the Makefile's injected UV environment."""
    make_path = shutil.which("make")
    assert make_path is not None, "make must be available to inspect its dry-run recipe"
    completed = subprocess.run(  # noqa: S603
        [
            make_path,
            "--no-print-directory",
            "--dry-run",
            "UV_ENV=CONTRACT_UV_ENV",
            "UV=contract-uv",
            "typecheck",
        ],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    command_output = completed.stdout
    assert "CONTRACT_UV_ENV contract-uv run ty --version" in command_output
    assert "CONTRACT_UV_ENV contract-uv run ty check" in command_output
