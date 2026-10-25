"""Pure validation and digest logic for release distributions."""

from __future__ import annotations

import dataclasses as dc
import hashlib
import json
import re
import typing as typ
import urllib.parse as urlparse

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    from pathlib import Path

_SAFE_FILENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.IGNORECASE)
_DIGEST_PREFIX = "sha256:"


class ReleaseAssetError(ValueError):
    """Raised when release artefacts or destination metadata are invalid."""


@dc.dataclass(frozen=True, slots=True)
class PypiFile:
    """One file listed by the PyPI Simple API.

    Parameters
    ----------
    sha256 : str
        Lowercase hexadecimal SHA-256 digest.
    url : str
        Absolute HTTPS URL for the file bytes.
    """

    sha256: str
    url: str


def collect_distributions(directory: Path) -> tuple[Path, ...]:
    """Collect every wheel and exactly one source archive from ``directory``.

    Any other entry is rejected. A release must contain at least one wheel and
    exactly one ``.tar.gz`` source distribution.

    Parameters
    ----------
    directory : pathlib.Path
        Directory containing only the build's release distributions.

    Returns
    -------
    tuple[pathlib.Path, ...]
        Sorted wheel paths followed by the single source archive.

    Raises
    ------
    ReleaseAssetError
        If the directory is empty, contains unknown entries, has no wheel, or
        does not contain exactly one source archive.
    """
    if not directory.is_dir():
        msg = f"distribution directory does not exist: {directory}"
        raise ReleaseAssetError(msg)

    entries = sorted(directory.iterdir(), key=lambda entry: entry.name)
    if not entries:
        msg = "refusing an empty release artefact set"
        raise ReleaseAssetError(msg)

    unknown = [
        entry.name
        for entry in entries
        if not entry.is_file()
        or not _SAFE_FILENAME.fullmatch(entry.name)
        or not (entry.name.endswith(".whl") or entry.name.endswith(".tar.gz"))
    ]
    if unknown:
        msg = f"refusing unknown release entries: {unknown}"
        raise ReleaseAssetError(msg)

    wheels = tuple(entry for entry in entries if entry.name.endswith(".whl"))
    sdists = tuple(entry for entry in entries if entry.name.endswith(".tar.gz"))
    if not wheels:
        msg = "release artefacts must include at least one wheel"
        raise ReleaseAssetError(msg)
    if len(sdists) != 1:
        msg = f"expected exactly one source distribution, found {len(sdists)}"
        raise ReleaseAssetError(msg)
    return (*wheels, sdists[0])


def parse_pep691_index(body: str, index_url: str) -> dict[str, PypiFile]:
    """Parse a PEP 691 JSON Simple index into filename, digest, and URL data.

    Parameters
    ----------
    body : str
        JSON response body from the project Simple index.
    index_url : str
        URL of the index, used to resolve relative file URLs.

    Returns
    -------
    dict[str, PypiFile]
        Each listed filename mapped to its SHA-256 digest and download URL.

    Raises
    ------
    ReleaseAssetError
        If the response is malformed or a file lacks a safe name, SHA-256
        digest, or download URL.
    """
    try:
        document = json.loads(body)
    except json.JSONDecodeError as error:
        msg = f"PyPI Simple index is not valid JSON: {error}"
        raise ReleaseAssetError(msg) from error
    if not isinstance(document, dict):
        msg = "PyPI Simple index must be a JSON object"
        raise ReleaseAssetError(msg)
    if not isinstance(document.get("files"), list):
        msg = "PyPI Simple index must contain a files array"
        raise ReleaseAssetError(msg)

    files: dict[str, PypiFile] = {}
    for entry in document["files"]:
        filename, file = _parse_pep691_file(entry, index_url)
        if filename in files:
            msg = f"PyPI Simple index repeats filename {filename!r}"
            raise ReleaseAssetError(msg)
        files[filename] = file
    return files


def _parse_pep691_file(entry: object, index_url: str) -> tuple[str, PypiFile]:
    """Validate and normalize one PEP 691 file entry."""
    if not isinstance(entry, dict):
        msg = "PyPI Simple index file entries must be objects"
        raise ReleaseAssetError(msg)
    filename = entry.get("filename")
    hashes = entry.get("hashes")
    relative_url = entry.get("url")
    digest = hashes.get("sha256") if isinstance(hashes, dict) else None
    if not isinstance(filename, str) or not _SAFE_FILENAME.fullmatch(filename):
        msg = "PyPI Simple index has an unsafe filename"
        raise ReleaseAssetError(msg)
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        msg = f"PyPI Simple index has an invalid SHA-256 digest for {filename}"
        raise ReleaseAssetError(msg)
    if not isinstance(relative_url, str):
        msg = f"PyPI Simple index has no download URL for {filename}"
        raise ReleaseAssetError(msg)
    url = urlparse.urljoin(index_url, relative_url)
    if not url.startswith("https://"):
        msg = f"PyPI file URL must use HTTPS: {url!r}"
        raise ReleaseAssetError(msg)
    return filename, PypiFile(digest.lower(), url)


def parse_github_asset_digests(body: str) -> dict[str, str | None]:
    """Parse ``gh release view --json assets`` into digest entries.

    Parameters
    ----------
    body : str
        JSON response containing an ``assets`` array.

    Returns
    -------
    dict[str, str or None]
        Each safe asset name mapped to its lowercase SHA-256 digest, or
        ``None`` when GitHub did not provide a SHA-256 digest.

    Raises
    ------
    ReleaseAssetError
        If the response is malformed or repeats an asset name.
    """
    try:
        document = json.loads(body)
    except json.JSONDecodeError as error:
        msg = f"GitHub release assets are not valid JSON: {error}"
        raise ReleaseAssetError(msg) from error
    if not isinstance(document, dict):
        msg = "GitHub release response must be a JSON object"
        raise ReleaseAssetError(msg)
    if not isinstance(document.get("assets"), list):
        msg = "GitHub release response must contain an assets array"
        raise ReleaseAssetError(msg)

    assets: dict[str, str | None] = {}
    for asset in document["assets"]:
        if not isinstance(asset, dict):
            msg = "GitHub release asset entries must be objects"
            raise ReleaseAssetError(msg)
        name = asset.get("name")
        if not isinstance(name, str) or not _SAFE_FILENAME.fullmatch(name):
            msg = "GitHub release has an unsafe asset name"
            raise ReleaseAssetError(msg)
        if name in assets:
            msg = f"GitHub release repeats asset name {name!r}"
            raise ReleaseAssetError(msg)
        digest = asset.get("digest")
        assets[name] = _parse_github_digest(digest)
    return assets


def _parse_github_digest(digest: object) -> str | None:
    """Return a valid SHA-256 hex digest from GitHub's ``sha256:`` form."""
    if not isinstance(digest, str) or not digest.startswith(_DIGEST_PREFIX):
        return None
    value = digest.removeprefix(_DIGEST_PREFIX)
    return value.lower() if _SHA256.fullmatch(value) else None


def sha256_file(path: Path) -> str:
    """Return a file's SHA-256 hex digest without loading it all at once.

    Parameters
    ----------
    path : pathlib.Path
        File to hash.

    Returns
    -------
    str
        Lowercase hexadecimal SHA-256 digest.
    """
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def missing_names(
    expected: cabc.Iterable[str], present: cabc.Collection[str]
) -> list[str]:
    """Return expected filenames absent from a destination, in sorted order.

    Parameters
    ----------
    expected : collections.abc.Iterable[str]
        Filenames that the destination should contain.
    present : collections.abc.Collection[str]
        Filenames already held by the destination.

    Returns
    -------
    list[str]
        Expected filenames absent from the destination, sorted by name.
    """
    return sorted(set(expected) - set(present))


def digest_mismatches(
    expected: cabc.Iterable[str],
    pypi_files: cabc.Mapping[str, PypiFile],
    github_assets: cabc.Mapping[str, str | None],
) -> list[str]:
    """Describe missing or differing distribution digests across destinations.

    Parameters
    ----------
    expected : collections.abc.Iterable[str]
        Distribution filenames that the release must contain.
    pypi_files : collections.abc.Mapping[str, PypiFile]
        PyPI Simple index entries.
    github_assets : collections.abc.Mapping[str, str or None]
        GitHub release asset digests.

    Returns
    -------
    list[str]
        Sorted diagnostic messages; an empty list means the digests agree.
    """
    problems = []
    for name in sorted(set(expected)):
        pypi_file = pypi_files.get(name)
        if pypi_file is None:
            problems.append(f"{name} is missing from PyPI")
            continue
        github_digest = github_assets.get(name)
        if name not in github_assets:
            problems.append(f"{name} is missing from the GitHub Release")
        elif github_digest is None:
            problems.append(f"{name} has no GitHub SHA-256 digest")
        elif github_digest != pypi_file.sha256:
            problems.append(
                f"{name} differs: PyPI sha256 {pypi_file.sha256}, "
                f"GitHub sha256 {github_digest}"
            )
    return problems
