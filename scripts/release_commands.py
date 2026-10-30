"""Run external release commands and download PyPI files within bounds.

The release CLI shells out to ``curl`` and ``gh`` with fixed argument vectors.
Keeping that process boundary in one module lets workflow contract tests stub
the commands, and gives the PyPI download its own subprocess deadline.
"""

from __future__ import annotations

import subprocess  # ruff: ignore[suspicious-subprocess-import] - fixed argv keeps PATH stand-ins interceptable without a shell.
import typing as typ

if __package__:
    from scripts.release_assets import PypiFile, ReleaseAssetError, sha256_file
    from scripts.release_curl import PYPI_DOWNLOAD_CURL_ARGUMENTS
else:
    from release_assets import PypiFile, ReleaseAssetError, sha256_file
    from release_curl import PYPI_DOWNLOAD_CURL_ARGUMENTS

if typ.TYPE_CHECKING:
    from pathlib import Path

# Curl bounds one transfer (``--max-time 300``) and its retries
# (``--retry-max-time 300``). This whole-subprocess deadline sits above both and
# still leaves a small margin for process setup and reaping.
PYPI_DOWNLOAD_DEADLINE_SECONDS = 330


def run_command(
    arguments: list[str], *, timeout: float | None = None
) -> subprocess.CompletedProcess[str]:
    """Run one external command without a shell and capture both streams."""
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - fixed argv keeps PATH stand-ins interceptable without a shell.
        arguments,
        capture_output=True,
        check=False,
        text=True,
        timeout=timeout,
    )


def require_success(result: subprocess.CompletedProcess[str], command: str) -> None:
    """Raise with the command's captured diagnostic on failure."""
    if result.returncode == 0:
        return
    detail = result.stderr.strip() or result.stdout.strip() or "no diagnostic"
    msg = f"{command} failed with exit {result.returncode}: {detail}"
    raise ReleaseAssetError(msg)


def download_pypi_file(file: PypiFile, destination: Path) -> None:
    """Download one canonical PyPI file and verify its advertised digest."""
    try:
        result = run_command(
            [*PYPI_DOWNLOAD_CURL_ARGUMENTS, str(destination), file.url],
            timeout=PYPI_DOWNLOAD_DEADLINE_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        msg = (
            f"curl PyPI file download exceeded the {PYPI_DOWNLOAD_DEADLINE_SECONDS}s "
            f"deadline for {file.url}"
        )
        raise ReleaseAssetError(msg) from error
    require_success(result, "curl PyPI file download")
    actual = sha256_file(destination)
    if actual != file.sha256:
        msg = (
            f"{destination.name} download sha256 {actual} does not match PyPI "
            f"sha256 {file.sha256}"
        )
        raise ReleaseAssetError(msg)
