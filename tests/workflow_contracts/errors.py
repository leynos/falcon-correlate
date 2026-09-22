"""The exception hierarchy every workflow reader in this package raises.

One module so there is one catch point. Two readers live here,
:mod:`workflow_documents` for the files and their YAML and
:mod:`codescene_lanes` for the CodeScene boundary, and each grew its own
`WorkflowReadError` while the other was on a different branch. Two classes of
that name in one package defeat the reason the base exists: a caller writing
`except WorkflowReadError` catches whichever one it happened to import and
misses the other, and nothing says so at the point of use.

The errors are real exceptions rather than `assert` statements. An `assert`
disappears under `python -O`, which would turn a refusal into a silent empty
answer, and an empty answer is what every rule in this package is most
vulnerable to: a contract over "every lane" passes over no lanes.
"""

from __future__ import annotations


class WorkflowContractError(RuntimeError):
    """Base for every failure raised by this package's workflow readers.

    A stable catch point. Callers wanting to handle any reader failure name
    this rather than enumerating subclasses, so a reader added later does not
    escape a handler written today.
    """


class WorkflowReadError(WorkflowContractError):
    """Raised when a workflow document has a shape a reader cannot read.

    The workflow and the reason are kept as attributes as well as rendered
    into the message, so a caller can act on which file failed and why without
    parsing prose that exists to be read by a person.

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
