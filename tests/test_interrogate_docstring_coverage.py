"""Tests for the Interrogate docstring coverage gate."""

from __future__ import annotations

import re
import subprocess  # ruff: ignore[suspicious-subprocess-import] - tests intentionally validate a CLI boundary.
import sys
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
# Keep in step with the literal ``--fail-under`` argument below, which stays
# literal so Ruff's S603 rule can still see a fully static command.
_EXPECTED_COVERAGE_PERCENT = 100.0
# Interrogate reports its own version in some runs, and any part of that string
# may change between releases, so redact dotted versions before comparison.
_INTERROGATE_VERSION_PATTERN = re.compile(r"\bv?\d+\.\d+\.\d+\w*")
_INTERROGATE_DURATION_PATTERN = re.compile(r"\b\d+\.\d+s\b")
_INTERROGATE_WHITESPACE_PATTERN = re.compile(r"[^\S\n]+")
_INTERROGATE_RESULT_PATTERN = re.compile(
    r"RESULT:\s*(?P<status>\w+)\s*"
    r"\(\s*minimum:\s*(?P<minimum>\d+(?:\.\d+)?)\s*%\s*,\s*"
    r"actual:\s*(?P<actual>\d+(?:\.\d+)?)\s*%\s*\)",
)


def _normalize_interrogate_output(output: str) -> str:
    """Redact nondeterministic Interrogate output fields and collapse spacing."""
    redacted = _INTERROGATE_VERSION_PATTERN.sub("<version>", output.strip())
    redacted = _INTERROGATE_DURATION_PATTERN.sub("<duration>", redacted)
    collapsed = _INTERROGATE_WHITESPACE_PATTERN.sub(" ", redacted)
    return "\n".join(line.strip() for line in collapsed.splitlines())


def _parse_interrogate_result(stdout: str) -> tuple[str, float, float]:
    """Return the status and coverage percentages from normalised Interrogate stdout."""
    normalized = _normalize_interrogate_output(stdout)
    match = _INTERROGATE_RESULT_PATTERN.search(normalized)
    assert match is not None, normalized
    return match["status"].upper(), float(match["minimum"]), float(match["actual"])


def _assert_interrogate_result_meets_gate(stdout: str) -> None:
    """Assert that the reported result satisfies the coverage gate."""
    status, minimum, actual = _parse_interrogate_result(stdout)
    output = _normalize_interrogate_output(stdout)
    assert status == "PASSED", f"expected status 'PASSED', got {status!r} in:\n{output}"
    failure_message = (
        f"expected minimum {_EXPECTED_COVERAGE_PERCENT}, got {minimum} in:\n{output}"
    )
    assert minimum == _EXPECTED_COVERAGE_PERCENT, failure_message
    failure_message = (
        f"expected actual {_EXPECTED_COVERAGE_PERCENT}, got {actual} in:\n{output}"
    )
    assert actual == _EXPECTED_COVERAGE_PERCENT, failure_message


def test_interrogate_reports_full_package_docstring_coverage() -> None:
    """Interrogate should enforce the package's 100 percent coverage gate."""
    result = subprocess.run(
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
    _assert_interrogate_result_meets_gate(result.stdout)


@pytest.mark.parametrize(
    "stdout",
    [
        "interrogate, version 1.7.0\nRESULT: PASSED (minimum: 100.0%, actual: 100.0%)",
        (
            "interrogate, version v1.8.0rc1\n"
            "RESULT: PASSED (minimum: 100.0%, actual: 100.0%)"
        ),
        "RESULT:   PASSED  ( minimum:  100.0 % ,  actual:  100.0 % )",
        "Finished in 1.25s\nRESULT: PASSED (minimum: 100.0%, actual: 100.0%)",
        "RESULT: PASSED (minimum: 100%, actual: 100%)",
        "RESULT: PASSED (minimum: 100.00%, actual: 100.00%)",
        "---------- RESULT: PASSED (minimum: 100.0%, actual: 100.0%) ----------",
    ],
)
def test_interrogate_result_parser_tolerates_cosmetic_variation(stdout: str) -> None:
    """Cosmetic output changes must not affect the parsed gate values."""
    expected_result = ("PASSED", _EXPECTED_COVERAGE_PERCENT, _EXPECTED_COVERAGE_PERCENT)
    parsed_result = _parse_interrogate_result(stdout)
    failure_message = f"expected {expected_result}, got {parsed_result} from {stdout!r}"
    assert parsed_result == expected_result, failure_message


@pytest.mark.parametrize(
    "stdout",
    [
        "RESULT: FAILED (minimum: 100.0%, actual: 99.9%)",
        "RESULT: PASSED (minimum: 100.0%, actual: 99.0%)",
        "RESULT: PASSED (minimum: 99.0%, actual: 100.0%)",
        "RESULT: FAILED (minimum: 100%, actual: 100%)",
    ],
)
def test_interrogate_result_parser_rejects_semantic_differences(stdout: str) -> None:
    """Semantic changes must survive normalisation and fail the gate values."""
    with pytest.raises(AssertionError):
        _assert_interrogate_result_meets_gate(stdout)


def test_normalize_interrogate_output_redacts_and_preserves_lines() -> None:
    """Redact volatile fields while retaining percentage values and line breaks."""
    output = "  interrogate  v1.8.0rc1\t finished in 1.25s  \n  actual: 100.0%  "
    assert _normalize_interrogate_output(output) == (
        "interrogate <version> finished in <duration>\nactual: 100.0%"
    ), "volatile fields and spacing should be normalised"


@given(
    version=st.tuples(*(st.integers(min_value=0, max_value=999),) * 3),
    duration=st.tuples(
        st.integers(min_value=0, max_value=999), st.integers(min_value=0, max_value=999)
    ),
    space=st.sampled_from([" ", "  ", "\t", " \t "]),
    result=st.tuples(
        st.integers(min_value=0, max_value=5), st.sampled_from(["PASSED", "FAILED"])
    ),
)
def test_interrogate_format_variations_preserve_result(
    version: tuple[int, int, int],
    duration: tuple[int, int],
    space: str,
    result: tuple[int, str],
) -> None:
    """Generated cosmetic changes preserve the status and coverage values."""
    decimals, status = result
    version_text = ".".join(map(str, version))
    percent = "100" + ("." + "0" * decimals if decimals else "")
    stdout = (
        f"interrogate v{version_text}\nFinished in {duration[0]}.{duration[1]}s\n"
        f"RESULT:{space}{status}{space}(minimum:{space}{percent}{space}%,"
        f"{space}actual:{space}{percent}{space}%)"
    )
    assert _parse_interrogate_result(stdout) == (status, 100.0, 100.0), stdout
