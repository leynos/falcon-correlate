"""Contract: ``run_act`` refuses a job ``act`` skipped, and only that.

``act`` skips a job whose runner label it cannot map, prints ``Skipping
unsupported platform`` and exits zero, so the act integration tests would
assert against a job that never ran. ``run_act`` turns that into a failure.
The integration tests are excluded from CI, so the refusal is proved here
with a stand-in ``act`` that prints what the real one would, rather than
left to be noticed the next time someone runs act by hand.
"""

from __future__ import annotations

import stat
import typing as typ

import pytest

from tests.workflows.act_platforms import UNSUPPORTED_PLATFORM_MESSAGE
from tests.workflows.act_runner import ActConfig, run_act

if typ.TYPE_CHECKING:
    from pathlib import Path


def _stand_in_act(directory: Path, output: str, exit_code: int) -> str:
    """Write an executable that prints ``output`` and exits ``exit_code``."""
    script = directory / "act"
    script.write_text(f"#!/bin/sh\nprintf '%s\\n' '{output}'\nexit {exit_code}\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return str(script)


def _config(tmp_path: Path, act: str) -> ActConfig:
    """Return a configuration that runs ``act`` for the ``lint`` job."""
    return ActConfig(
        event="pull_request",
        job="lint",
        event_path=tmp_path / "event.json",
        artefact_dir=tmp_path / "artefacts",
        act_executable=act,
    )


class TestRunAct:
    """The skip refusal fires on the skip message and nowhere else."""

    def test_a_skipped_job_is_refused_although_act_exited_zero(
        self, tmp_path: Path
    ) -> None:
        """Exit zero is what makes the skip invisible, so the case uses it."""
        output = f"[CI/lint] {UNSUPPORTED_PLATFORM_MESSAGE}: ubicloud-standard-2"
        act = _stand_in_act(tmp_path, output, exit_code=0)

        with pytest.raises(AssertionError) as raised:
            run_act(_config(tmp_path, act))

        message = str(raised.value)
        for expected in ("lint", "exited 0", "ACT_PLATFORM_IMAGES", output):
            assert expected in message, (
                f"the refusal must carry {expected!r}; got {message!r}"
            )

    def test_a_job_that_ran_is_returned_whatever_it_exited(
        self, tmp_path: Path
    ) -> None:
        """A failing job that ran is the caller's to judge, not a skip."""
        act = _stand_in_act(tmp_path, "[CI/lint] job failed", exit_code=3)

        code, artefacts, logs = run_act(_config(tmp_path, act))

        assert code == 3, f"run_act must return act's exit code; got {code}"
        assert artefacts == tmp_path / "artefacts", (
            f"run_act must return the artefact directory; got {artefacts}"
        )
        assert "job failed" in logs, f"run_act must return the logs; got {logs!r}"
