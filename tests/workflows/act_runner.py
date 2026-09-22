"""Run ``act`` against the CI workflow, and refuse a job it skipped.

Separated from the act integration tests for the reason
:mod:`tests.workflows.act_platforms` is: those tests probe for ``act`` and
Docker at import time and are excluded from CI, so the refusal of a skipped
job could not be tested where it needs to be. This module has no import-time
side effects, so a contract that runs on every pull request can drive
:func:`run_act` with a stand-in ``act`` and prove the refusal fires.
"""

from __future__ import annotations

import dataclasses as dc
import shutil
import subprocess
from pathlib import Path

from tests.workflows.act_platforms import (
    UNSUPPORTED_PLATFORM_MESSAGE,
    act_platform_arguments,
)

REPO_ROOT = Path(__file__).parent.parent.parent
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"

#: Runner labels mapped to container images for `act`, as arguments.
#:
#: The mapping itself lives in :mod:`tests.workflows.act_platforms`, which
#: has no import-time side effects, so the contract that guards it can run
#: in CI.
ACT_PLATFORMS = act_platform_arguments()


@dc.dataclass(frozen=True)
class ActConfig:
    """Configuration for running act."""

    event: str
    job: str
    event_path: Path
    artefact_dir: Path
    matrix: dict[str, str] = dc.field(default_factory=dict)
    dry_run: bool = False
    #: The ``act`` to run. ``None`` resolves it from ``PATH``; a test passes
    #: a stand-in, so the skip refusal is exercised where ``act`` is absent.
    act_executable: str | None = None


def run_act(config: ActConfig) -> tuple[int, Path, str]:
    """Run act with the specified configuration.

    A job ``act`` skipped because its runner label is unmapped fails with
    ``AssertionError``, raised by :func:`refuse_a_skipped_job`: ``act`` exits
    zero in that case, so every assertion the caller makes would be about a
    job that never ran.

    Parameters
    ----------
    config : ActConfig
        Configuration for the event, job, matrix values, and artefact directory.

    Returns
    -------
    tuple[int, Path, str]
        The exit code, artefact directory, and combined stdout/stderr logs.

    Raises
    ------
    FileNotFoundError
        If ``act`` is not available on ``PATH``.
    """
    config.artefact_dir.mkdir(parents=True, exist_ok=True)

    act_path = config.act_executable or shutil.which("act")
    if act_path is None:
        msg = "act executable not found in PATH"
        raise FileNotFoundError(msg)

    cmd = [
        act_path,
        config.event,
        "-j",
        config.job,
        "-e",
        str(config.event_path),
        *ACT_PLATFORMS,
        "--artifact-server-path",
        str(config.artefact_dir),
        "--json",
        "-b",
        "-W",
        str(WORKFLOW_PATH),
    ]

    for key, value in config.matrix.items():
        cmd.extend(["--matrix", f"{key}:{value}"])

    if config.dry_run:
        cmd.append("--list")

    completed = subprocess.run(  # noqa: S603
        cmd,
        text=True,
        capture_output=True,
        cwd=str(REPO_ROOT),
        check=False,
    )
    logs = completed.stdout + "\n" + completed.stderr
    refuse_a_skipped_job(config.job, completed.returncode, logs)
    return completed.returncode, config.artefact_dir, logs


def refuse_a_skipped_job(job: str, exit_code: int, logs: str) -> None:
    """Fail when ``act`` skipped the job instead of running it.

    ``act`` exits zero when it skips a job whose label it cannot map, so the
    exit code alone reads as success for a job that never ran.

    Parameters
    ----------
    job : str
        The job ``act`` was asked to run.
    exit_code : int
        What ``act`` exited with.
    logs : str
        Its combined output.

    Raises
    ------
    AssertionError
        If the output carries ``act``'s unsupported-platform message.
    """
    if UNSUPPORTED_PLATFORM_MESSAGE not in logs:
        return
    message = (
        f"act skipped {job} because its runner label is not mapped, and "
        f"exited {exit_code}. Every assertion below would then be about a job "
        "that never ran. Add the label to ACT_PLATFORM_IMAGES.\n"
        f"{logs}"
    )
    raise AssertionError(message)
