"""Read a step's ``if:`` guard as the conjunction GitHub evaluates.

A rule asserting that a guard *contains* ``github.ref == 'refs/heads/main'``
passes for ``github.ref == 'refs/heads/main' && env.T != '' ||
github.event_name == 'workflow_dispatch'``, which makes every conjunct optional
and lets a dispatch from any branch publish. Guards are therefore split on
``&&``, and any form this reading cannot represent as a conjunction, an
unquoted ``||`` first among them, is refused rather than approximated.
"""

from __future__ import annotations

import re

from tests.workflow_contracts.errors import WorkflowReadError


def conjuncts(condition: str, where: str) -> list[str]:
    """Split a guard on ``&&``, refusing disjunction, grouping and negation.

    Parameters
    ----------
    condition : str
        The guard as written, with or without ``${{ }}``.
    where : str
        The step's location, for the message.

    Returns
    -------
    list[str]
        Each conjunct, whitespace-normalized.

    Raises
    ------
    WorkflowReadError
        If the guard contains ``||``, a parenthesized group, a negation, or
        an empty conjunct.

    Examples
    --------
    >>> conjuncts("${{ github.ref == 'refs/heads/main' && env.T != '' }}", "x")
    ["github.ref == 'refs/heads/main'", "env.T != ''"]
    """
    bare = _bare(condition)
    _refuse_what_is_not_a_conjunction(bare, condition, where)
    parts = [" ".join(part.split()) for part in bare.split("&&")]
    if not all(parts):
        message = f"the guard {condition!r} has an empty conjunct"
        raise WorkflowReadError(message, where)
    return parts


def _bare(condition: str) -> str:
    """Remove one enclosing ``${{ }}`` and surrounding whitespace.

    Parameters
    ----------
    condition : str
        The guard as written.

    Returns
    -------
    str
        The bare expression.
    """
    bare = condition.strip()
    if bare.startswith("${{") and bare.endswith("}}"):
        return bare[3:-2].strip()
    return bare


#: Tokens a conjunction may not contain outside a quoted literal, with why.
_NOT_A_CONJUNCTION = (
    ("||", "a disjunction makes every conjunct optional"),
    ("(", "a grouped sub-expression"),
    ("!", "a negation"),
)


def _refuse_what_is_not_a_conjunction(bare: str, condition: str, where: str) -> None:
    """Refuse a guard containing a disjunction, a group or a negation.

    Quoted literals may contain anything; `!=` is a comparison, not a
    negation; and `()` closes a status call such as `always()`.

    Parameters
    ----------
    bare : str
        The expression without ``${{ }}``.
    condition : str
        The guard as written, for the message.
    where : str
        The step's location, for the message.

    Raises
    ------
    WorkflowReadError
        If the expression contains a token no conjunction may.
    """
    scrubbed = re.sub(r"'[^']*'", "''", bare).replace("!=", "==").replace("()", "")
    for token, detail in _NOT_A_CONJUNCTION:
        if token in scrubbed:
            message = f"cannot read the guard {condition!r}: {detail}"
            raise WorkflowReadError(message, where)
