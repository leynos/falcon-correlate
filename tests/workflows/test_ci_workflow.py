"""Integration tests for CI workflow using act.

These tests validate the CI workflow locally using act before pushing to GitHub.
They are excluded from the normal test suite (via --ignore=tests/workflows in CI)
and should be run manually when making workflow changes.

Run with: pytest tests/workflows/ -v
"""

from __future__ import annotations

import json
import typing as typ
from pathlib import Path

import pytest

from tests.workflows.act_runner import WORKFLOW_PATH, ActConfig, run_act

FIXTURES_DIR = Path(__file__).parent / "fixtures"


pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("act_available", "docker_available"),
]


def parse_json_logs(logs: str) -> list[dict[str, typ.Any]]:
    """Parse JSON log entries from act output.

    Args:
        logs: Raw log output from act.

    Returns
    -------
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

    Returns
    -------
        True if the message is found in any log entry.

    """
    for entry in parse_json_logs(logs):
        output = entry.get("Output") or entry.get("message") or ""
        if message in output:
            return True
    # Also check raw logs for non-JSON output
    return message in logs


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
            artefact_dir=tmp_path / "act-artefacts",
            dry_run=True,
        )
        _code, _artdir, logs = run_act(config)
        # In dry-run mode, act returns 0 and lists jobs
        # The output should mention our jobs
        assert "lint" in logs.lower() or "test" in logs.lower(), (
            f"Expected job names in output:\n{logs}"
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
        - Markdown linting and Oxford spelling checks
        - Mermaid diagram validation
        """
        config = ActConfig(
            event="pull_request",
            job="lint",
            event_path=FIXTURES_DIR / "pull_request.event.json",
            artefact_dir=tmp_path / "act-artefacts",
        )
        code, _artdir, logs = run_act(config)
        assert code == 0, f"Lint job failed:\n{logs}"


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
            artefact_dir=tmp_path / "act-artefacts",
            matrix={"python-version": python_version},
        )
        code, _artdir, logs = run_act(config)
        assert code == 0, f"Test job failed for Python {python_version}:\n{logs}"

        # Verify Python version is mentioned in logs
        assert log_contains_message(logs, python_version), (
            f"Expected Python {python_version} in logs"
        )

    @pytest.mark.slow
    def test_test_job_produces_coverage_artefact(self, tmp_path: Path) -> None:
        """Verify the test job produces a coverage artefact."""
        config = ActConfig(
            event="pull_request",
            job="test",
            event_path=FIXTURES_DIR / "pull_request.event.json",
            artefact_dir=tmp_path / "act-artefacts",
            matrix={"python-version": "3.13"},
        )
        code, artdir, logs = run_act(config)
        assert code == 0, f"Test job failed:\n{logs}"

        # Check for coverage artefact
        coverage_files = list(artdir.rglob("coverage*.xml"))
        assert coverage_files, f"Coverage artefact missing. Logs:\n{logs}"
