"""Reader for the retired CodeScene checksum names.

Kept apart from `codescene_lanes` for the reason every reader in this
directory is kept apart from the contracts beside it: a reader exercised only
over this repository's own correct workflows passes whether or not it
discriminates anything, and a separate module lets a contract drive it with
documents built in the test.

The names it looks for are retired rather than merely unused.
`installer-checksum` carried a digest of the CodeScene installer script, and
the `CODESCENE_CLI_SHA256` repository variable fed it. From shared-actions
`f68e8e2e` the upload action rejects a non-empty `installer-checksum` and
installs the CLI from its own committed manifest instead, so a workflow
passing the input fails the moment the variable holds a value, and a workflow
refreshing the variable maintains a value nothing reads, which never fails at
all.
"""

from __future__ import annotations

import typing as typ

#: The deprecated input, and the repository variable that fed it.
DEPRECATED_CHECKSUM_INPUT: typ.Final[str] = "installer-checksum"
DEPRECATED_DIGEST_VARIABLE: typ.Final[str] = "CODESCENE_CLI_SHA256"

#: The dispatch workflow whose only output was that variable.
DIGEST_REFRESH_WORKFLOW: typ.Final[str] = "get-codescene-sha.yml"

_RETIRED_NAMES: typ.Final[tuple[str, ...]] = (
    DEPRECATED_CHECKSUM_INPUT,
    DEPRECATED_DIGEST_VARIABLE,
)


def deprecated_digest_mentions(text: str) -> list[str]:
    """Return the retired checksum names appearing in a workflow's code.

    Read from the raw text for the reason `codescene_mentions` is: a name can
    sit in a `run:` script, an `env:` value or an action input, and a walk
    reading only the shapes it expects misses whichever one is used next.

    Comment lines are excluded on the same terms. A comment invokes nothing,
    and `coverage-main.yml` explains in one why it passes no checksum; a rule
    that refused the word would delete the only place that reason can live.

    Parameters
    ----------
    text : str
        The file's text.

    Returns
    -------
    list[str]
        Each retired name found, sorted and without repeats.
    """
    code = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )
    return sorted({name for name in _RETIRED_NAMES if name in code})
