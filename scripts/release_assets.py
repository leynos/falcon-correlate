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


def _is_distribution_entry(entry: Path) -> bool:
    """Recognize safe regular distribution files in a build directory."""
    return (
        entry.is_file()
        and bool(_SAFE_FILENAME.fullmatch(entry.name))
        and entry.name.endswith((".whl", ".tar.gz"))
    )


def _distribution_entries(directory: Path) -> list[Path]:
    """Read and validate the entries in a distribution directory."""
    if not directory.is_dir():
        msg = f"distribution directory does not exist: {directory}"
        raise ReleaseAssetError(msg)

    entries = sorted(directory.iterdir(), key=lambda entry: entry.name)
    if not entries:
        msg = "refusing an empty release artefact set"
        raise ReleaseAssetError(msg)

    unknown = [entry.name for entry in entries if not _is_distribution_entry(entry)]
    if unknown:
        msg = f"refusing unknown release entries: {unknown}"
        raise ReleaseAssetError(msg)

    return entries


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
    entries = _distribution_entries(directory)
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
    match document:
        case {"files": list() as entries}:
            pass
        case dict():
            msg = "PyPI Simple index must contain a files array"
            raise ReleaseAssetError(msg)
        case _:
            msg = "PyPI Simple index must be a JSON object"
            raise ReleaseAssetError(msg)

    files: dict[str, PypiFile] = {}
    for entry in entries:
        filename, file = _parse_pep691_file(entry, index_url)
        if filename in files:
            msg = f"PyPI Simple index repeats filename {filename!r}"
            raise ReleaseAssetError(msg)
        files[filename] = file
    return files


def _parse_pep691_file(entry: object, index_url: str) -> tuple[str, PypiFile]:
    """Validate and normalize one PEP 691 file entry."""
    match entry:
        case {
            "filename": str() as filename,
            "hashes": {"sha256": str() as digest},
            "url": str() as relative_url,
        }:
            pass
        case {
            "filename": str() as filename,
            "hashes": dict() as hashes,
            "url": str() as relative_url,
        }:
            digest = hashes.get("sha256")
        case {
            "filename": str() as filename,
            "url": str() as relative_url,
        }:
            digest = None
        case dict():
            msg = "PyPI Simple index file entry is missing required fields"
            raise ReleaseAssetError(msg)
        case _:
            msg = "PyPI Simple index file entries must be objects"
            raise ReleaseAssetError(msg)

    if not _SAFE_FILENAME.fullmatch(filename):
        msg = "PyPI Simple index has an unsafe filename"
        raise ReleaseAssetError(msg)
    match digest:
        case str() if _SHA256.fullmatch(digest):
            pass
        case _:
            msg = f"PyPI Simple index has an invalid SHA-256 digest for {filename}"
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
    match document:
        case {"assets": list() as entries}:
            pass
        case dict():
            msg = "GitHub release response must contain an assets array"
            raise ReleaseAssetError(msg)
        case _:
            msg = "GitHub release response must be a JSON object"
            raise ReleaseAssetError(msg)

    assets: dict[str, str | None] = {}
    for asset in entries:
        name, digest = _parse_github_asset(asset)
        if name in assets:
            msg = f"GitHub release repeats asset name {name!r}"
            raise ReleaseAssetError(msg)
        assets[name] = digest
    return assets


def _parse_github_asset(asset: object) -> tuple[str, str | None]:
    """Validate one GitHub asset and normalize its optional digest."""
    match asset:
        case {"name": str() as name, "digest": digest}:
            pass
        case {"name": str() as name}:
            digest = None
        case dict():
            msg = "GitHub release asset is missing a valid name"
            raise ReleaseAssetError(msg)
        case _:
            msg = "GitHub release asset entries must be objects"
            raise ReleaseAssetError(msg)
    if not _SAFE_FILENAME.fullmatch(name):
        msg = "GitHub release has an unsafe asset name"
        raise ReleaseAssetError(msg)
    return name, _parse_github_digest(digest)


def _parse_github_digest(digest: object) -> str | None:
    """Return a valid SHA-256 hex digest from GitHub's ``sha256:`` form."""
    match digest:
        case str() as value if value.startswith(_DIGEST_PREFIX):
            value = value.removeprefix(_DIGEST_PREFIX)
            return value.lower() if _SHA256.fullmatch(value) else None
        case _:
            return None


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
    candidate_assets: cabc.Mapping[str, str | None],
    candidate_name: str = "GitHub Release",
) -> list[str]:
    """Describe missing or differing candidate digests against PyPI.

    Parameters
    ----------
    expected : collections.abc.Iterable[str]
        Distribution filenames that the release must contain.
    pypi_files : collections.abc.Mapping[str, PypiFile]
        PyPI Simple index entries.
    candidate_assets : collections.abc.Mapping[str, str or None]
        Candidate destination digests, or ``None`` when absent.
    candidate_name : str, default ``"GitHub Release"``
        Destination label used in diagnostics.

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
        candidate_digest = candidate_assets.get(name)
        if name not in candidate_assets:
            problems.append(f"{name} is missing from {candidate_name}")
        elif candidate_digest is None:
            problems.append(f"{name} has no {candidate_name} SHA-256 digest")
        elif candidate_digest != pypi_file.sha256:
            problems.append(
                f"{name} differs: PyPI sha256 {pypi_file.sha256}, "
                f"{candidate_name} sha256 {candidate_digest}"
            )
    return problems


def require_local_distribution_digests(
    distributions: cabc.Sequence[Path], index: cabc.Mapping[str, PypiFile]
) -> None:
    """Require local distributions to match the digests advertised by PyPI.

    Parameters
    ----------
    distributions : collections.abc.Sequence[pathlib.Path]
        The local wheel and source archive that would be released.
    index : collections.abc.Mapping[str, PypiFile]
        PyPI Simple-index entries for those distribution filenames.

    Raises
    ------
    ReleaseAssetError
        If any local distribution is absent from PyPI or has different bytes.
    """
    names = [path.name for path in distributions]
    local_digests = {path.name: sha256_file(path) for path in distributions}
    problems = digest_mismatches(names, index, local_digests, "local build")
    if problems:
        msg = "local release distributions differ from PyPI: " + "; ".join(problems)
        raise ReleaseAssetError(msg)


def require_github_release_digests(
    names: cabc.Iterable[str],
    index: cabc.Mapping[str, PypiFile],
    assets: cabc.Mapping[str, str | None],
    bundle_name: str,
) -> None:
    """Require release distributions to match PyPI and the bundle to exist.

    Parameters
    ----------
    names : collections.abc.Iterable[str]
        Distribution filenames expected on both destinations.
    index : collections.abc.Mapping[str, PypiFile]
        Canonical PyPI file metadata.
    assets : collections.abc.Mapping[str, str or None]
        GitHub Release asset digests.
    bundle_name : str
        Name of the required provenance bundle.

    Raises
    ------
    ReleaseAssetError
        If a distribution differs or the bundle is absent.
    """
    problems = digest_mismatches(names, index, assets)
    if problems:
        msg = "; ".join(problems)
        raise ReleaseAssetError(msg)
    if bundle_name not in assets:
        msg = f"the GitHub Release is missing {bundle_name}"
        raise ReleaseAssetError(msg)
