"""Deterministic contracts for workflow topology and CI setup."""

from __future__ import annotations

import pytest

from tests.workflow_contracts.triggers import trigger_names
from tests.workflow_contracts.workflow_documents import (
    jobs_of,
    parse_workflow,
    text_of,
    workflow_texts,
)

WORKFLOWS = {
    "ci.yml": ({"lint": set(), "test": set()}, {"push", "pull_request"}),
    "coverage-main.yml": ({"coverage-upload": set()}, {"push", "workflow_dispatch"}),
    "build-wheels.yml": ({"build": set()}, {"workflow_call"}),
    "release.yml": ({"pure-wheel": set(), "release": {"pure-wheel"}}, {"push"}),
    "mutation-testing.yml": ({"mutation": set()}, {"schedule", "workflow_dispatch"}),
    "dependabot-automerge.yml": (
        {"automerge": set()},
        {"pull_request_target", "workflow_dispatch"},
    ),
}


def test_workflow_inventory() -> None:
    """Every workflow must have an explicitly reviewed structure."""
    assert set(workflow_texts()) == set(WORKFLOWS), (
        "Workflow inventory must match the reviewed table"
    )


@pytest.mark.parametrize("workflow", sorted(WORKFLOWS), ids=str)
def test_workflow_topology(workflow: str) -> None:
    """Jobs, dependencies and triggers match the reviewed topology."""
    text = text_of(workflow_texts(), workflow)
    jobs = jobs_of(text, workflow)
    expected_jobs, expected_triggers = WORKFLOWS[workflow]
    assert set(jobs) == set(expected_jobs), (
        "Workflow jobs must match the reviewed table"
    )
    for name, expected_needs in expected_jobs.items():
        needs = jobs[name].get("needs", [])
        assert isinstance(needs, (str, list)), f"{workflow}:{name} has invalid needs"
        assert set([needs] if isinstance(needs, str) else needs) == expected_needs, (
            "Job dependencies must match the reviewed table"
        )
    assert (
        trigger_names(parse_workflow(text, workflow), workflow) == expected_triggers
    ), "Workflow triggers must match the reviewed table"


@pytest.mark.parametrize(
    ("workflow", "filters"),
    [
        ("ci.yml", {"branches": ["main"]}),
        ("coverage-main.yml", {"branches": ["main"]}),
        ("release.yml", {"tags": ["v*.*.*"]}),
    ],
    ids=str,
)
def test_push_filters(workflow: str, filters: dict[str, list[str]]) -> None:
    """Push triggers target only the intended branches or tags."""
    document = parse_workflow(text_of(workflow_texts(), workflow), workflow)
    trigger_names(document, workflow)
    triggers = document.get("on", document.get(True))
    assert isinstance(triggers, dict), "Push triggers must be a mapping"
    assert triggers.get("push") == filters, "Push filters must match the reviewed table"


def _workflow_step(job: dict, job_name: str, step_name: str) -> dict:
    """Return the unique named step in a job."""
    steps = job.get("steps")
    assert isinstance(steps, list), f"{job_name} steps must be a list"
    matches = [
        step
        for step in steps
        if isinstance(step, dict)
        and isinstance(step.get("name"), str)
        and step_name in step["name"]
    ]
    assert len(matches) == 1, (
        f"expected one {step_name!r} step in {job_name!r}, found {len(matches)}"
    )
    return matches[0]


def test_ci_matrix() -> None:
    """CI tests all supported Python versions even if one fails."""
    jobs = jobs_of(text_of(workflow_texts(), "ci.yml"), "ci.yml")
    strategy = jobs["test"]["strategy"]
    assert strategy["matrix"]["python-version"] == ["3.12", "3.13", "3.14"], (
        "CI Python matrix must match supported versions"
    )
    assert strategy.get("fail-fast") is False, "CI matrix must disable fail-fast"


@pytest.mark.parametrize("job_name", ["lint", "test"], ids=str)
def test_ci_python_setup(job_name: str) -> None:
    """Both CI jobs install Python with uv, using the matrix for tests."""
    jobs = jobs_of(text_of(workflow_texts(), "ci.yml"), "ci.yml")
    run = _workflow_step(jobs[job_name], job_name, "Set up Python").get("run")
    assert isinstance(run, str), "Python setup must contain a run command"
    assert "uv python install" in run, "Python setup must install using uv"
    if job_name == "test":
        assert "${{ matrix.python-version }}" in run, (
            "Test Python setup must use the matrix version"
        )
