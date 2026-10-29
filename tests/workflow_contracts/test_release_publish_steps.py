"""Contracts for idempotent PyPI publication staging."""

from __future__ import annotations

import typing as typ

from tests.workflow_contracts.release_payloads import (
    SDIST as _SDIST,
)
from tests.workflow_contracts.release_payloads import (
    WHEEL as _WHEEL,
)
from tests.workflow_contracts.release_payloads import (
    simple_body as _index_body,
)
from tests.workflow_contracts.workflow_step_runner import run_named_workflow_step

if typ.TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _configure_stage(
    monkeypatch: pytest.MonkeyPatch,
    body: str,
    pypi_stage_paths: tuple[Path, Path, Path],
) -> tuple[Path, Path]:
    """Prepare the CLI environment and scripted published-name index."""
    distributions, staging, output = pypi_stage_paths
    distributions.mkdir()
    (distributions / _WHEEL).write_bytes(b"wheel")
    (distributions / _SDIST).write_bytes(b"sdist")
    monkeypatch.setenv("CURL_BODY", body)
    monkeypatch.setenv("CURL_STATUS", "200")
    return staging, output


def test_stage_pypi_keeps_only_distribution_names_absent_from_index(
    monkeypatch: pytest.MonkeyPatch,
    curl_argv_log: Path,
    pypi_stage_paths: tuple[Path, Path, Path],
) -> None:
    """The upload directory contains only files not already published."""
    staging, output = _configure_stage(
        monkeypatch, _index_body({_WHEEL: b"wheel"}), pypi_stage_paths
    )

    result = run_named_workflow_step(
        "release.yml", "publish-pypi", "Stage distributions not already on PyPI"
    )

    assert result.returncode == 0, "an index with a valid existing file must succeed"
    assert [path.name for path in staging.iterdir()] == [_SDIST], (
        "the existing wheel must be skipped and only the missing sdist staged"
    )
    assert output.read_text(encoding="utf-8") == "has-uploads=true\n", (
        "a remaining distribution must enable the PyPI publisher"
    )
    assert curl_argv_log.is_file(), "staging must query the Simple index"


def test_stage_pypi_succeeds_without_upload_when_all_names_exist(
    monkeypatch: pytest.MonkeyPatch,
    curl_argv_log: Path,
    pypi_stage_paths: tuple[Path, Path, Path],
) -> None:
    """A replay with every filename published yields an empty upload set."""
    staging, output = _configure_stage(
        monkeypatch,
        _index_body({_WHEEL: b"wheel", _SDIST: b"sdist"}),
        pypi_stage_paths,
    )

    result = run_named_workflow_step(
        "release.yml", "publish-pypi", "Stage distributions not already on PyPI"
    )

    assert result.returncode == 0, "a no-op publication re-run must succeed"
    assert not list(staging.iterdir()), "already published files must not be staged"
    assert output.read_text(encoding="utf-8") == "has-uploads=false\n", (
        "an empty remainder must disable the upload action"
    )
    assert curl_argv_log.is_file(), "the no-op check must still query the Simple index"
