"""Tests for the Interrogate docstring coverage gate."""

from __future__ import annotations

import subprocess  # noqa: S404 - tests intentionally validate a CLI boundary.
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_EXPECTED_INTERROGATE_RESULT = "RESULT: PASSED (minimum: 100.0%, actual: 100.0%)"


def test_interrogate_reports_full_package_docstring_coverage() -> None:
    """Interrogate should enforce the package's 100 percent coverage gate."""
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "interrogate",
            "--fail-under",
            "100",
            "src/falcon_correlate",
        ],
        cwd=_PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == _EXPECTED_INTERROGATE_RESULT
