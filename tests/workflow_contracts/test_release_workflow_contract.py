"""Structural contracts for the attested release workflow."""

from __future__ import annotations

import re
import typing as typ

import pytest

from tests.workflow_contracts.workflow_documents import (
    REPO_ROOT,
    WORKFLOWS_DIR,
    parse_workflow,
)

_RELEASE_PATH = WORKFLOWS_DIR / "release.yml"
_CI_PATH = WORKFLOWS_DIR / "ci.yml"
_ACTION_PATH = REPO_ROOT / ".github" / "actions" / "pure-python-wheel" / "action.yml"
_RELEASE_JOB_NAMES = {
    "attest",
    "check-version",
    "draft-release",
    "publish-pypi",
    "publish-release",
    "pure-wheel",
}
_EXPECTED_NEEDS = {
    "check-version": set(),
    "pure-wheel": set(),
    "attest": {"check-version", "pure-wheel"},
    "publish-pypi": {"check-version", "attest"},
    "draft-release": {"check-version", "attest"},
    "publish-release": {
        "check-version",
        "attest",
        "publish-pypi",
        "draft-release",
    },
}
_EXPECTED_PERMISSIONS = {
    "check-version": {"contents": "read"},
    "pure-wheel": {"contents": "read"},
    "attest": {
        "contents": "read",
        "id-token": "write",
        "attestations": "write",
    },
    "publish-pypi": {"contents": "read", "id-token": "write"},
    "draft-release": {"contents": "write"},
    "publish-release": {"contents": "write"},
}
_PINNED_ACTION = re.compile(r"^.+@[0-9a-f]{40}$")
_SETUP_PYTHON_PREFIX = "actions/setup-python@"
_USES_WITH_VERSION = re.compile(
    r"^\s*(?:-\s+)?uses:\s*(?P<reference>\S+)\s+#\s+(?P<version>v\S+)\s*$",
    re.MULTILINE,
)


@pytest.fixture(scope="module")
def release_text() -> str:
    """Read the release workflow source when its contracts are collected."""
    return _RELEASE_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def release_workflow(release_text: str) -> dict[str, typ.Any]:
    """Parse the release workflow for structural assertions."""
    return parse_workflow(release_text, "release.yml")


@pytest.fixture(scope="module")
def ci_workflow() -> dict[str, typ.Any]:
    """Read the CI workflow only when its build job contract is needed."""
    return parse_workflow(_CI_PATH.read_text(encoding="utf-8"), "ci.yml")


@pytest.fixture(scope="module")
def action_text() -> str:
    """Read the pure-Python action source for dependency contracts."""
    return _ACTION_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def action(action_text: str) -> dict[str, typ.Any]:
    """Parse the pure-Python action for step and pin assertions."""
    return parse_workflow(action_text, "pure-python-wheel/action.yml")


def _steps(job: dict[str, typ.Any]) -> list[dict[str, typ.Any]]:
    """Return a job's checked-in steps for focused contract assertions."""
    steps = job.get("steps")
    assert isinstance(steps, list), "every job must declare a step list"
    assert all(isinstance(step, dict) for step in steps), (
        "every workflow step must be a mapping"
    )
    return steps


def _named_step(job: dict[str, typ.Any], name: str) -> dict[str, typ.Any]:
    """Return the one step with the stable workflow-contract name."""
    return next(step for step in _steps(job) if step.get("name") == name)


def _all_steps(document: dict[str, typ.Any]) -> list[dict[str, typ.Any]]:
    """Collect steps from every job in a strictly parsed workflow."""
    jobs = document.get("jobs")
    if isinstance(jobs, dict):
        return [step for job in jobs.values() for step in _steps(job)]
    runs = document.get("runs")
    if isinstance(runs, dict):
        return _steps(runs)
    raise TypeError


def _run_scripts(
    document: dict[str, typ.Any], job_names: set[str]
) -> list[tuple[str, str]]:
    """Return each run body from the named workflow jobs."""
    jobs = document["jobs"]
    scripts = []
    for name in job_names:
        scripts.extend(
            (f"{name}:{step.get('name', '<unnamed>')}", step["run"])
            for step in _steps(jobs[name])
            if "run" in step
        )
    return typ.cast("list[tuple[str, str]]", scripts)


def _upload_action(steps: list[dict[str, typ.Any]]) -> dict[str, typ.Any]:
    """Return the artefact upload step or fail the contract clearly."""
    return next(
        step
        for step in steps
        if str(step.get("uses", "")).startswith("actions/upload-artifact@")
    )


def test_release_workflow_has_versioned_trigger_and_non_cancelling_lock(
    release_workflow: dict[str, typ.Any],
) -> None:
    """A tag rerun must not cancel an upload already in progress."""
    triggers = release_workflow.get("on", release_workflow.get(True))
    concurrency = release_workflow.get("concurrency")
    assert isinstance(triggers, dict), "the release workflow must declare triggers"
    assert triggers["push"]["tags"] == ["v*.*.*"], (
        "release publication must run only for version tags"
    )
    assert release_workflow["permissions"] == {}, (
        "workflow-wide permissions must default to none"
    )
    assert concurrency == {
        "group": "release-${{ github.ref }}",
        "cancel-in-progress": False,
    }, "a rerun must queue behind an upload instead of cancelling it"


def test_release_jobs_have_least_privilege_and_ordered_dependencies(
    release_workflow: dict[str, typ.Any],
) -> None:
    """Every publication job waits for version validation and its inputs."""
    jobs = release_workflow["jobs"]
    assert set(jobs) == _RELEASE_JOB_NAMES, (
        "release jobs must match the reviewed pipeline"
    )
    for name, job in jobs.items():
        assert "if" not in job, f"{name} must not hide behind a job condition"
        assert "continue-on-error" not in job, f"{name} must not suppress failure"
        assert job["runs-on"] == "ubicloud-standard-2", (
            f"{name} must use the registered release runner"
        )
        timeout = job.get("timeout-minutes")
        assert type(timeout) is int, f"{name} must use an integer timeout"
        assert 0 < timeout <= 60, (
            f"{name} must have a timeout no greater than 60 minutes"
        )
        actual_needs = set(job.get("needs", []))
        assert actual_needs == _EXPECTED_NEEDS[name], (
            f"{name} dependencies must be {_EXPECTED_NEEDS[name]}, got {actual_needs}"
        )
        assert job.get("permissions") == _EXPECTED_PERMISSIONS[name], (
            f"{name} must hold only its reviewed permissions"
        )
        for step in _steps(job):
            assert "continue-on-error" not in step, (
                f"{name}:{step.get('name', '<unnamed>')} must not suppress failure"
            )


def test_pypi_environment_and_upload_are_narrow_and_idempotent(
    release_workflow: dict[str, typ.Any], action: dict[str, typ.Any]
) -> None:
    """Trusted Publishing runs in the restricted pypi environment."""
    jobs = release_workflow["jobs"]
    pypi_job = jobs["publish-pypi"]
    assert pypi_job["environment"]["name"] == "pypi", (
        "only the PyPI publisher must enter the Trusted Publishing environment"
    )
    assert all(
        name == "publish-pypi" or "environment" not in job for name, job in jobs.items()
    ), "GitHub Release jobs must not inherit the PyPI environment"
    assert "GH_TOKEN" not in pypi_job.get("env", {}), (
        "PyPI publication must use Trusted Publishing instead of a stored token"
    )

    stage = _named_step(pypi_job, "Stage distributions not already on PyPI")
    publish = _named_step(pypi_job, "Publish to PyPI with Trusted Publishing")
    assert (
        stage["env"]["SIMPLE_INDEX_URL"] == "https://pypi.org/simple/falcon-correlate/"
    ), "staging must query the published project name"
    assert publish["if"] == "steps.stage.outputs.has-uploads == 'true'", (
        "replays with no remaining files must skip the upload action"
    )
    assert publish["with"]["packages-dir"] == "dist/pypi-staging", (
        "the upload action must consume only the filtered staging directory"
    )
    assert publish["with"]["skip-existing"] is True, (
        "a publication race must remain idempotent"
    )
    assert (
        _upload_action(_steps(jobs["attest"]))["with"]["if-no-files-found"] == "error"
    ), "attestation artifacts must not silently upload an empty release"
    assert (
        _upload_action(_steps(action["runs"]))["with"]["if-no-files-found"] == "error"
    ), "the build artifact must fail when no distributions were produced"


def _check_action_pins(label: str, document: dict[str, typ.Any], raw_text: str) -> None:
    """Check external action pins and checkout credentials in one document."""
    comments = {
        match["reference"]: match["version"]
        for match in _USES_WITH_VERSION.finditer(raw_text)
    }
    checkouts = 0
    for step in _all_steps(document):
        reference = step.get("uses")
        if not isinstance(reference, str):
            continue
        if reference.startswith("./"):
            continue
        assert _PINNED_ACTION.fullmatch(reference), (
            f"{label} action {reference!r} must use a full commit SHA"
        )
        assert comments.get(reference), (
            f"{label} action {reference!r} must carry a trailing version comment"
        )
        if reference.startswith("actions/checkout@"):
            checkouts += 1
            assert step.get("with", {}).get("persist-credentials") is False, (
                f"{label} checkout must not persist credentials"
            )
    assert checkouts > 0, f"{label} must include its expected checkout step"


def test_external_actions_are_pinned_and_checkouts_drop_credentials(
    release_workflow: dict[str, typ.Any],
    release_text: str,
    action: dict[str, typ.Any],
    action_text: str,
) -> None:
    """Release and composite-action dependencies cannot move by tag."""
    for label, document, raw_text in (
        ("release.yml", release_workflow, release_text),
        ("pure-python-wheel/action.yml", action, action_text),
    ):
        _check_action_pins(label, document, raw_text)


@pytest.mark.parametrize(
    "alternate_sha", [None, "a" * 40], ids=["checked-in", "updated"]
)
def test_release_helper_jobs_pin_supported_python(
    release_workflow: dict[str, typ.Any],
    release_text: str,
    alternate_sha: str | None,
) -> None:
    """Release helpers run on the project's supported Python version."""
    if alternate_sha is not None:
        updated = re.sub(
            r"(actions/setup-python@)[0-9a-f]{40}",
            rf"\g<1>{alternate_sha}",
            release_text,
        )
        assert f"actions/setup-python@{alternate_sha}" in updated, (
            "the regression case must exercise an updated action pin"
        )
        release_workflow = parse_workflow(updated, "release.yml")
    helper_jobs = (
        "check-version",
        "attest",
        "publish-pypi",
        "draft-release",
        "publish-release",
    )
    for job_name in helper_jobs:
        steps = _steps(release_workflow["jobs"][job_name])
        checkout_index = next(
            index
            for index, step in enumerate(steps)
            if step.get("uses", "").startswith("actions/checkout@")
        )
        setup_python_index = next(
            index
            for index, step in enumerate(steps)
            if step.get("uses", "").startswith(_SETUP_PYTHON_PREFIX)
        )
        setup_python = steps[setup_python_index]
        assert setup_python_index == checkout_index + 1, (
            f"{job_name} must set up Python immediately after checkout"
        )
        assert setup_python.get("with", {}).get("python-version") == "3.13", (
            f"{job_name} release helpers require pinned Python 3.13"
        )


def test_run_scripts_are_strict_and_do_not_interpolate_expressions(
    release_workflow: dict[str, typ.Any],
    release_text: str,
    ci_workflow: dict[str, typ.Any],
    action: dict[str, typ.Any],
) -> None:
    """Release scripts receive workflow values through environment variables."""
    scripts = [
        *_run_scripts(release_workflow, _RELEASE_JOB_NAMES),
        *_run_scripts(ci_workflow, {"build"}),
        *[
            (str(step.get("name", "<unnamed>")), step["run"])
            for step in _steps(action["runs"])
            if "run" in step
        ],
    ]
    for name, script in scripts:
        assert isinstance(script, str), f"{name} run body must be a string"
        assert "${{" not in script, f"{name} must not interpolate expressions into Bash"
        assert script.lstrip().startswith("set -euo pipefail"), (
            f"{name} must begin with strict shell options"
        )

    assert "softprops/action-gh-release" not in release_text, (
        "the release workflow must not publish before asset reconciliation"
    )
    assert "--clobber" not in release_text, (
        "GitHub assets must never be overwritten during an idempotent rerun"
    )
