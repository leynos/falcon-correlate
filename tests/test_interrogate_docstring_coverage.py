"""Tests for the Interrogate docstring coverage gate."""

from __future__ import annotations

import re
import subprocess  # noqa: S404 - tests intentionally validate a CLI boundary.
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_INTERROGATE_RESULT_PATTERN = re.compile(
    r"RESULT:\s+(?P<status>\w+)\s+"
    r"\(minimum:\s+(?P<minimum>\d+\.\d+)%,\s+"
    r"actual:\s+(?P<actual>\d+\.\d+)%\)",
)


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
    result_match = _INTERROGATE_RESULT_PATTERN.search(result.stdout)
    assert result_match is not None, result.stdout
    assert result_match["status"] == "PASSED"
    assert result_match["minimum"] == "100.0"
    assert result_match["actual"] == "100.0"
