"""Readers over the workflow documents the placement contracts assert against.

The contracts next door say what must be true. This module turns the
workflow files into something to say it about, and it is kept separate for
two reasons.

The first is that a reader can be wrong while no workflow is wrong, and a
reader exercised only over this repository's own files cannot show that:
parametrized over seven correct documents it passes whether or not it
discriminates anything. Separating the reading lets the contracts drive it
with documents built in the test, including shapes this repository does not
contain and should never contain.

The second is that the raw text matters as much as the parsed value. A
folded scalar whose continuation is indented more deeply than its first line
keeps the line break, and the resulting ``runs-on`` carries a newline inside
an expression GitHub evaluates anyway. The parse tolerates it, so a reader
returning only the parsed value cannot refuse it, and a green run is not
evidence that it is absent.
"""

from __future__ import annotations

import re
import typing as typ
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
ACTIONLINT_CONFIG = REPO_ROOT / ".github" / "actionlint.yaml"

#: The paid label this repository uses.
UBICLOUD_LABEL = "ubicloud-standard-2"

#: Labels GitHub hosts itself, named rather than matched by prefix. A label
#: outside this set and outside the registry is either a typo or an
#: unreviewed paid runner, and the registry contract must say so either way.
GITHUB_HOSTED_LABELS = frozenset({
    "ubuntu-latest",
    "ubuntu-24.04",
    "ubuntu-24.04-arm",
    "ubuntu-22.04",
    "ubuntu-22.04-arm",
    "windows-latest",
    "macos-latest",
    "macos-15",
    "macos-15-intel",
})

#: Every job that must bill for a paid runner, as ``workflow:job``.
PAID_LANES = frozenset({
    "ci.yml:lint",
    "ci.yml:test",
    "coverage-main.yml:coverage-upload",
    "release.yml:pure-wheel",
    "release.yml:release",
})

#: Lanes that stay GitHub-hosted, with the reason each one stays. A
#: scheduled or dispatch-only lane gains nothing from a paid runner, and
#: public-repository minutes are free on GitHub.
HOSTED_LANES: typ.Final[dict[str, str]] = {
    "get-codescene-sha.yml:refresh-sha": "workflow_dispatch only",
    "build-wheels.yml:build": "workflow_call, and its matrix is not Linux-only",
}

#: The longest ceiling any paid lane may declare. Not a limit on what a job
#: needs, but a bound on what a hang can cost.
MAXIMUM_TIMEOUT_MINUTES = 60

#: The fork fallback, parsed. The guard names the fork field; the true arm
#: is the hosted fallback and the false arm is the paid runner.
#: A matrix job defers its label to the leg, and the deferral itself is
#: not a label.
MATRIX_DEFERRAL = "${{ matrix.os }}"

FORK_FALLBACK = re.compile(
    r"^\$\{\{\s*github\.event\.pull_request\.head\.repo\.fork\s*"
    r"&&\s*'(?P<when_fork>[^']+)'\s*"
    r"\|\|\s*'(?P<when_branch>[^']+)'\s*\}\}$"
)


class WorkflowReadError(RuntimeError):
    """Raised when a workflow document has a shape this reader cannot read.

    A real exception rather than an ``assert``: the queries below are the
    thing the contracts depend on, and an ``assert`` disappears under
    ``python -O``, which would turn a refusal into a silent empty answer.
    """


def _as_mapping(value: object, message: str) -> dict[str, typ.Any]:
    """Assert ``value`` is a mapping and narrow its static type."""
    if not isinstance(value, dict):
        raise WorkflowReadError(message)
    return typ.cast("dict[str, typ.Any]", value)


def workflow_texts() -> dict[str, str]:
    """Return every workflow file's raw text, keyed by file name.

    Both YAML extensions are read. A lane in the other one would otherwise
    escape every rule here without failing anything.

    Returns
    -------
    dict[str, str]
        File name to file text.
    """
    texts: dict[str, str] = {}
    for path in sorted(WORKFLOWS_DIR.glob("*.y*ml")):
        texts[path.name] = path.read_text(encoding="utf-8")
    return texts


def jobs_of(text: str, workflow: str) -> dict[str, dict[str, typ.Any]]:
    """Return one workflow's jobs, parsed."""
    document = _as_mapping(yaml.safe_load(text), f"{workflow} must parse to a mapping")
    jobs = _as_mapping(document.get("jobs"), f"{workflow} must declare a jobs mapping")
    return {
        str(name): _as_mapping(job, f"{workflow}:{name} must be a mapping")
        for name, job in jobs.items()
    }


def all_lanes() -> list[tuple[str, str, dict[str, typ.Any]]]:
    """Return every job in every workflow as ``(workflow, job, mapping)``."""
    lanes: list[tuple[str, str, dict[str, typ.Any]]] = []
    for workflow, text in workflow_texts().items():
        for name, job in jobs_of(text, workflow).items():
            lanes.append((workflow, name, job))
    return lanes


def _runner_declarations(job: dict[str, typ.Any]) -> list[object]:
    """Return the runner declarations a job resolves through.

    A matrix job defers to its legs, so each leg's image is a declaration
    and the job's own ``runs-on`` is only the deferral. A reusable-workflow
    caller declares nothing: the called workflow places its own jobs.

    Returns
    -------
    list[object]
        One declaration per leg, or the job's own ``runs-on``, or nothing.

    Raises
    ------
    WorkflowReadError
        If a job defers to ``matrix.os`` without declaring an include list.
    """
    runs_on = job.get("runs-on")
    if runs_on is None and isinstance(job.get("uses"), str):
        return []
    if not (isinstance(runs_on, str) and runs_on.strip() == MATRIX_DEFERRAL):
        return [runs_on]
    strategy = _as_mapping(
        job.get("strategy"),
        "a job deferring runs-on to matrix.os must declare a strategy mapping",
    )
    matrix = _as_mapping(
        strategy.get("matrix"),
        "a job deferring runs-on to matrix.os must declare a matrix mapping. "
        "A matrix built at run time, such as "
        "`matrix: ${{ fromJSON(needs.plan.outputs.legs) }}`, is valid GitHub "
        "and parses to a string, which this reader cannot inventory",
    )
    include = matrix.get("include")
    if not isinstance(include, list):
        message = (
            "a job deferring runs-on to matrix.os must declare a matrix "
            f"include list; got {include!r}"
        )
        raise WorkflowReadError(message)
    return [
        _as_mapping(
            entry, f"a matrix include entry must be a mapping; got {entry!r}"
        ).get("os")
        for entry in include
    ]


def _labels_from_declaration(value: object) -> set[str]:
    """Return the labels one runner declaration can resolve to.

    A conditional contributes **both** arms, because which one a run bills
    for depends on the head that triggered it. Anything else is a literal.

    Returns
    -------
    set[str]
        The labels that declaration can resolve to.

    Raises
    ------
    WorkflowReadError
        If the declaration is a shape this reader cannot inventory.
    """
    if not isinstance(value, str):
        message = (
            "runs-on here is a label, a conditional, or the matrix "
            "deferral. The list form and the group/labels mapping are "
            "valid GitHub and this reader cannot inventory them, so a "
            "job using one is refused rather than contributing nothing; "
            f"got {value!r}"
        )
        raise WorkflowReadError(message)
    fallback = FORK_FALLBACK.match(value.strip())
    if fallback:
        return {fallback["when_fork"], fallback["when_branch"]}
    return {value.strip()}


def labels_of(job: dict[str, typ.Any]) -> set[str]:
    """Return every label a job could resolve to.

    A job calling a reusable workflow declares no ``runs-on`` at all: the
    called workflow places its own jobs, so the caller bills for nothing and
    contributes no label. Any shape this reader cannot inventory is refused
    rather than skipped, because skipping answers "no labels" for a job that
    may bill for several, and a registry question must never be answered
    quietly.

    Returns
    -------
    set[str]
        Every label the job could resolve to, with no expression left in it.
        A reusable-workflow caller contributes an empty set.
    """
    labels: set[str] = set()
    for value in _runner_declarations(job):
        labels.update(_labels_from_declaration(value))
    return labels


def billable_labels(job: dict[str, typ.Any]) -> set[str]:
    """Return the labels a job can bill a third party for."""
    return labels_of(job) - set(GITHUB_HOSTED_LABELS)


def read_actionlint_registry() -> set[str]:
    """Return the runner labels registered for actionlint.

    Returns
    -------
    set[str]
        Every label named under ``self-hosted-runner.labels``.
    """
    config = _as_mapping(
        yaml.safe_load(ACTIONLINT_CONFIG.read_text(encoding="utf-8")),
        "the actionlint config must parse to a mapping",
    )
    runner = _as_mapping(
        config.get("self-hosted-runner"),
        "the config must declare self-hosted-runner",
    )
    return set(runner.get("labels") or [])


def serves_pull_requests(workflow: str) -> bool:
    """Report whether a workflow runs on pull requests.

    Derived from the document rather than declared, so a lane added to a
    pull-request workflow is covered by the fork-fallback rule without
    anyone remembering to list it. A second declaration is the gap: the
    lane would satisfy every other paid-lane rule while carrying a literal
    label that a fork can never obtain.

    Returns
    -------
    bool
        True when the workflow declares a ``pull_request`` trigger.
    """
    document = _as_mapping(
        yaml.safe_load(workflow_texts()[workflow]),
        f"{workflow} must parse to a mapping",
    )
    # PyYAML resolves an unquoted `on:` key to the boolean True.
    triggers = document.get("on", document.get(True))
    if isinstance(triggers, str):
        return triggers == "pull_request"
    if isinstance(triggers, list):
        return "pull_request" in triggers
    return "pull_request" in _as_mapping(
        triggers, f"{workflow} must declare an on: mapping"
    )


def paid_lanes_by_trigger(*, serving_pull_requests: bool) -> list[str]:
    """Return the paid lanes whose workflow does or does not serve pull requests.

    One function rather than a near-identical pair. The two questions are
    complements of each other, and writing them separately invited the two
    answers to drift apart, which is the very gap this derivation closes.

    Parameters
    ----------
    serving_pull_requests : bool
        Select the lanes whose workflow declares a ``pull_request`` trigger
        when true, and those whose workflow does not when false.

    Returns
    -------
    list[str]
        Each lane as ``workflow:job``, sorted.
    """
    return sorted(
        lane
        for lane in PAID_LANES
        if serves_pull_requests(lane.partition(":")[0]) is serving_pull_requests
    )
