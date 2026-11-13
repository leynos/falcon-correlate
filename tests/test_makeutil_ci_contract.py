"""Contract test for how CI jobs and ``make test`` provision the Makefile parser.

Makeutil parses the Makefile into structured rules, so the Makefile contract
tests assert the interface without relying on whitespace or nearby source text.
Every full-suite CI job installs the same pinned revision with the pinned
nightly toolchain.
"""

from __future__ import annotations

import json
import shlex
import subprocess  # ruff: ignore[suspicious-subprocess-import] - contracts invoke a fixed local executable.
import typing as typ
from pathlib import Path

import yaml

_MAKEUTIL_COMMAND: typ.Final = ("makeutil", "parse", "Makefile")
_MAKEUTIL_REVISION: typ.Final = "29fc5a1634ffbaa18a773eed9dff1b2838a45d9c"
_MAKEUTIL_TOOLCHAIN: typ.Final = "nightly-2026-05-28"
_MAKEUTIL_INSTALL_TOKENS: typ.Final = (
    "rustup",
    "toolchain",
    "install",
    "${MAKEUTIL_TOOLCHAIN}",
    "--profile",
    "minimal",
    "RUSTFLAGS=-Zpolonius=next",
    "cargo",
    "+${MAKEUTIL_TOOLCHAIN}",
    "install",
    "--git",
    "https://github.com/leynos/makeutil",
    "--rev",
    "${MAKEUTIL_REVISION}",
    "--locked",
    "--force",
    "makeutil",
)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _makefile_report() -> dict[str, object]:
    """Return Makeutil's complete, successfully parsed Makefile report."""
    completed = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - fixed parser command.
        _MAKEUTIL_COMMAND,
        capture_output=True,
        check=True,
        cwd=_PROJECT_ROOT,
        text=True,
    )
    report = typ.cast("dict[str, object]", json.loads(completed.stdout))
    parse = _mapping(report.get("parse"), subject="parse report")
    assert parse.get("status") == "complete", (
        f"makeutil did not complete the Makefile parse: {parse!r}"
    )
    return report


def _mapping(value: object, *, subject: str) -> dict[str, object]:
    """Return a JSON object, naming the unexpected `subject` on failure."""
    assert isinstance(value, dict), f"expected {subject} to be a JSON object"
    return typ.cast("dict[str, object]", value)


def _objects(value: object, *, subject: str) -> list[dict[str, object]]:
    """Return a JSON object array, naming the unexpected `subject` on failure."""
    assert isinstance(value, list), f"expected {subject} to be a JSON array"
    return [_mapping(item, subject=f"{subject} item") for item in value]


def _text_sequence(value: object, *, subject: str) -> tuple[str, ...]:
    """Return a JSON string array, naming the unexpected `subject` on failure."""
    assert isinstance(value, list), f"expected {subject} to be a JSON array"
    assert all(isinstance(item, str) for item in value), (
        f"expected {subject} to contain only JSON strings"
    )
    return tuple(typ.cast("list[str]", value))


def _sole_recipe_rule(target: str) -> dict[str, object]:
    """Return the only parsed rule for `target` that has recipes."""
    rules = _objects(_makefile_report().get("rules"), subject="rules")
    matches = [
        rule
        for rule in rules
        if target in _text_sequence(rule.get("targets"), subject="rule targets")
        and _objects(rule.get("recipes"), subject="rule recipes")
    ]
    assert len(matches) == 1, (
        f"expected one recipe-bearing Makefile rule named {target!r}, found "
        f"{len(matches)}"
    )
    return matches[0]


def _workflow_job(workflow_path: str, job_name: str) -> dict[str, object]:
    """Return `job_name` from a repository workflow."""
    workflow = yaml.safe_load((_PROJECT_ROOT / workflow_path).read_text())
    workflow_mapping = _mapping(workflow, subject=f"{workflow_path} workflow")
    jobs = _mapping(workflow_mapping.get("jobs"), subject=f"{workflow_path} jobs")
    return _mapping(jobs.get(job_name), subject=f"{workflow_path} job {job_name!r}")


def _sole_workflow_step(
    job_name: str,
    step_name: str,
    *,
    workflow_path: str = ".github/workflows/ci.yml",
) -> dict[str, object]:
    """Return the sole named workflow step from `job_name`."""
    steps = _objects(
        _workflow_job(workflow_path, job_name).get("steps"),
        subject=f"{workflow_path} job {job_name!r} steps",
    )
    matches = [step for step in steps if step.get("name") == step_name]
    assert len(matches) == 1, (
        f"expected one {step_name!r} step in {workflow_path} job {job_name!r}, "
        f"found {len(matches)}"
    )
    return matches[0]


def _assert_makeutil_installation(command: object, *, contract: str) -> None:
    """Assert that `command` installs the pinned Makeutil parser."""
    assert isinstance(command, str), (
        f"{contract} must provide a Makeutil installation shell command"
    )
    assert (
        tuple(shlex.split(command.replace("\\\n", ""))) == _MAKEUTIL_INSTALL_TOKENS
    ), f"{contract} must pin the Makeutil installation command"


def test_ci_runs_lint_and_installs_makeutil_for_full_suites() -> None:
    """CI must share lint and Makeutil contracts with local contributor gates."""
    lint_step = _sole_workflow_step("lint", "Run lint gates")
    assert lint_step.get("run") == "make lint", (
        "CI lint-step contract must invoke the shared make lint target"
    )
    test_rule = _sole_recipe_rule("test")
    prerequisites = _text_sequence(
        test_rule.get("prerequisites"), subject="test prerequisites"
    )
    assert "makeutil" in prerequisites, (
        "make test must require Makeutil before its Makefile contract tests run"
    )

    for workflow_path, job_name in (
        (".github/workflows/ci.yml", "test"),
        (".github/workflows/coverage-main.yml", "coverage-upload"),
    ):
        job = _workflow_job(workflow_path, job_name)
        environment = _mapping(
            job.get("env"), subject=f"{workflow_path} Makeutil environment"
        )
        assert environment.get("MAKEUTIL_REVISION") == _MAKEUTIL_REVISION, (
            f"{workflow_path} Makeutil revision contract must stay pinned"
        )
        assert environment.get("MAKEUTIL_TOOLCHAIN") == _MAKEUTIL_TOOLCHAIN, (
            f"{workflow_path} Makeutil toolchain contract must stay pinned"
        )
        parser_step = _sole_workflow_step(
            job_name, "Install Makefile parser", workflow_path=workflow_path
        )
        _assert_makeutil_installation(
            parser_step.get("run"),
            contract=f"{workflow_path} Makeutil-install contract",
        )
