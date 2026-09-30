"""Which events start a workflow, read in every form GitHub accepts.

A workflow's triggers are a scalar, a sequence or a mapping, under the ``on``
key or the boolean PyYAML reads it as. A reader that understood one form would
read ``on: [push, pull_request]`` as a single event with a strange name, and
that workflow would escape every pull-request rule. The CV-005 closure over
local calls now lives in the shared contract library (``make
test-workflow-contracts``); what stays here is the trigger reading the runner
contracts share.
"""

from __future__ import annotations

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
    """Read the scalar, list and mapping trigger forms, refusing any other."""
    if isinstance(declared, str):
        return frozenset({declared})
    names = list(declared) if isinstance(declared, (list, dict)) else []
    if not names or not all(isinstance(name, str) for name in names):
        message = f"declares triggers in no form GitHub accepts: {declared!r}"
        raise WorkflowReadError(message, workflow)
    return frozenset(names)
