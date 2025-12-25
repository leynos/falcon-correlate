"""Pytest configuration for workflow integration tests.

These tests require act and Docker to be available. They are excluded from
the normal test suite and should be run manually when making workflow changes.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    )


def _check_tool_available(tool_name: str, args: list[str]) -> bool:
    """Check if a tool is available by running it with given args.

    Args:
        tool_name: Name of the tool to find in PATH.
        args: Arguments to pass to the tool.

    Returns:
        True if the tool is available and runs successfully.

    """
    tool_path = shutil.which(tool_name)
    if tool_path is None:
        return False
    result = subprocess.run(  # noqa: S603
        [tool_path, *args],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


@pytest.fixture(scope="session")
def act_available() -> bool:
    """Check if act is available."""
    return _check_tool_available("act", ["--version"])


@pytest.fixture(scope="session")
def docker_available() -> bool:
    """Check if Docker is available."""
    return _check_tool_available("docker", ["info"])
