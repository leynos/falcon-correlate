"""Which workflows a pull request can run, and what they forward to others.

A pull-request lane is a closure, not a trigger list. A workflow declaring only
``workflow_call`` still runs on a pull request when a pull-request workflow
calls it, and ``secrets: inherit`` hands it every secret the caller holds. The
hole was measured elsewhere in this estate, not reasoned about: a
``workflow_call``-only workflow, called from a pull-request job with ``secrets:
inherit`` and curling the CodeScene API with the inherited token, passed every
contract that enumerated triggers alone.

Every function here reads parsed documents, so each reading can be driven over
documents built in a test. This repository calls no local reusable workflow
today, so read from its own files a traversal that followed nothing would pass.
"""

from __future__ import annotations

import posixpath
import typing as typ

from tests.workflow_contracts.errors import WorkflowReadError

if typ.TYPE_CHECKING:
    import collections.abc as cabc

#: Events that let a pull request decide what runs. `pull_request_target` runs
#: with the base repository's secrets, which makes it the more dangerous of
#: the two, not an exemption.
PULL_REQUEST_EVENTS: typ.Final[frozenset[str]] = frozenset({
    "pull_request",
    "pull_request_target",
})

#: Where GitHub reads a repository's workflows.
WORKFLOW_DIRECTORY: typ.Final[str] = ".github/workflows"

#: This repository, as a remote reference to one of its own workflows names it.
REPOSITORY: typ.Final[str] = "leynos/falcon-correlate"

#: An ``owner/repo/path`` reference has at least two separators before the path.
_REMOTE_SEPARATORS: typ.Final[int] = 2


def trigger_names(
    document: cabc.Mapping[typ.Any, typ.Any], workflow: str
) -> frozenset[str]:
    """Return the events a workflow declares, in any form GitHub accepts.

    ``on: push``, ``on: [push, pull_request]`` and the mapping form are all
    read. A mapping-only reader stringifies the list into one key named after
    the whole list, and that workflow then escapes every pull-request rule.
    PyYAML reads an unquoted ``on`` as the boolean ``True``, so both keys are
    tried, and a document declaring both is refused as ambiguous.

    Parameters
    ----------
    document : cabc.Mapping[typ.Any, typ.Any]
        A parsed workflow document.
    workflow : str
        The file's name, for the message.

    Returns
    -------
    frozenset[str]
        The declared event names.

    Raises
    ------
    WorkflowReadError
        If the document declares no trigger block, declares it under both
        keys, or declares it in no form GitHub accepts.
    """
    present = [key for key in ("on", True) if key in document]
    if len(present) != 1:
        message = f"must declare exactly one trigger block; found {present}"
        raise WorkflowReadError(message, workflow)
    return _event_names(document[present[0]], workflow)


def _event_names(declared: object, workflow: str) -> frozenset[str]:
    """Read the scalar, list and mapping trigger forms.

    Parameters
    ----------
    declared : object
        The value under the trigger key.
    workflow : str
        The file's name, for the message.

    Returns
    -------
    frozenset[str]
        The declared event names.

    Raises
    ------
    WorkflowReadError
        If the value is none of a string, a list of strings, or a mapping.
    """
    if isinstance(declared, str):
        return frozenset({declared})
    names = list(declared) if isinstance(declared, (list, dict)) else []
    if not names or not all(isinstance(name, str) for name in names):
        message = f"declares triggers in no form GitHub accepts: {declared!r}"
        raise WorkflowReadError(message, workflow)
    return frozenset(names)


def _local_workflow(reference: str) -> str | None:
    """Return the workflow file a same-repository call names, if it is one.

    Matched by shape rather than by an enumerated prefix list: strip this
    repository's own ``owner/repo/`` and any ``@ref``, normalize the path,
    which also removes a leading ``./``, and ask whether what remains is a
    file directly under the workflow directory.

    Parameters
    ----------
    reference : str
        A job-level ``uses`` value.

    Returns
    -------
    str | None
        The file name, or ``None`` when the reference is not a local call.
    """
    path = reference.split("@", 1)[0].removeprefix(f"{REPOSITORY}/")
    directory, name = posixpath.split(posixpath.normpath(path))
    return name if directory == WORKFLOW_DIRECTORY and name else None


def _is_remote(reference: str) -> bool:
    """Report whether a job-level ``uses`` is an ``owner/repo/path@ref`` call.

    Parameters
    ----------
    reference : str
        A job-level ``uses`` value.

    Returns
    -------
    bool
        True for a reference into another repository.
    """
    path, separator, ref = reference.partition("@")
    return (
        bool(separator and ref)
        and path.count("/") >= _REMOTE_SEPARATORS
        and ".." not in path
    )


def _called(reference: str, present: cabc.Collection[str], workflow: str) -> str | None:
    """Return the local workflow one job-level ``uses`` calls, if any.

    Parameters
    ----------
    reference : str
        The job's ``uses`` value.
    present : cabc.Collection[str]
        File names in the workflow directory.
    workflow : str
        The calling file's name, for the message.

    Returns
    -------
    str | None
        The called file name, or ``None`` for a remote reusable workflow.

    Raises
    ------
    WorkflowReadError
        If the reference has neither known shape, which would otherwise drop
        the callee from the closure in silence, or names a local file that
        does not exist.
    """
    name = _local_workflow(reference)
    if name is None and not _is_remote(reference):
        message = f"calls {reference!r}, which is neither local nor owner/repo/path@ref"
        raise WorkflowReadError(message, workflow)
    if name is not None and name not in present:
        message = f"calls {reference!r}, which is not in {WORKFLOW_DIRECTORY}"
        raise WorkflowReadError(message, workflow)
    return name


def _jobs(document: cabc.Mapping[typ.Any, typ.Any]) -> dict[typ.Any, dict]:
    """Return a document's job mappings, skipping anything that is not one.

    The CodeScene reader refuses a malformed job in its own traversal; this
    reader answers only which calls and forwards a well-formed job makes.

    Parameters
    ----------
    document : cabc.Mapping[typ.Any, typ.Any]
        A parsed workflow document.

    Returns
    -------
    dict[typ.Any, dict]
        Job name to job mapping.
    """
    jobs = document.get("jobs")
    if not isinstance(jobs, dict):
        return {}
    return {name: job for name, job in jobs.items() if isinstance(job, dict)}


def local_calls(
    document: cabc.Mapping[typ.Any, typ.Any],
    present: cabc.Collection[str],
    workflow: str,
) -> frozenset[str]:
    """Return the same-repository workflows a document's jobs call.

    Only a job-level ``uses`` is a workflow call; a step-level ``uses`` runs
    an action. A remote reusable workflow is not followed, because its text is
    not here: what it can receive is decided by the caller's ``secrets:``,
    which :func:`inherited_secrets` and the text markers read. A malformed call
    is refused by :func:`_called` with :class:`WorkflowReadError`.

    Parameters
    ----------
    document : cabc.Mapping[typ.Any, typ.Any]
        A parsed workflow document.
    present : cabc.Collection[str]
        File names in the workflow directory.
    workflow : str
        The file's name, for the message.

    Returns
    -------
    frozenset[str]
        File names this document calls.
    """
    called = (
        _called(str(job["uses"]), present, workflow)
        for job in _jobs(document).values()
        if job.get("uses") is not None
    )
    return frozenset(name for name in called if name is not None)


def pull_request_closure(
    documents: cabc.Mapping[str, cabc.Mapping[typ.Any, typ.Any]],
) -> frozenset[str]:
    """Return every workflow a pull request reaches, following local calls.

    Parameters
    ----------
    documents : cabc.Mapping[str, cabc.Mapping[typ.Any, typ.Any]]
        File name to parsed document, for every workflow in the directory.

    Returns
    -------
    frozenset[str]
        The workflows a pull-request event triggers, and everything they
        call, transitively.
    """
    pending = [
        name
        for name, document in documents.items()
        if PULL_REQUEST_EVENTS & trigger_names(document, name)
    ]
    reached: set[str] = set()
    while pending:
        current = pending.pop()
        if current in reached:
            continue
        reached.add(current)
        pending.extend(local_calls(documents[current], documents, current) - reached)
    return frozenset(reached)


def inherited_secrets(document: cabc.Mapping[typ.Any, typ.Any]) -> list[str]:
    """Return every job that forwards all its secrets to a reusable workflow.

    ``secrets: inherit`` names no secret, so no text marker finds it, and it
    is how the token reaches a called workflow whose own text never mentions
    the caller.

    Parameters
    ----------
    document : cabc.Mapping[typ.Any, typ.Any]
        A parsed workflow document.

    Returns
    -------
    list[str]
        The names of the jobs that inherit, sorted.
    """
    return sorted(
        str(name)
        for name, job in _jobs(document).items()
        if str(job.get("secrets", "")).strip() == "inherit"
    )
