"""The lane vocabulary the placement contracts assert about.

Reading files and YAML lives in :mod:`tests.workflow_contracts.workflow_documents`;
this module knows about runners, paid lanes, ceilings and the fork fallback,
and asks that module for documents. The contracts next door say what must be
true. This module turns the workflow files into something to say it about,
and it is kept separate from the contracts for two reasons.

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

from tests.workflow_contracts.workflow_documents import (
    WorkflowReadError,
    as_mapping,
    jobs_of,
    parse_workflow,
    workflow_texts,
)

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


def all_lanes(
    texts: dict[str, str] | None = None,
) -> list[tuple[str, str, dict[str, typ.Any]]]:
    """Return every job in every workflow as ``(workflow, job, mapping)``.

    The source is a parameter so this query can be driven over documents
    built in a test. Defaulting to the repository's own workflows keeps the
    contracts next door readable, but a caller that wants a different corpus
    does not have to reach past this function to get one.

    Parameters
    ----------
    texts : dict[str, str] or None
        File name to file text. Defaults to this repository's workflows.

    Returns
    -------
    list[tuple[str, str, dict[str, typ.Any]]]
        Each job as ``(workflow, job, mapping)``.
    """
    texts = workflow_texts() if texts is None else texts
    lanes: list[tuple[str, str, dict[str, typ.Any]]] = []
    for workflow, text in texts.items():
        for name, job in jobs_of(text, workflow).items():
            lanes.append((workflow, name, job))
    return lanes


def timeout_minutes_of(job: dict[str, typ.Any]) -> int | None:
    """Return a job's declared ceiling in minutes, or ``None`` if absent.

    ``bool`` is a subclass of ``int``, so ``timeout-minutes: true`` would
    satisfy an ``isinstance`` check and then satisfy a range check as the
    value one. GitHub does not accept it, and a contract that does would
    accept a lane with no ceiling at all. The type is compared exactly, and
    a Boolean is reported as the shape it is rather than silently returned
    as a number.

    Parameters
    ----------
    job : dict[str, typ.Any]
        The job mapping.

    Returns
    -------
    int or None
        The declared ceiling, or ``None`` when none is declared.

    Raises
    ------
    WorkflowReadError
        If a ceiling is declared but is not an integer.
    """
    declared = job.get("timeout-minutes")
    if declared is None:
        return None
    if type(declared) is not int:
        message = (
            f"timeout-minutes must be an integer; got {declared!r}. A Boolean "
            "satisfies an isinstance check against int and then reads as one "
            "minute or zero, which is not a ceiling anyone reviewed"
        )
        raise WorkflowReadError(message)
    return declared


def continue_on_error_sites(job: dict[str, typ.Any]) -> list[str]:
    """Return every place a job declares ``continue-on-error``.

    The key is reported wherever it appears, whatever its value. GitHub
    accepts an expression there, and PyYAML hands an expression back as a
    string, so ``continue-on-error: ${{ true }}`` is not ``True`` and an
    identity comparison against ``True`` lets it through. The lane can then
    fail without failing the workflow while the contract passes, which is
    the whole failure this rule exists to refuse.

    Parameters
    ----------
    job : dict[str, typ.Any]
        The job mapping.

    Returns
    -------
    list[str]
        A description of each site, empty when the key appears nowhere.
    """
    sites: list[str] = []
    if "continue-on-error" in job:
        sites.append(f"job scope ({job['continue-on-error']!r})")
    for step in job.get("steps", []) or []:
        if isinstance(step, dict) and "continue-on-error" in step:
            named = step.get("name", step.get("uses", "?"))
            sites.append(f"step {named!r} ({step['continue-on-error']!r})")
    return sites


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
    strategy = as_mapping(
        job.get("strategy"),
        "a job deferring runs-on to matrix.os must declare a strategy mapping",
    )
    matrix = as_mapping(
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
        as_mapping(
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


def serves_pull_requests(workflow: str, texts: dict[str, str] | None = None) -> bool:
    """Report whether a workflow runs on pull requests.

    Derived from the document rather than declared, so a lane added to a
    pull-request workflow is covered by the fork-fallback rule without
    anyone remembering to list it. A second declaration is the gap: the
    lane would satisfy every other paid-lane rule while carrying a literal
    label that a fork can never obtain.

    Parameters
    ----------
    workflow : str
        The workflow file name.
    texts : dict[str, str] or None
        File name to file text. Defaults to this repository's workflows.

    Returns
    -------
    bool
        True when the workflow declares a ``pull_request`` trigger.
    """
    texts = workflow_texts() if texts is None else texts
    document = parse_workflow(texts[workflow], workflow)
    # PyYAML resolves an unquoted `on:` key to the boolean True.
    triggers = document.get("on", document.get(True))
    if isinstance(triggers, str):
        return triggers == "pull_request"
    if isinstance(triggers, list):
        return "pull_request" in triggers
    return "pull_request" in as_mapping(
        triggers, f"{workflow} must declare an on: mapping"
    )


def paid_lanes_by_trigger(
    *, serving_pull_requests: bool, texts: dict[str, str] | None = None
) -> list[str]:
    """Return the paid lanes whose workflow does or does not serve pull requests.

    One function rather than a near-identical pair. The two questions are
    complements of each other, and writing them separately invited the two
    answers to drift apart, which is the very gap this derivation closes.

    Parameters
    ----------
    serving_pull_requests : bool
        Select the lanes whose workflow declares a ``pull_request`` trigger
        when true, and those whose workflow does not when false.
    texts : dict[str, str] or None
        File name to file text. Defaults to this repository's workflows.

    Returns
    -------
    list[str]
        Each lane as ``workflow:job``, sorted.
    """
    texts = workflow_texts() if texts is None else texts
    return sorted(
        lane
        for lane in PAID_LANES
        if serves_pull_requests(lane.partition(":")[0], texts) is serving_pull_requests
    )
