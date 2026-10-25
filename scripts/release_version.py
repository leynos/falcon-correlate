#!/usr/bin/env -S uv run python
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Check the project version against a release tag using only the stdlib."""

from __future__ import annotations

import os
import re
import sys
import tomllib
import typing as typ
from pathlib import Path

if typ.TYPE_CHECKING:
    import collections.abc as cabc

_PRERELEASE_MARKER = re.compile(
    r"(?i)(?<=\d)[-_.]?(?:alpha|beta|preview|pre|rc|a|b|c|dev)(?:[-_.]?\d+)?(?=[+.-]|$)"
)


def is_prerelease(version: str) -> bool:
    """Return whether a PEP 440 version is a pre-release or development release.

    Local version labels do not affect the classification, and post-release
    labels alone remain final releases.

    Parameters
    ----------
    version : str
        A version string from ``[project].version``.

    Returns
    -------
    bool
        ``True`` for pre-release and development versions.

    Examples
    --------
    >>> is_prerelease("1.2.0rc1"), is_prerelease("1.2.0.post1")
    (True, False)
    >>> is_prerelease("1.2.0+dev.4")
    False
    """
    public_version = version.partition("+")[0]
    return _PRERELEASE_MARKER.search(public_version) is not None


def validate_tag_version(tag: str, version: str) -> None:
    """Require the release tag to equal ``v`` plus the declared version.

    Parameters
    ----------
    tag : str
        The complete tag name.
    version : str
        The version declared by ``pyproject.toml``.

    Raises
    ------
    ValueError
        If the tag is not an exact match.

    Examples
    --------
    >>> validate_tag_version("v1.2.0", "1.2.0")
    >>> validate_tag_version("1.2.0", "1.2.0")
    Traceback (most recent call last):
        ...
    ValueError
    """
    expected = f"v{version}"
    if tag != expected:
        message = (
            f"Tag {tag!r} does not match pyproject.toml version {version!r}; "
            f"expected {expected!r}."
        )
        raise ValueError(message)


def _project_version(root: Path) -> str:
    """Read and validate ``[project].version`` from the manifest."""
    document = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    version = document["project"]["version"]
    if not isinstance(version, str):
        msg = "pyproject.toml [project].version must be a string"
        raise TypeError(msg)
    return version


def main(
    environ: cabc.Mapping[str, str] | None = None, root: Path | None = None
) -> int:
    """Check the tag and append version outputs for the workflow."""
    environment = os.environ if environ is None else environ
    project_root = Path.cwd() if root is None else root
    try:
        tag = environment["RELEASE_TAG"]
        output_path = Path(environment["GITHUB_OUTPUT"])
        version = _project_version(project_root)
        validate_tag_version(tag, version)
    except (KeyError, OSError, TypeError, ValueError) as error:
        message = str(error)
        print(
            f"::error file=pyproject.toml,title=Version check::{message}",
            file=sys.stderr,
        )
        return 1

    prerelease = str(is_prerelease(version)).lower()
    with output_path.open("a", encoding="utf-8") as output:
        output.write(f"version={version}\n")
        output.write(f"prerelease={prerelease}\n")
    print(f"Release tag {tag} matches pyproject.toml version {version}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
