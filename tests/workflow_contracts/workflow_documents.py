"""Reading the workflow documents, and refusing the shapes that cannot be read.

Separated from the lane vocabulary next door because the two answer different
questions. This module knows about files, YAML and the shapes a document may
take; it knows nothing about runners, paid lanes or ceilings.

Reading is the one fallible step, so it reports its own failure rather than
letting an ``OSError`` or a ``yaml.YAMLError`` surface from what reads like a
query. Every entry point takes its source as a parameter and defaults to this
repository, so a caller can ask any of these questions about documents built
in a test.

Two refusals here were silent wrong answers before they were refusals. A
workflow directory that is not there made ``Path.glob`` yield nothing, so the
reader returned an empty mapping and every contract over "every lane" passed
over no lanes at all. And a ``labels:`` written as a bare scalar became a set
of its characters, so the registry contract compared letters against runner
labels.
"""

from __future__ import annotations

import typing as typ
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
ACTIONLINT_CONFIG = REPO_ROOT / ".github" / "actionlint.yaml"


class WorkflowReadError(RuntimeError):
    """Raised when a workflow document has a shape this reader cannot read.

    A real exception rather than an ``assert``: the queries below are the
    thing the contracts depend on, and an ``assert`` disappears under
    ``python -O``, which would turn a refusal into a silent empty answer.
    """


def as_mapping(value: object, message: str) -> dict[str, typ.Any]:
    """Return ``value`` as a mapping, refusing anything else.

    Public because the lane queries next door need the same refusal for the
    trigger mapping, and a second copy of it would be a second thing to keep
    in step with this one.

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

    Reading is the one fallible step in this module, so it reports its own
    failure rather than letting an ``OSError`` surface from what reads like
    a query. The directory is a parameter so a caller can point the reader
    at documents built in a test; it defaults to this repository's own
    workflows only so the contracts next door stay readable.

    Both YAML extensions are read. A lane in the other one would otherwise
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
        If a file cannot be read or decoded.
    """
    directory = WORKFLOWS_DIR if directory is None else directory
    if not directory.is_dir():
        message = (
            f"{directory} is not a readable workflow directory. A missing "
            "directory would otherwise make every contract here pass over an "
            "empty set of lanes"
        )
        raise WorkflowReadError(message)
    try:
        paths = sorted(directory.glob("*.y*ml"))
    except OSError as error:
        message = f"{directory} could not be enumerated: {error}"
        raise WorkflowReadError(message) from error
    texts: dict[str, str] = {}
    for path in paths:
        try:
            texts[path.name] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            message = f"{path.name} could not be read: {error}"
            raise WorkflowReadError(message) from error
    return texts


def parse_workflow(text: str, workflow: str) -> dict[str, typ.Any]:
    """Return one workflow's parsed document.

    Parameters
    ----------
    text : str
        The file's text.
    workflow : str
        The file's name, for the message.

    Returns
    -------
    dict[str, typ.Any]
        The parsed document.

    Raises
    ------
    WorkflowReadError
        If the text is not valid YAML, or is not a mapping.
    """
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as error:
        message = f"{workflow} could not be parsed: {error}"
        raise WorkflowReadError(message) from error
    return as_mapping(document, f"{workflow} must parse to a mapping")


def jobs_of(text: str, workflow: str) -> dict[str, dict[str, typ.Any]]:
    """Return one workflow's jobs, parsed.

    Returns
    -------
    dict[str, dict[str, typ.Any]]
        Each job mapping, keyed by job name.
    """
    document = parse_workflow(text, workflow)
    jobs = as_mapping(document.get("jobs"), f"{workflow} must declare a jobs mapping")
    return {
        str(name): as_mapping(job, f"{workflow}:{name} must be a mapping")
        for name, job in jobs.items()
    }


def read_actionlint_registry(config_path: Path | None = None) -> set[str]:
    """Return the runner labels registered for actionlint.

    Parameters
    ----------
    config_path : Path or None
        Which configuration to read. Defaults to this repository's own.

    Returns
    -------
    set[str]
        Every label named under ``self-hosted-runner.labels``.

    Raises
    ------
    WorkflowReadError
        If the file cannot be read, is not valid YAML, or is not a mapping.
    """
    config_path = ACTIONLINT_CONFIG if config_path is None else config_path
    try:
        text = config_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        message = f"{config_path.name} could not be read: {error}"
        raise WorkflowReadError(message) from error
    config = parse_workflow(text, config_path.name)
    runner = as_mapping(
        config.get("self-hosted-runner"),
        "the config must declare self-hosted-runner",
    )
    labels = runner.get("labels")
    if labels is None:
        return set()
    if not isinstance(labels, list) or not all(
        isinstance(label, str) for label in labels
    ):
        message = (
            f"{config_path.name} must declare self-hosted-runner.labels as a "
            f"list of strings; got {labels!r}. A bare scalar would otherwise "
            "become a set of its characters and the registry contract would "
            "compare letters against labels"
        )
        raise WorkflowReadError(message)
    return set(labels)
