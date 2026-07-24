"""Contract tests for the mutation-testing caller workflow.

The executable logic lives in the ``leynos/shared-actions`` reusable
workflow, which carries its own unit and integration tests;
falcon-correlate's caller is declarative configuration. These tests
parse the caller with PyYAML and assert the contract it must uphold, so
drift (repointing the pin at a branch, widening permissions, or adding
undocumented inputs) fails CI on the pull request rather than surfacing
in a scheduled or manual run. The caller must reference the correct
reusable workflow at a commit SHA; Dependabot owns the SHA value, so
these tests assert the shape of the pin, not which commit it names.
"""

from __future__ import annotations

import re
import typing as typ
from pathlib import Path

import yaml

WORKFLOW_PATH = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "mutation-testing.yml"
)

USES_RE = re.compile(
    r"^leynos/shared-actions/\.github/workflows/mutation-mutmut\.yml@[0-9a-f]{40}$"
)


def _as_mapping(value: object, message: str) -> dict[object, object]:
    """Assert ``value`` is a mapping and narrow its static type."""
    assert isinstance(value, dict), message
    return typ.cast("dict[object, object]", value)


def _load() -> dict[object, object]:
    """Parse the workflow file."""
    return _as_mapping(
        yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8")),
        "the workflow must parse to a mapping",
    )


def _triggers(workflow: dict[object, object]) -> dict[object, object]:
    """Return the workflow trigger mapping."""
    triggers = workflow.get("on", workflow.get(True))
    return _as_mapping(triggers, "the workflow must declare an on: mapping")


def _mutation_job(workflow: dict[object, object]) -> dict[object, object]:
    """Return the single calling job."""
    jobs = _as_mapping(workflow.get("jobs"), "the workflow must declare a jobs mapping")
    assert jobs, "the workflow must declare at least one job"
    assert list(jobs) == ["mutation"], (
        f"expected a single job named 'mutation', found {list(jobs)}"
    )
    return _as_mapping(jobs["mutation"], "jobs.mutation must be a mapping")


def test_uses_reference_is_pinned_to_a_commit_sha() -> None:
    """The job must call mutation-mutmut.yml pinned to a 40-hex commit SHA.

    The exact SHA is not asserted: Dependabot owns bumping it, and a
    lockstep assertion here would fail every bump PR until a human
    hand-edited the pin.
    """
    uses = _mutation_job(_load()).get("uses")
    assert isinstance(uses, str), "jobs.mutation.uses is missing"
    assert USES_RE.match(uses), (
        f"jobs.mutation.uses must reference mutation-mutmut.yml pinned to "
        f"a full 40-character lowercase hex commit SHA (not a branch or "
        f"tag), got {uses!r}"
    )


def test_job_permissions_are_exactly_least_privilege() -> None:
    """The job grants contents: read and id-token: write, nothing broader."""
    permissions = _mutation_job(_load()).get("permissions")
    assert permissions == {"contents": "read", "id-token": "write"}, (
        "jobs.mutation.permissions must be exactly "
        f"{{'contents': 'read', 'id-token': 'write'}}, got {permissions!r}"
    )


def test_workflow_default_permissions_are_empty() -> None:
    """The workflow-level default token scope is empty."""
    workflow = _load()
    assert workflow.get("permissions") == {}, (
        f"top-level permissions must be an empty mapping, got "
        f"{workflow.get('permissions')!r}"
    )


def test_concurrency_serializes_per_ref_without_cancelling() -> None:
    """Runs queue per ref instead of cancelling one another."""
    concurrency = _as_mapping(
        _load().get("concurrency"), "the workflow must declare concurrency"
    )
    assert concurrency.get("group") == "mutation-testing-${{ github.ref }}", (
        f"concurrency.group must key on the triggering ref, got "
        f"{concurrency.get('group')!r}"
    )
    assert concurrency.get("cancel-in-progress") is False, (
        f"concurrency.cancel-in-progress must be false, got "
        f"{concurrency.get('cancel-in-progress')!r}"
    )


def test_triggers_keep_schedule_and_plain_dispatch() -> None:
    """The daily schedule stays; dispatch declares no inputs."""
    triggers = _triggers(_load())
    schedule = triggers.get("schedule")
    assert schedule == [{"cron": "5 6 * * *"}], (
        f"on.schedule must be the daily 06:05 UTC cron, got {schedule!r}"
    )
    assert "workflow_dispatch" in triggers, "on.workflow_dispatch is missing"
    dispatch = _as_mapping(
        triggers.get("workflow_dispatch") or {},
        "on.workflow_dispatch must be a mapping",
    )
    inputs = dispatch.get("inputs")
    assert not inputs, (
        "on.workflow_dispatch must not declare inputs; the Actions "
        "run-workflow control selects the ref"
    )


def test_with_block_is_absent_so_shared_defaults_apply() -> None:
    """The caller passes no inputs; the shared defaults fit this repo.

    ``paths`` defaults to ``src/`` and ``module-prefix-strip`` defaults
    to ``src/``, both of which match the src-layout package at
    ``src/falcon_correlate/``.
    """
    job = _mutation_job(_load())
    assert "with" not in job, (
        f"jobs.mutation must not pass inputs (shared defaults apply), got "
        f"{job.get('with')!r}"
    )
