"""Readers over the workflow documents the CodeScene boundary asserts against.

Kept apart from the contracts next door for the reason every reader in this
directory is: a reader exercised only over this repository's own seven correct
documents passes whether or not it discriminates anything, and separating it
lets a contract drive it with documents built in the test.

The boundary itself is CV-005. A pull request must not reach CodeScene. The CLI
is a third party in the path of every review, and on 2026-09-16 a floating
version broke its cobertura parser and reddened every branch in this estate
whose pull requests ran the check step, on code that had not changed. One
push-to-main lane publishes; pull requests measure coverage and compare it
against a local ratchet baseline.
"""

from __future__ import annotations

import typing as typ
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

#: The action that generates a coverage report.
COVERAGE_ACTION: typ.Final[str] = (
    "leynos/shared-actions/.github/actions/generate-coverage"
)

#: The action that talks to CodeScene.
UPLOAD_ACTION: typ.Final[str] = (
    "leynos/shared-actions/.github/actions/upload-codescene-coverage"
)

#: Pins verified to carry the CLI manifest that pins cs-coverage 1.0.101,
#: which is what makes an installation deterministic without a checksum
#: input. An allowlist rather than a list of known-bad pins: Dependabot
#: chooses from the whole history, so a list of bad pins can never be
#: complete, and an older pin reintroduces the floating install that broke
#: this repository's lanes. Refusing an unknown pin costs one verification;
#: accepting one fails open and silently.
MANIFEST_PINNED: typ.Final[frozenset[str]] = frozenset({
    "a5765019912a8ab6882b12db049c7cde635f3a85",
})

#: Anything naming CodeScene in a workflow's text. Matched against the raw
#: text rather than the parsed document, because a mention can sit in a
#: `run:` script, an `env:` value or an action input, and a walk that reads
#: only the shapes it expects would miss whichever one is used next.
CODESCENE_MARKERS: typ.Final[tuple[str, ...]] = (
    "cs-coverage",
    "CS_ACCESS_TOKEN",
    "upload-codescene-coverage",
    "codescene.io",
)


class WorkflowContractError(RuntimeError):
    """Base for every failure raised by this package's workflow readers.

    A stable catch point. Callers that want to handle any reader failure
    should name this rather than enumerating subclasses, so a reader added
    later does not escape a handler written today.
    """


class WorkflowReadError(WorkflowContractError):
    """Raised when a workflow document has a shape this reader cannot read.

    A real exception rather than an `assert`, which disappears under
    `python -O` and would turn a refusal into a silent empty answer.

    The workflow and the reason are kept as attributes as well as rendered
    into the message, so a caller can act on which file failed and why
    without parsing prose that exists to be read by a person.

    Attributes
    ----------
    workflow : str or None
        The file or directory the failure is about, when one is known.
    reason : str
        Why it could not be read.
    """

    def __init__(self, reason: str, workflow: str | None = None) -> None:
        """Record the reason and, when known, the workflow it concerns.

        Parameters
        ----------
        reason : str
            Why the document could not be read.
        workflow : str or None
            The file or directory concerned.
        """
        self.workflow = workflow
        self.reason = reason
        super().__init__(f"{workflow}: {reason}" if workflow else reason)


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
        If the text is not valid YAML, or is not a mapping.
    """
    try:
        document = yaml.safe_load(text)
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


def serves_pull_requests(document: dict[str, typ.Any]) -> bool:
    """Report whether a workflow runs on pull requests.

    Derived from the document rather than listed, so a workflow that gains a
    `pull_request` trigger tomorrow comes under the boundary without anyone
    remembering to add it.

    Parameters
    ----------
    document : dict[str, typ.Any]
        A parsed workflow document.

    Returns
    -------
    bool
        True when the workflow declares a `pull_request` trigger.
    """
    triggers = triggers_of(document)
    if isinstance(triggers, str):
        return triggers == "pull_request"
    if isinstance(triggers, list):
        return "pull_request" in triggers
    return "pull_request" in as_mapping(triggers, "a workflow must declare on:")


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


def steps_of(document: dict[str, typ.Any]) -> list[tuple[str, dict[str, typ.Any]]]:
    """Return every step in every job, paired with its job name.

    Parameters
    ----------
    document : dict[str, typ.Any]
        A parsed workflow document.

    Returns
    -------
    list[tuple[str, dict[str, typ.Any]]]
        Each step as `(job, mapping)`.
    """
    found: list[tuple[str, dict[str, typ.Any]]] = []
    for name, job in as_mapping(document.get("jobs"), "a workflow needs jobs").items():
        job_map = as_mapping(job, f"job {name} must be a mapping")
        found.extend(
            (str(name), as_mapping(step, f"a step in {name} must map"))
            for step in job_map.get("steps") or []
        )
    return found


def steps_using(
    document: dict[str, typ.Any], action: str
) -> list[tuple[str, str, dict[str, typ.Any]]]:
    """Return every step invoking `action`, with its job name and ref.

    The action path is compared against the part of `uses` before the `@`,
    not searched for as a substring: a search also selects any action whose
    path extends this one.

    Parameters
    ----------
    document : dict[str, typ.Any]
        A parsed workflow document.
    action : str
        The action path, without a ref.

    Returns
    -------
    list[tuple[str, str, dict[str, typ.Any]]]
        Each match as `(job, ref, inputs)`.
    """
    found: list[tuple[str, str, dict[str, typ.Any]]] = []
    for job, step in steps_of(document):
        uses = str(step.get("uses", ""))
        path, _, ref = uses.partition("@")
        if path != action:
            continue
        found.append((job, ref, as_mapping(step.get("with") or {}, "with must map")))
    return found


def codescene_mentions(text: str) -> list[str]:
    """Return every CodeScene marker appearing in a workflow's raw text.

    Read from the text rather than the parsed document because a mention can
    sit in a `run:` script, an `env:` value or an action input, and a walk
    reading only the shapes it expects misses whichever one is used next.

    Comment lines are excluded, so a file may explain the boundary without
    breaching it. A comment cannot invoke anything, and a rule that refused
    the word would forbid the only place the reason can be written down.

    Parameters
    ----------
    text : str
        The file's text.

    Returns
    -------
    list[str]
        Each marker found, sorted and without repeats.
    """
    code = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )
    return sorted({marker for marker in CODESCENE_MARKERS if marker in code})


def is_publisher(document: dict[str, typ.Any]) -> bool:
    """Report whether a workflow is the push-to-main publisher.

    A push trigger naming main is not enough on its own. `ci.yml` declares
    both `push` to main and `pull_request`, so a predicate reading only the
    push arm would call it a publisher while the boundary rules also call it
    a pull-request workflow, and the same file would be required to upload
    and forbidden from uploading. A workflow that serves pull requests is a
    pull-request workflow, and the publisher is the one that does not.

    Parameters
    ----------
    document : dict[str, typ.Any]
        A parsed workflow document.

    Returns
    -------
    bool
        True when the workflow pushes to main and serves no pull request.
    """
    return pushes_to_main(document) and not serves_pull_requests(document)
