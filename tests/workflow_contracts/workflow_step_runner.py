"""Run named workflow scripts through Bash with their declared environment."""

from __future__ import annotations

import os
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import] - executes checked-in workflow scripts.
import tempfile
from pathlib import Path

import pytest

from tests.workflow_contracts.workflow_documents import (
    REPO_ROOT,
    WORKFLOWS_DIR,
    parse_workflow,
)


def _prioritize_recorders(environment: dict[str, str]) -> None:
    """Put any fixture-installed command recorders first on ``PATH``."""
    for variable, directory, executable in (
        ("GH_ARGV_PATH", "gh-bin", "gh"),
        ("CURL_ARGV_PATH", "curl-bin", "curl"),
    ):
        record_path = environment.get(variable)
        if record_path is None:
            continue
        recorder = Path(record_path).parent / directory / executable
        environment["PATH"] = os.pathsep.join((
            str(recorder.parent),
            environment["PATH"],
        ))
        if shutil.which(executable, path=environment["PATH"]) != str(recorder):
            pytest.fail(f"the {executable} recorder is not first on PATH")


def run_named_workflow_step(
    workflow_name: str, job_name: str, step_name: str
) -> subprocess.CompletedProcess[str]:
    """Execute one named ``run`` step with YAML and test environment values."""
    workflow_text = (WORKFLOWS_DIR / workflow_name).read_text(encoding="utf-8")
    workflow = parse_workflow(workflow_text, workflow_name)
    job = workflow["jobs"][job_name]
    step = next(item for item in job["steps"] if item.get("name") == step_name)
    script = step.get("run")
    if not isinstance(script, str):
        raise TypeError

    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("the checked-in workflow step requires Bash")

    environment: dict[str, str] = {}
    for scope in (workflow.get("env"), job.get("env"), step.get("env")):
        if isinstance(scope, dict):
            environment.update({key: str(value) for key, value in scope.items()})
    environment.update(os.environ)
    # Bash startup hooks can reorder PATH and bypass the recording commands.
    environment.pop("BASH_ENV", None)
    _prioritize_recorders(environment)
    with tempfile.TemporaryDirectory(prefix="workflow-step-") as output_directory:
        environment.setdefault(
            "GITHUB_OUTPUT", str(Path(output_directory) / "github-output")
        )
        return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - the workflow body is checked in.
            [bash, "-c", script],
            capture_output=True,
            check=False,
            cwd=REPO_ROOT,
            env=environment,
            text=True,
        )
