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

import typing as typ

from tests.workflow_contracts.runs_on import (
    FORK_FALLBACK,
    GITHUB_HOSTED_LABELS,
    MATRIX_DEFERRAL,
    UBICLOUD_LABEL,
    billable_labels,
    labels_of,
)

# Re-exported deliberately. The `runs-on` vocabulary moved to `runs_on` for
# the module-size limit, and the contracts import it from here because that is
# where the lane vocabulary lives. Naming it keeps the re-export intentional
# rather than an import left behind by the split.
__all__ = [
    "FORK_FALLBACK",
    "GITHUB_HOSTED_LABELS",
    "HOSTED_LANES",
    "MATRIX_DEFERRAL",
    "MAXIMUM_TIMEOUT_MINUTES",
    "PAID_LANES",
    "UBICLOUD_LABEL",
    "all_lanes",
    "billable_labels",
    "continue_on_error_sites",
    "labels_of",
    "paid_lanes_by_trigger",
    "serves_pull_requests",
    "timeout_minutes_of",
]
from tests.workflow_contracts.workflow_documents import (
    WorkflowReadError,
    as_mapping,
    jobs_of,
    parse_workflow,
    text_of,
    workflow_texts,
)

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
    "build-wheels.yml:build": "workflow_call, and its matrix is not Linux-only",
}

#: The longest ceiling any paid lane may declare. Not a limit on what a job
#: needs, but a bound on what a hang can cost.
MAXIMUM_TIMEOUT_MINUTES = 60


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
    document = parse_workflow(text_of(texts, workflow), workflow)
    # PyYAML resolves an unquoted `on:` key to the boolean True.
    triggers = document.get("on", document.get(True))
    if isinstance(triggers, str):
        return triggers == "pull_request"
    if isinstance(triggers, list):
        return "pull_request" in triggers
    return "pull_request" in as_mapping(
        triggers, "must declare an on: mapping", workflow
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
