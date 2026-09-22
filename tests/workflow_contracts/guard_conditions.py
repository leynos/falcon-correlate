"""Read a step's ``if:`` guard as the conjunction GitHub evaluates.

A rule asserting that a guard *contains* ``github.ref == 'refs/heads/main'``
passes for ``github.ref == 'refs/heads/main' && env.T != '' ||
github.event_name == 'workflow_dispatch'``, which makes every conjunct optional
and lets a dispatch from any branch publish. Guards are therefore split on
``&&``, and any form this reading cannot represent as a conjunction, an
unquoted ``||`` first among them, is refused rather than approximated.

:func:`admits` then evaluates a guard against a named context, which is how a
contract asks the behavioural question, whether a dispatch from a feature
branch uploads, without a workflow runner. It evaluates only the conjunctive
equality subset these guards use and refuses anything else, so an unfamiliar
guard fails loudly instead of being judged by a reading that does not
understand it.
"""

from __future__ import annotations

import re
import typing as typ

from tests.workflow_contracts.errors import WorkflowReadError

if typ.TYPE_CHECKING:
    import collections.abc as cabc

#: Tokens a conjunction may not contain outside a quoted literal, with why.
_NOT_A_CONJUNCTION = (
    ("||", "a disjunction makes every conjunct optional"),
    ("(", "a grouped sub-expression"),
    (")", "an unmatched closing parenthesis"),
    ("!", "a negation"),
)
#: A context reference compared with a quoted literal.
_COMPARISON = re.compile(
    r"^(?P<reference>[A-Za-z_][\w.-]*)\s*(?P<operator>==|!=)\s*'(?P<literal>[^']*)'$"
)
#: A bare context reference, read for truthiness.
_REFERENCE = re.compile(r"^[A-Za-z_][\w.-]*$")
#: Status functions, taken as true: the guards asserted on run after success.
_STATUS_FUNCTIONS = frozenset({"always()", "success()"})


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
        If the guard has an empty conjunct. A disjunction, a parenthesis or a
        negation is refused the same way by the check this calls.

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


def admits(condition: str, context: cabc.Mapping[str, str], where: str) -> bool:
    """Evaluate a conjunctive guard against named context values.

    Comparison ignores case, as GitHub's does for strings. A reference the
    context does not name is refused rather than read as empty, because the
    question is only answered when every input to it is stated. An empty
    guard admits everything.

    Parameters
    ----------
    condition : str
        The guard as written.
    context : cabc.Mapping[str, str]
        A value for each reference the guard reads, such as ``github.ref``.
    where : str
        The step's location, for a refusal's message.

    Returns
    -------
    bool
        Whether GitHub would run the step in that context. A conjunct of no
        supported form, or one reading an unnamed reference, is refused with
        :class:`WorkflowReadError` by the helpers.

    Examples
    --------
    >>> admits("github.ref == 'refs/heads/main'", {"github.ref": "refs/heads/x"}, "x")
    False
    """
    if not _bare(condition):
        return True
    return all(
        _admits_one(part, context, where) for part in conjuncts(condition, where)
    )


def _admits_one(part: str, context: cabc.Mapping[str, str], where: str) -> bool:
    """Evaluate one conjunct, refusing a form or reference it cannot read."""
    if part in _STATUS_FUNCTIONS:
        return True
    if comparison := _COMPARISON.fullmatch(part):
        value = _lookup(comparison["reference"], context, where)
        equal = value.casefold() == comparison["literal"].casefold()
        return equal if comparison["operator"] == "==" else not equal
    if _REFERENCE.fullmatch(part):
        return _lookup(part, context, where).casefold() not in {"", "false", "0"}
    message = f"cannot evaluate the conjunct {part!r}"
    raise WorkflowReadError(message, where)


def _lookup(reference: str, context: cabc.Mapping[str, str], where: str) -> str:
    """Return a context value, refusing one the caller did not supply."""
    if reference not in context:
        message = f"the guard reads {reference!r}, which the context does not name"
        raise WorkflowReadError(message, where)
    return context[reference]


def _bare(condition: str) -> str:
    """Remove one enclosing ``${{ }}`` and surrounding whitespace."""
    bare = condition.strip()
    if bare.startswith("${{") and bare.endswith("}}"):
        return bare[3:-2].strip()
    return bare


def _refuse_what_is_not_a_conjunction(bare: str, condition: str, where: str) -> None:
    """Refuse a disjunction, a parenthesis or a negation outside a literal."""
    # Quoted literals may contain anything; `!=` is a comparison, not a
    # negation; and `()` closes a status call such as `always()`.
    scrubbed = re.sub(r"'[^']*'", "''", bare).replace("!=", "==").replace("()", "")
    for token, detail in _NOT_A_CONJUNCTION:
        if token in scrubbed:
            message = f"cannot read the guard {condition!r}: {detail}"
            raise WorkflowReadError(message, where)
