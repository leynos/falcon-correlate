"""Contracts that the test suite runs once per interpreter per event.

Pull requests run plain pytest on 3.12 and 3.14 and generate coverage on 3.13
in `ci.yml`. A push to main runs the suite under coverage on 3.13 in
`coverage-main.yml`, so `ci.yml` excludes its 3.13 leg on push. Without that
exclusion the same tests ran twice on every trunk commit, once plainly and
once instrumented, on the same interpreter.

The contract counts suite runs rather than inspecting one line, so it fails in
both directions: a second run of an interpreter is a duplicate, and a missing
one is an interpreter that stopped being tested. It also refuses a leg that
starts and runs no suite, which is how a step guard alone would hide the
duplicate while still billing a runner. Every step that could run the
suite in a form this reader does not know is refused rather than skipped, so a
new spelling cannot hide a run from the count.
"""

from __future__ import annotations

import re
import typing as typ

import pytest

from tests.workflow_contracts.codescene_lanes import (
    as_mapping,
    parse,
    pushes_to_main,
    serves_pull_requests,
    workflow_texts,
)
from tests.workflow_contracts.errors import WorkflowReadError
from tests.workflow_contracts.guard_conditions import admits

if typ.TYPE_CHECKING:
    import collections.abc as cabc

INTERPRETERS = ("3.12", "3.13", "3.14")
PLAIN_SUITE = "uv run pytest -v -n auto --ignore=tests/workflows"
COVERAGE_ACTION = "leynos/shared-actions/.github/actions/generate-coverage@"
MATRIX_KEY = "python-version"
#: The one computed exclusion this reader evaluates: a version dropped on one
#: event, and nothing dropped on any other.
EVENT_EXCLUSION = re.compile(
    r"^\$\{\{\s*github\.event_name == '(?P<event>[a-z_]+)'"
    r" && '(?P<version>[^']*)' \|\| ''\s*\}\}$"
)
INSTALL_INTERPRETER = re.compile(r"^uv python install (?P<version>\S+)$")
#: Commands that run the suite, or might; each must be the plain command.
SUITE_HINT = re.compile(r"\bpytest\b|\bmake\s+test\b")


def _excluded(entry: object, event: str, where: str) -> str:
    """Return the interpreter one matrix exclusion drops for *event*."""
    exclusion = as_mapping(entry, f"{where}: an exclusion must be a mapping")
    if set(exclusion) != {MATRIX_KEY}:
        message = f"{where}: cannot read the exclusion {exclusion!r}"
        raise WorkflowReadError(message)
    value = str(exclusion[MATRIX_KEY])
    if "${{" not in value:
        return value
    if computed := EVENT_EXCLUSION.fullmatch(value):
        return computed["version"] if computed["event"] == event else ""
    message = f"{where}: cannot evaluate the exclusion {value!r}"
    raise WorkflowReadError(message)


def _legs(job: dict[str, typ.Any], event: str, where: str) -> list[str | None]:
    """Return the interpreters a job's matrix starts for *event*.

    A job without a matrix is one leg with no matrix interpreter. A matrix
    with an ``include`` or a second dimension is refused, because either
    changes which legs start in a way this count does not model.

    Returns
    -------
    list[str | None]
        The started legs' interpreters, or ``[None]`` for a matrix-free job.

    Raises
    ------
    WorkflowReadError
        If the matrix has a key this reader does not model.
    """
    strategy = job.get("strategy")
    if strategy is None:
        return [None]
    matrix = as_mapping(
        as_mapping(strategy, f"{where}: strategy must map").get("matrix"),
        f"{where}: matrix must map",
    )
    if set(matrix) - {MATRIX_KEY, "exclude"}:
        message = f"{where}: cannot read the matrix keys {sorted(matrix)!r}"
        raise WorkflowReadError(message)
    dropped = {_excluded(entry, event, where) for entry in matrix.get("exclude", [])}
    return [str(version) for version in matrix[MATRIX_KEY] if version not in dropped]


def _installed_interpreter(job: dict[str, typ.Any], where: str) -> str:
    """Return the one interpreter a matrix-free job installs."""
    versions = [
        match["version"]
        for step in job.get("steps") or []
        if (match := INSTALL_INTERPRETER.fullmatch(str(step.get("run", "")).strip()))
    ]
    if len(versions) != 1:
        message = f"{where}: expected one interpreter installation, found {versions!r}"
        raise WorkflowReadError(message)
    return versions[0]


def _runs_suite(step: dict[str, typ.Any], where: str) -> bool:
    """Report whether a step runs the suite, refusing a form it cannot read."""
    if str(step.get("uses", "")).startswith(COVERAGE_ACTION):
        return True
    command = str(step.get("run", "")).strip()
    if not SUITE_HINT.search(command):
        return False
    if command == PLAIN_SUITE:
        return True
    message = f"{where}: cannot tell whether {command!r} runs the suite"
    raise WorkflowReadError(message)


def _starts_on(document: dict[str, typ.Any], workflow: str, event: str) -> bool:
    """Report whether *event* starts a workflow."""
    if event == "push":
        return pushes_to_main(document)
    return serves_pull_requests(document, workflow)


def suite_legs(texts: cabc.Mapping[str, str], event: str) -> list[tuple[str, int]]:
    """Return every started leg of a suite job, with how often it runs the suite.

    A job counts when any of its steps can run the suite. Each leg its matrix
    starts for *event* is reported with its interpreter and the number of suite
    steps its guards admit, which may be none: a leg that starts and runs no
    suite still takes a runner.

    Parameters
    ----------
    texts : cabc.Mapping[str, str]
        Workflow texts keyed by file name.
    event : str
        ``push`` for a push to main, or ``pull_request``.

    Returns
    -------
    list[tuple[str, int]]
        One ``(interpreter, suite runs)`` pair per started leg. A matrix,
        exclusion, guard or suite command the helpers cannot read is refused
        with :class:`WorkflowReadError` rather than counted.
    """
    legs: list[tuple[str, int]] = []
    for workflow, text in texts.items():
        document = parse(workflow, text)
        if not _starts_on(document, workflow, event):
            continue
        jobs = as_mapping(document.get("jobs"), f"{workflow} needs jobs")
        for name, raw in jobs.items():
            job = as_mapping(raw, f"{workflow}/{name} must map")
            legs.extend(_job_legs(job, event, f"{workflow}/{name}"))
    return legs


def suite_runs(texts: cabc.Mapping[str, str], event: str) -> list[str]:
    """Return the interpreter of every suite run *event* starts.

    Parameters
    ----------
    texts : cabc.Mapping[str, str]
        Workflow texts keyed by file name.
    event : str
        ``push`` for a push to main, or ``pull_request``.

    Returns
    -------
    list[str]
        One interpreter per suite run, repeated when it runs more than once.

    Examples
    --------
    >>> steps = [{"run": "uv python install 3.13"}, {"run": PLAIN_SUITE}]
    >>> text = str({"on": {"push": {"branches": ["main"]}},
    ...             "jobs": {"test": {"steps": steps}}})
    >>> suite_runs({"ci.yml": text}, "push")
    ['3.13']
    """
    return [
        interpreter
        for interpreter, count in suite_legs(texts, event)
        for _ in range(count)
    ]


def _leg_context(event: str, leg: str | None) -> dict[str, str]:
    """Return the context a leg's guards evaluate in."""
    context = {"github.event_name": event}
    if leg is not None:
        context["matrix.python-version"] = leg
    return context


def _job_legs(job: dict[str, typ.Any], event: str, where: str) -> list[tuple[str, int]]:
    """Return each started leg of one job with its admitted suite-step count."""
    suite_steps = [step for step in job.get("steps") or [] if _runs_suite(step, where)]
    if not suite_steps:
        return []
    started = [
        (leg, context)
        for leg in _legs(job, event, where)
        if admits(str(job.get("if", "")), context := _leg_context(event, leg), where)
    ]
    return [
        (
            leg or _installed_interpreter(job, where),
            sum(
                admits(str(step.get("if", "")), context, where) for step in suite_steps
            ),
        )
        for leg, context in started
    ]


@pytest.mark.parametrize("event", ["push", "pull_request"])
def test_each_interpreter_runs_the_suite_exactly_once(event: str) -> None:
    """Count one suite run per interpreter: no duplicate and no gap."""
    runs = suite_runs(workflow_texts(), event)

    assert sorted(runs) == sorted(INTERPRETERS), (
        f"on {event}, the suite ran on {sorted(runs)}; "
        f"expected each of {list(INTERPRETERS)} exactly once"
    )


@pytest.mark.parametrize("event", ["push", "pull_request"])
def test_no_suite_leg_starts_without_running_the_suite(event: str) -> None:
    """Refuse a leg that starts a runner only to skip every suite step.

    Guarding the plain step alone keeps the count right while the leg still
    checks out, installs and bills a runner for nothing; the matrix has to
    drop it instead.
    """
    idle = [
        interpreter
        for interpreter, count in suite_legs(workflow_texts(), event)
        if count == 0
    ]

    assert not idle, f"on {event}, legs on {idle} start but run no suite"


def test_an_unreadable_suite_command_is_refused() -> None:
    """Refuse a pytest spelling the count does not know, rather than skip it."""
    text = """
on:
  push:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: uv python install 3.13
      - run: uv run pytest -q
"""
    with pytest.raises(WorkflowReadError, match="cannot tell whether"):
        suite_runs({"ci.yml": text}, "push")


def test_an_unreadable_exclusion_is_refused() -> None:
    """Refuse a computed exclusion of a shape this reader cannot evaluate."""
    text = """
on:
  push:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.12', '3.13']
        exclude:
          - python-version: ${{ github.ref == 'refs/heads/main' && '3.13' || '' }}
    steps:
      - run: uv run pytest -v -n auto --ignore=tests/workflows
"""
    with pytest.raises(WorkflowReadError, match="cannot evaluate the exclusion"):
        suite_runs({"ci.yml": text}, "push")
