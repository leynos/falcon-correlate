#!/usr/bin/env -S uv run python
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Run the release workflow's distribution checks and reconciliation steps."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import] - workflow tests intercept PATH commands.
import sys
import time
import typing as typ
from pathlib import Path

if __package__:
    from scripts.release_assets import (
        PypiFile,
        ReleaseAssetError,
        collect_distributions,
        digest_mismatches,
        parse_github_asset_digests,
        parse_pep691_index,
        sha256_file,
    )
else:
    from release_assets import (
        PypiFile,
        ReleaseAssetError,
        collect_distributions,
        digest_mismatches,
        parse_github_asset_digests,
        parse_pep691_index,
        sha256_file,
    )

if typ.TYPE_CHECKING:
    import collections.abc as cabc

_SIMPLE_ACCEPT = "application/vnd.pypi.simple.v1+json"
_INDEX_ATTEMPTS = 6


def _required(name: str) -> str:
    """Return a required workflow environment value."""
    value = os.environ.get(name)
    if value is None or not value.strip():
        msg = f"required environment variable {name} is missing"
        raise ReleaseAssetError(msg)
    return value


def _run(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    """Run one external command without a shell and capture both streams."""
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - fixed argv keeps PATH stand-ins interceptable without a shell.
        arguments,
        capture_output=True,
        check=False,
        text=True,
    )


def _require_success(result: subprocess.CompletedProcess[str], command: str) -> None:
    """Raise with the command's captured diagnostic on failure."""
    if result.returncode == 0:
        return
    detail = result.stderr.strip() or result.stdout.strip() or "no diagnostic"
    msg = f"{command} failed with exit {result.returncode}: {detail}"
    raise ReleaseAssetError(msg)


def _clear_directory(directory: Path) -> None:
    """Create an empty staging directory, refusing nested stale entries."""
    directory.mkdir(parents=True, exist_ok=True)
    for entry in directory.iterdir():
        if entry.is_dir():
            msg = f"staging directory contains a nested entry: {entry}"
            raise ReleaseAssetError(msg)
        entry.unlink()


def _copy_distributions(source: Path, destination: Path) -> None:
    """Validate a source directory and copy its distributions into a clean one."""
    files = collect_distributions(source)
    if source.resolve() == destination.resolve():
        return
    _clear_directory(destination)
    for path in files:
        shutil.copyfile(path, destination / path.name)


def _fetch_index_once(url: str) -> tuple[int, str]:
    """Fetch one PEP 691 index response and return its status and body."""
    result = _run([
        "curl",
        "--silent",
        "--show-error",
        "--location",
        "--retry",
        "5",
        "--retry-all-errors",
        "--retry-delay",
        "2",
        "--retry-max-time",
        "90",
        "--connect-timeout",
        "10",
        "--max-time",
        "30",
        "--write-out",
        "\\n%{http_code}",
        "--header",
        f"Accept: {_SIMPLE_ACCEPT}",
        url,
    ])
    if result.returncode != 0:
        _require_success(result, "curl Simple index request")
    try:
        body, status_text = result.stdout.rsplit("\n", maxsplit=1)
        status = int(status_text)
    except (ValueError, TypeError) as error:
        msg = "curl did not report an HTTP status for the Simple index"
        raise ReleaseAssetError(msg) from error
    return status, body


def _read_index(url: str, expected: cabc.Collection[str] = ()) -> dict[str, PypiFile]:
    """Read PyPI's index, polling briefly when a just-uploaded file is absent."""
    expected_names = set(expected)
    for attempt in range(_INDEX_ATTEMPTS):
        status, body = _fetch_index_once(url)
        match status:
            case 404:
                index: dict[str, PypiFile] = {}
            case 200:
                index = parse_pep691_index(body, url)
            case _:
                msg = f"PyPI Simple index returned HTTP {status}"
                raise ReleaseAssetError(msg)
        if not expected_names or expected_names <= index.keys():
            return index
        if attempt + 1 < _INDEX_ATTEMPTS:
            time.sleep(2)
    absent = sorted(expected_names - index.keys())
    msg = f"PyPI Simple index did not list expected release files: {absent}"
    raise ReleaseAssetError(msg)


def _write_output(name: str, value: str) -> None:
    """Append one scalar value to the GitHub Actions output file."""
    with Path(_required("GITHUB_OUTPUT")).open("a", encoding="utf-8") as output:
        output.write(f"{name}={value}\n")


def _collect() -> None:
    """Validate and stage the build artifact for attestation."""
    source = Path(_required("SOURCE_DIR"))
    destination = Path(_required("DIST_DIR"))
    _copy_distributions(source, destination)
    print(f"Collected {len(collect_distributions(destination))} release artefacts.")


def _stage_pypi() -> None:
    """Stage only distributions PyPI's Simple index does not already list."""
    distributions = collect_distributions(Path(_required("DIST_DIR")))
    index = _read_index(_required("SIMPLE_INDEX_URL"))
    destination = Path(_required("STAGING_DIR"))
    _clear_directory(destination)
    remaining = [path for path in distributions if path.name not in index]
    for path in remaining:
        shutil.copyfile(path, destination / path.name)
    _write_output("has-uploads", str(bool(remaining)).lower())
    if remaining:
        print(f"Staged {len(remaining)} distribution(s) for PyPI.")
    else:
        print("Every distribution is already on PyPI; skipping the upload.")


def _ensure_draft() -> None:
    """Create a draft release only when the tag has no release yet."""
    collect_distributions(Path(_required("DIST_DIR")))
    tag = _required("RELEASE_TAG")
    view = _run(["gh", "release", "view", tag, "--json", "tagName"])
    if view.returncode == 0:
        print(f"Reusing the existing release for {tag}.")
        return
    diagnostic = f"{view.stdout}\n{view.stderr}".casefold()
    if "not found" not in diagnostic and "404" not in diagnostic:
        _require_success(view, "gh release view")
    create = _run([
        "gh",
        "release",
        "create",
        tag,
        "--draft",
        "--verify-tag",
        "--generate-notes",
        "--title",
        tag,
    ])
    _require_success(create, "gh release create")
    print(f"Created a draft release for {tag}.")


def _release_assets(tag: str) -> dict[str, str | None]:
    """Read release asset names and digests with the GitHub CLI."""
    result = _run(["gh", "release", "view", tag, "--json", "assets"])
    _require_success(result, "gh release view")
    return parse_github_asset_digests(result.stdout)


def _download_pypi_file(file: PypiFile, destination: Path) -> None:
    """Download one canonical PyPI file and verify its advertised digest."""
    result = _run([
        "curl",
        "--silent",
        "--show-error",
        "--location",
        "--fail",
        "--retry",
        "5",
        "--retry-all-errors",
        "--retry-delay",
        "2",
        "--connect-timeout",
        "10",
        "--max-time",
        "300",
        "--output",
        str(destination),
        file.url,
    ])
    _require_success(result, "curl PyPI file download")
    actual = sha256_file(destination)
    if actual != file.sha256:
        msg = (
            f"{destination.name} download sha256 {actual} does not match PyPI "
            f"sha256 {file.sha256}"
        )
        raise ReleaseAssetError(msg)


def _check_existing_asset_digests(
    names: cabc.Iterable[str],
    index: cabc.Mapping[str, PypiFile],
    assets: cabc.Mapping[str, str | None],
) -> None:
    """Refuse existing GitHub bytes that disagree with PyPI's canonical files."""
    for name in names:
        if name in assets and assets[name] != index[name].sha256:
            msg = (
                f"{name} already exists on GitHub with a digest that differs from PyPI"
            )
            raise ReleaseAssetError(msg)


def _stage_release_gaps(
    names: cabc.Iterable[str],
    index: cabc.Mapping[str, PypiFile],
    assets: cabc.Mapping[str, str | None],
    bundle: Path,
) -> None:
    """Download PyPI's missing release bytes and stage the tag bundle if absent."""
    tag = _required("RELEASE_TAG")
    upload_dir = Path(_required("STAGING_DIR"))
    _clear_directory(upload_dir)
    upload_paths: list[Path] = []
    for name in names:
        if name not in assets:
            downloaded = upload_dir / name
            _download_pypi_file(index[name], downloaded)
            upload_paths.append(downloaded)
    if bundle.name not in assets:
        staged_bundle = upload_dir / bundle.name
        shutil.copyfile(bundle, staged_bundle)
        upload_paths.append(staged_bundle)

    if upload_paths:
        upload = _run(["gh", "release", "upload", tag, *map(str, upload_paths)])
        _require_success(upload, "gh release upload")
    else:
        print("The release already holds every distribution and its bundle.")


def _reconcile_release_assets(
    tag: str,
    names: cabc.Iterable[str],
    index: cabc.Mapping[str, PypiFile],
    bundle: Path,
) -> dict[str, str | None]:
    """Upload only missing names and return the release's refreshed asset map."""
    assets = _release_assets(tag)
    _check_existing_asset_digests(names, index, assets)
    _stage_release_gaps(names, index, assets, bundle)
    return _release_assets(tag)


def _publish_release() -> None:
    """Reconcile GitHub assets with PyPI bytes, verify digests, then publish."""
    distributions = collect_distributions(Path(_required("DIST_DIR")))
    tag = _required("RELEASE_TAG")
    names = [path.name for path in distributions]
    bundle = Path(_required("BUNDLE_DIR")) / f"{tag}.sigstore.json"
    if not bundle.is_file():
        msg = f"the tag's Sigstore bundle is missing: {bundle}"
        raise ReleaseAssetError(msg)

    index = _read_index(_required("SIMPLE_INDEX_URL"), names)
    verified_assets = _reconcile_release_assets(tag, names, index, bundle)
    problems = digest_mismatches(names, index, verified_assets)
    if problems:
        msg = "; ".join(problems)
        raise ReleaseAssetError(msg)
    if bundle.name not in verified_assets:
        msg = f"the GitHub Release is missing {bundle.name}"
        raise ReleaseAssetError(msg)

    prerelease = _required("PRERELEASE").lower()
    if prerelease not in {"true", "false"}:
        msg = "PRERELEASE must be either true or false"
        raise ReleaseAssetError(msg)
    publish = _run([
        "gh",
        "release",
        "edit",
        tag,
        "--draft=false",
        f"--prerelease={prerelease}",
    ])
    _require_success(publish, "gh release edit")
    print(f"Published release {tag} with PyPI's distribution bytes.")


def _parser() -> argparse.ArgumentParser:
    """Create the small command selector used by the workflow steps."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "command",
        choices=("collect", "stage-pypi", "ensure-draft", "publish-release"),
    )
    return parser


def _main(argv: cabc.Sequence[str] | None = None) -> int:
    """Run a release helper command and report failures as workflow annotations."""
    args = _parser().parse_args(argv)
    try:
        match args.command:
            case "collect":
                _collect()
            case "stage-pypi":
                _stage_pypi()
            case "ensure-draft":
                _ensure_draft()
            case "publish-release":
                _publish_release()
    except (OSError, ReleaseAssetError, ValueError) as error:
        print(f"::error title=release-assets::{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
