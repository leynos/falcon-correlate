"""Hold the ``codescene`` environment to the uploading job (CV-005).

The CodeScene token lives in the ``codescene`` environment, whose deployment
policy admits ``main`` alone. So every job that calls the uploader declares
that environment, no other job does, and no workflow a pull request can start
declares it in any job: a declaration there would let branch code ask for the
token.

Split from the contracts so the rule can be driven over documents written for
each case, not only over the files it guards.
"""

from __future__ import annotations

import typing as typ

from tests.workflow_contracts.codescene_lanes import UPLOAD_ACTION, as_mapping
from tests.workflow_contracts.pull_request_reach import pull_request_closure

if typ.TYPE_CHECKING:
    import collections.abc as cabc

#: The environment holding the CodeScene token.
ENVIRONMENT: typ.Final[str] = "codescene"
MISSING: typ.Final[str] = f"uploads but does not declare `environment: {ENVIRONMENT}`"
STRAY: typ.Final[str] = f"declares `{ENVIRONMENT}` but uploads nothing"
REACHABLE: typ.Final[str] = (
    f"can be started by a pull request and declares `{ENVIRONMENT}`"
)
NO_UPLOADER: typ.Final[str] = "no workflow job calls the CodeScene uploader"


def environment_name(job: cabc.Mapping[str, typ.Any]) -> str | None:
    """Return the environment a job declares, from either accepted form.

    Parameters
    ----------
    job : cabc.Mapping[str, typ.Any]
        One job mapping.

    Returns
    -------
    str | None
        The environment's name, or None when the job declares none.

    Examples
    --------
    >>> environment_name({"environment": "codescene"})
    'codescene'
    >>> environment_name({"environment": {"name": "codescene", "url": "x"}})
    'codescene'
    >>> environment_name({}) is None
    True
    """
    match job.get("environment"):
        case str() as name:
            return name
        case {"name": str() as name}:
            return name
        case _:
            return None


def _jobs(name: str, document: cabc.Mapping[str, typ.Any]) -> dict[str, typ.Any]:
    """Return a workflow's jobs, keyed by job id."""
    return as_mapping(document.get("jobs"), f"{name} needs jobs")


def _uploads(job: cabc.Mapping[str, typ.Any]) -> bool:
    """Return whether a job has a step calling the CodeScene uploader."""
    return any(
        isinstance(step, dict)
        and str(step.get("uses", "")).partition("@")[0] == UPLOAD_ACTION
        for step in job.get("steps") or []
    )


def _placement_problem(job: cabc.Mapping[str, typ.Any]) -> str | None:
    """Return what is wrong with one job's environment, or None when nothing is."""
    declares = environment_name(job) == ENVIRONMENT
    if _uploads(job):
        return None if declares else MISSING
    return STRAY if declares else None


def _placement_violations(
    documents: cabc.Mapping[str, cabc.Mapping[str, typ.Any]],
) -> list[str]:
    """Report uploading jobs without the environment and other jobs with it."""
    jobs = [
        (name, job_id, job)
        for name, document in documents.items()
        for job_id, job in _jobs(name, document).items()
    ]
    problems = [
        f"{name}:{job_id} {problem}"
        for name, job_id, job in jobs
        if (problem := _placement_problem(job)) is not None
    ]
    if not any(_uploads(job) for _name, _job_id, job in jobs):
        problems.append(NO_UPLOADER)
    return problems


def _reachable_violations(
    documents: cabc.Mapping[str, cabc.Mapping[str, typ.Any]],
) -> list[str]:
    """Report every job a pull request can start that declares the environment."""
    return [
        f"{name}:{job_id} {REACHABLE}"
        for name in sorted(pull_request_closure(documents))
        for job_id, job in _jobs(name, documents[name]).items()
        if environment_name(job) == ENVIRONMENT
    ]


def environment_violations(
    documents: cabc.Mapping[str, cabc.Mapping[str, typ.Any]],
) -> list[str]:
    """Report every departure from the ``codescene`` environment placement.

    Parameters
    ----------
    documents : cabc.Mapping[str, cabc.Mapping[str, typ.Any]]
        File name to parsed document, for every workflow in the directory.

    Returns
    -------
    list[str]
        One message per violation; empty when the placement holds. Finding no
        uploading job is itself a violation, so the rule cannot pass by finding
        nothing to check.
    """
    return _placement_violations(documents) + _reachable_violations(documents)
