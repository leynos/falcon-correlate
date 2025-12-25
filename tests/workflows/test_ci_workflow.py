"""Integration tests for CI workflow using act.

These tests validate the CI workflow locally using act before pushing to GitHub.
They are excluded from the normal test suite (via --ignore=tests/workflows in CI)
and should be run manually when making workflow changes.

Run with: pytest tests/workflows/ -v
"""

from __future__ import annotations

import dataclasses as dc
import json
import shutil
import subprocess
import typing as typ
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).parent.parent.parent
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _tool_is_available(tool_name: str, args: list[str]) -> bool:
    """Check if a tool is available by running it with given args."""
    tool_path = shutil.which(tool_name)
    if tool_path is None:
        return False
    result = subprocess.run(  # noqa: S603
        [tool_path, *args],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


# Check if act and Docker are available at module load time
ACT_AVAILABLE = _tool_is_available("act", ["--version"])
DOCKER_AVAILABLE = _tool_is_available("docker", ["info"])


@dc.dataclass(frozen=True)
class ActConfig:
    """Configuration for running act."""

    event: str
    job: str
    event_path: Path
    artifact_dir: Path
    matrix: dict[str, str] = dc.field(default_factory=dict)
    dry_run: bool = False


def run_act(config: ActConfig) -> tuple[int, Path, str]:
    """Run act with the specified configuration.

    Args:
        config: ActConfig instance with all settings.

    Returns:
        Tuple of (exit code, artifact directory, combined logs).

    """
    config.artifact_dir.mkdir(parents=True, exist_ok=True)

    act_path = shutil.which("act")
    if act_path is None:
        msg = "act executable not found in PATH"
        raise FileNotFoundError(msg)

    cmd = [
        act_path,
        config.event,
        "-j",
        config.job,
        "-e",
        str(config.event_path),
        "-P",
        "ubuntu-latest=catthehacker/ubuntu:act-latest",
        "--artifact-server-path",
        str(config.artifact_dir),
        "--json",
        "-b",
        "-W",
        str(WORKFLOW_PATH),
    ]

    for key, value in config.matrix.items():
        cmd.extend(["--matrix", f"{key}:{value}"])

    if config.dry_run:
        cmd.append("--list")

    completed = subprocess.run(  # noqa: S603
        cmd,
        text=True,
        capture_output=True,
        cwd=str(REPO_ROOT),
        check=False,
    )
    logs = completed.stdout + "\n" + completed.stderr
    return completed.returncode, config.artifact_dir, logs


def parse_json_logs(logs: str) -> list[dict[str, typ.Any]]:
    """Parse JSON log entries from act output.

    Args:
        logs: Raw log output from act.

    Returns:
        List of parsed JSON log entries.

    """
    entries = []
    for line in logs.splitlines():
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        try:
            entries.append(json.loads(stripped))
        except json.JSONDecodeError:
            continue
    return entries


def log_contains_message(logs: str, message: str) -> bool:
    """Check if any log entry contains the specified message.

    Args:
        logs: Raw log output from act.
        message: Message to search for.

    Returns:
        True if the message is found in any log entry.

    """
    for entry in parse_json_logs(logs):
        output = entry.get("Output") or entry.get("message") or ""
        if message in output:
            return True
    # Also check raw logs for non-JSON output
    return message in logs


@pytest.mark.skipif(
    not ACT_AVAILABLE,
    reason="act is not installed",
)
@pytest.mark.skipif(
    not DOCKER_AVAILABLE,
    reason="Docker is not available",
)
class TestCIWorkflowStructure:
    """Tests for CI workflow structure validation."""

    def test_workflow_file_exists(self) -> None:
        """Verify the CI workflow file exists."""
        assert WORKFLOW_PATH.exists(), f"Workflow not found at {WORKFLOW_PATH}"

    def test_workflow_lists_jobs(self, tmp_path: Path) -> None:
        """Verify act can parse and list the workflow jobs."""
        config = ActConfig(
            event="pull_request",
            job="lint",
            event_path=FIXTURES_DIR / "pull_request.event.json",
            artifact_dir=tmp_path / "act-artifacts",
            dry_run=True,
        )
        _code, _artdir, logs = run_act(config)
        # In dry-run mode, act returns 0 and lists jobs
        # The output should mention our jobs
        assert "lint" in logs.lower() or "test" in logs.lower(), (
            f"Expected job names in output:\n{logs}"
        )


@pytest.mark.skipif(
    not ACT_AVAILABLE,
    reason="act is not installed",
)
@pytest.mark.skipif(
    not DOCKER_AVAILABLE,
    reason="Docker is not available",
)
class TestCIWorkflowLintJob:
    """Tests for the lint job in the CI workflow."""

    @pytest.mark.slow
    def test_lint_job_runs_successfully(self, tmp_path: Path) -> None:
        """Verify the lint job completes without errors.

        This test runs the actual lint job which includes:
        - Makefile validation
        - Code formatting check
        - Ruff linting
        - Type checking
        """
        config = ActConfig(
            event="pull_request",
            job="lint",
            event_path=FIXTURES_DIR / "pull_request.event.json",
            artifact_dir=tmp_path / "act-artifacts",
        )
        code, _artdir, logs = run_act(config)
        assert code == 0, f"Lint job failed:\n{logs}"


@pytest.mark.skipif(
    not ACT_AVAILABLE,
    reason="act is not installed",
)
@pytest.mark.skipif(
    not DOCKER_AVAILABLE,
    reason="Docker is not available",
)
class TestCIWorkflowTestJob:
    """Tests for the test job in the CI workflow."""

    @pytest.mark.slow
    @pytest.mark.parametrize("python_version", ["3.12", "3.13", "3.14"])
    def test_test_job_runs_for_python_version(
        self,
        tmp_path: Path,
        python_version: str,
    ) -> None:
        """Verify the test job runs successfully for each Python version.

        Args:
            tmp_path: Pytest temporary directory fixture.
            python_version: Python version to test.

        """
        config = ActConfig(
            event="pull_request",
            job="test",
            event_path=FIXTURES_DIR / "pull_request.event.json",
            artifact_dir=tmp_path / "act-artifacts",
            matrix={"python-version": python_version},
        )
        code, _artdir, logs = run_act(config)
        assert code == 0, f"Test job failed for Python {python_version}:\n{logs}"

        # Verify Python version is mentioned in logs
        assert log_contains_message(logs, python_version), (
            f"Expected Python {python_version} in logs"
        )

    @pytest.mark.slow
    def test_test_job_produces_coverage_artifact(self, tmp_path: Path) -> None:
        """Verify the test job produces a coverage artifact."""
        config = ActConfig(
            event="pull_request",
            job="test",
            event_path=FIXTURES_DIR / "pull_request.event.json",
            artifact_dir=tmp_path / "act-artifacts",
            matrix={"python-version": "3.13"},
        )
        code, artdir, logs = run_act(config)
        assert code == 0, f"Test job failed:\n{logs}"

        # Check for coverage artifact
        coverage_files = list(artdir.rglob("coverage*.xml"))
        assert coverage_files, f"Coverage artifact missing. Logs:\n{logs}"


@pytest.mark.skipif(
    not ACT_AVAILABLE,
    reason="act is not installed",
)
@pytest.mark.skipif(
    not DOCKER_AVAILABLE,
    reason="Docker is not available",
)
class TestCIWorkflowMatrixConfiguration:
    """Tests for matrix configuration in the CI workflow."""

    def test_matrix_includes_all_python_versions(self) -> None:
        """Verify the workflow matrix includes Python 3.12, 3.13, and 3.14."""
        import yaml

        with WORKFLOW_PATH.open() as f:
            workflow = yaml.safe_load(f)

        test_job = workflow["jobs"]["test"]
        matrix = test_job["strategy"]["matrix"]
        python_versions = matrix["python-version"]

        expected_versions = ["3.12", "3.13", "3.14"]
        assert python_versions == expected_versions, (
            f"Expected {expected_versions}, got {python_versions}"
        )

    def test_matrix_fail_fast_is_disabled(self) -> None:
        """Verify fail-fast is disabled so all matrix jobs run."""
        import yaml

        with WORKFLOW_PATH.open() as f:
            workflow = yaml.safe_load(f)

        test_job = workflow["jobs"]["test"]
        strategy = test_job["strategy"]

        assert strategy.get("fail-fast") is False, (
            "fail-fast should be disabled for matrix testing"
        )

    def test_lint_job_uses_uv_for_python(self) -> None:
        """Verify the lint job uses uv to install Python."""
        import yaml

        with WORKFLOW_PATH.open() as f:
            workflow = yaml.safe_load(f)

        lint_job = workflow["jobs"]["lint"]
        steps = lint_job["steps"]

        # Find the Python setup step
        python_step = next(
            (s for s in steps if "Set up Python" in s.get("name", "")),
            None,
        )
        assert python_step is not None, "Python setup step not found"
        assert "uv python install" in python_step.get("run", ""), (
            "Expected uv python install in Python setup step"
        )

    def test_test_job_uses_uv_for_python(self) -> None:
        """Verify the test job uses uv to install Python."""
        import yaml

        with WORKFLOW_PATH.open() as f:
            workflow = yaml.safe_load(f)

        test_job = workflow["jobs"]["test"]
        steps = test_job["steps"]

        # Find the Python setup step
        python_step = next(
            (s for s in steps if "Set up Python" in s.get("name", "")),
            None,
        )
        assert python_step is not None, "Python setup step not found"
        assert "uv python install" in python_step.get("run", ""), (
            "Expected uv python install in Python setup step"
        )
        assert "${{ matrix.python-version }}" in python_step.get("run", ""), (
            "Expected matrix.python-version in Python setup step"
        )
