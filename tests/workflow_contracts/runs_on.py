"""How a job's ``runs-on`` resolves to the labels it can bill for.

Separated from the lane vocabulary next door because the two answer different
questions. This module knows what GitHub accepts in a ``runs-on`` and how each
form resolves; it knows nothing about which lanes this repository agreed to
move or what ceiling they must declare.

All three forms GitHub accepts are modelled: a scalar label, a sequence of
labels, and the ``group``/``labels`` mapping. Anything else is refused rather
than read as declaring no runner, and that direction is the point. A reader
returning the empty set for an unmodelled shape removes the lane from the
placement rule, the ceiling rule and the registry rule at the same time, and
all three then pass; vk's reader did exactly that and hid a paid, unregistered
sequence lane from all three at once (vk #264).
"""

from __future__ import annotations

import re
import typing as typ

from tests.workflow_contracts.workflow_documents import (
    WorkflowReadError,
    as_mapping,
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

#: A matrix job defers its label to the leg, and the deferral itself is not a
#: label.
MATRIX_DEFERRAL = "${{ matrix.os }}"

#: The fork fallback, parsed. The guard names the fork field; the true arm is
#: the hosted fallback and the false arm is the paid runner.
FORK_FALLBACK = re.compile(
    r"^\$\{\{\s*github\.event\.pull_request\.head\.repo\.fork\s*"
    r"&&\s*'(?P<when_fork>[^']+)'\s*"
    r"\|\|\s*'(?P<when_branch>[^']+)'\s*\}\}$"
)


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


def _labels_from_sequence(value: list[object]) -> set[str]:
    """Return the labels a sequence ``runs-on`` resolves to.

    Every element must be satisfied at once, so a job naming a paid label in
    a sequence bills for it exactly as a scalar would. Modelled rather than
    refused: vk's reader classified this shape as "declares no runner" and
    hid a paid, unregistered lane from three contracts at once (vk #264).

    Parameters
    ----------
    value : list[object]
        The sequence as parsed.

    Returns
    -------
    set[str]
        Every label the sequence names.
    """
    labels: set[str] = set()
    for element in value:
        labels |= _labels_from_declaration(element)
    return labels


def _labels_from_group_mapping(value: dict[str, typ.Any]) -> set[str]:
    """Return the labels a ``group``/``labels`` mapping resolves to.

    Both keys contribute. ``labels`` narrows within the group rather than
    replacing it, a runner group is as billable as a label, and the registry
    question is asked of both.

    Parameters
    ----------
    value : dict[str, typ.Any]
        The mapping as parsed.

    Returns
    -------
    set[str]
        Every label and group the mapping names.

    Raises
    ------
    WorkflowReadError
        If the mapping declares neither key.
    """
    found: set[str] = set()
    for key in ("group", "labels"):
        if key in value:
            found |= _labels_from_declaration(value[key])
    if not found:
        message = (
            "runs-on is a mapping declaring neither group nor labels, so no "
            f"runner can be resolved from it; got {value!r}"
        )
        raise WorkflowReadError(message)
    return found


def _labels_from_declaration(value: object) -> set[str]:
    """Return the labels one runner declaration can resolve to.

    All three forms GitHub accepts are modelled: a scalar label, a sequence
    of labels, and the ``group``/``labels`` mapping. A conditional
    contributes **both** arms, because which one a run bills for depends on
    the head that triggered it.

    Anything outside those forms is refused rather than read as declaring no
    runner. The difference matters: a reader that returns the empty set for
    an unmodelled shape removes that lane from the placement rule, the
    ceiling rule and the registry rule simultaneously, and every one of them
    then passes. Refusing fails one rule loudly instead.

    Returns
    -------
    set[str]
        The labels that declaration can resolve to.

    Raises
    ------
    WorkflowReadError
        If the declaration is a shape this reader cannot inventory.
    """
    if isinstance(value, list):
        return _labels_from_sequence(value)
    if isinstance(value, dict):
        return _labels_from_group_mapping(value)
    if not isinstance(value, str):
        message = (
            "runs-on must be a label, a conditional, the matrix deferral, a "
            "sequence of labels, or a group/labels mapping. Anything else is "
            "refused rather than read as declaring no runner, because a "
            f"silent miss hides a paid lane from every rule at once; got {value!r}"
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
