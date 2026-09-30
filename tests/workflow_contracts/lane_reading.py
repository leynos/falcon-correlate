"""Readers over the workflow documents the runner and suite contracts assert against.

Kept apart from the contracts next door for the reason every reader in this
directory is: a reader exercised only over this repository's own correct
documents passes whether or not it discriminates anything, and separating it
lets a contract drive it with documents built in the test.

The CodeScene boundary (CV-005) is not read here: `make test-workflow-contracts`
runs it from the shared contract library.
"""

from __future__ import annotations

import typing as typ
from pathlib import Path

import yaml

from tests.workflow_contracts.errors import WorkflowContractError, WorkflowReadError
from tests.workflow_contracts.strict_yaml import StrictLoader
from tests.workflow_contracts.triggers import PULL_REQUEST_EVENTS, trigger_names

__all__ = ["WorkflowContractError", "WorkflowReadError"]

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"


def as_mapping(value: object, message: str) -> dict[str, typ.Any]:
    """Return `value` as a mapping, refusing anything else.

    Parameters
    ----------
    value : object
        The parsed value.
    message : str
        What to say when it is not a mapping.

    Returns
    -------
    dict[str, typ.Any]
        The value, narrowed.

    Raises
    ------
    WorkflowReadError
        If the value is not a mapping.
    """
    if not isinstance(value, dict):
        raise WorkflowReadError(message)
    return typ.cast("dict[str, typ.Any]", value)


def workflow_texts(directory: Path | None = None) -> dict[str, str]:
    """Return every workflow file's raw text, keyed by file name.

    Both YAML extensions are read: a lane in the other one would otherwise
    escape every rule here without failing anything.

    Parameters
    ----------
    directory : Path or None
        Where to read from. Defaults to this repository's workflows.

    Returns
    -------
    dict[str, str]
        File name to file text.

    Raises
    ------
    WorkflowReadError
        If the directory is absent, or a file cannot be read or decoded.
    """
    directory = WORKFLOWS_DIR if directory is None else directory
    if not directory.is_dir():
        message = (
            "not a readable workflow directory. A missing directory would "
            "otherwise make every rule here pass over an empty set of "
            "workflows"
        )
        raise WorkflowReadError(message, str(directory))
    texts: dict[str, str] = {}
    for path in sorted(directory.glob("*.y*ml")):
        try:
            texts[path.name] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            message = f"could not be read: {error}"
            raise WorkflowReadError(message, path.name) from error
    return texts


def parse(workflow: str, text: str) -> dict[str, typ.Any]:
    """Return one workflow's parsed document.

    Parameters
    ----------
    workflow : str
        The file's name, for the message.
    text : str
        The file's text.

    Returns
    -------
    dict[str, typ.Any]
        The parsed document.

    Raises
    ------
    WorkflowReadError
        If the text is not valid YAML, repeats a mapping key, uses a list or
        mapping as a key, or is not a mapping. PyYAML alone keeps the last of
        two equal keys in silence, so a credential declared in the discarded
        half would read here as absent.
    """
    try:
        document = yaml.load(text, Loader=StrictLoader)  # ruff: ignore[unsafe-yaml-load] - strict SafeLoader subclass
    except yaml.YAMLError as error:
        message = f"could not be parsed: {error}"
        raise WorkflowReadError(message, workflow) from error
    return as_mapping(document, f"{workflow} must parse to a mapping")


def triggers_of(document: dict[str, typ.Any]) -> object:
    """Return a workflow's trigger declaration.

    PyYAML resolves an unquoted `on:` key to the boolean `True`, so both
    spellings are read. A reader checking only the string key reports every
    workflow as having no triggers, which would make the rules below vacuous
    rather than failing.

    Parameters
    ----------
    document : dict[str, typ.Any]
        A parsed workflow document.

    Returns
    -------
    object
        Whatever the file declares, which may be a string, list or mapping.
    """
    return document.get("on", document.get(True))


def serves_pull_requests(
    document: dict[str, typ.Any], workflow: str = "workflow"
) -> bool:
    """Report whether a pull request can start a workflow directly.

    Derived from the document rather than listed, so a workflow that gains a
    `pull_request` trigger tomorrow comes under the boundary without anyone
    remembering to add it. `pull_request_target` counts: it runs with the
    base repository's secrets. A workflow a pull-request workflow calls is
    reached too, which is the closure's question, not this one's.

    Parameters
    ----------
    document : dict[str, typ.Any]
        A parsed workflow document.
    workflow : str
        The file's name, for a refusal's message.

    Returns
    -------
    bool
        True when the workflow declares a pull-request event, in any of the
        forms :func:`~tests.workflow_contracts.triggers.trigger_names`
        reads; an unreadable trigger block is refused there.
    """
    return bool(PULL_REQUEST_EVENTS & trigger_names(document, workflow))


def pushes_to_main(document: dict[str, typ.Any]) -> bool:
    """Report whether a workflow runs on a push to main.

    Parameters
    ----------
    document : dict[str, typ.Any]
        A parsed workflow document.

    Returns
    -------
    bool
        True when the workflow declares a push trigger naming main.
    """
    triggers = triggers_of(document)
    if not isinstance(triggers, dict):
        return False
    push = triggers.get("push")
    if not isinstance(push, dict):
        return False
    branches = push.get("branches")
    return isinstance(branches, list) and "main" in branches
