"""Contracts for PyPI index propagation during release publication."""

from __future__ import annotations

import json
import typing as typ

if typ.TYPE_CHECKING:
    from pathlib import Path

    import pytest

from tests.workflow_contracts.release_payloads import (
    BUNDLE as _BUNDLE,
)
from tests.workflow_contracts.release_payloads import (
    BUNDLE_BYTES as _BUNDLE_BYTES,
)
from tests.workflow_contracts.release_payloads import (
    SDIST as _SDIST,
)
from tests.workflow_contracts.release_payloads import (
    SIMPLE_URL as _SIMPLE_URL,
)
from tests.workflow_contracts.release_payloads import (
    TAG as _TAG,
)
from tests.workflow_contracts.release_payloads import (
    WHEEL as _WHEEL,
)
from tests.workflow_contracts.release_payloads import (
    release_view as _release_view,
)
from tests.workflow_contracts.release_payloads import (
    simple_body as _index_body,
)
from tests.workflow_contracts.workflow_step_runner import run_named_workflow_step


def test_publish_retries_until_pypi_indexes_newly_uploaded_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    curl_argv_log: Path,
    gh_argv_log: Path,
) -> None:
    """The release step waits briefly when PyPI's index initially lags."""
    distributions = tmp_path / "dist"
    distributions.mkdir()
    pypi_files = {_WHEEL: b"wheel", _SDIST: b"sdist"}
    for name, contents in pypi_files.items():
        (distributions / name).write_bytes(contents)

    bundle_directory = tmp_path / "bundle"
    bundle_directory.mkdir()
    (bundle_directory / _BUNDLE).write_bytes(_BUNDLE_BYTES)

    monkeypatch.setenv("DIST_DIR", str(distributions))
    monkeypatch.setenv("RELEASE_TAG", _TAG)
    monkeypatch.setenv("SIMPLE_INDEX_URL", _SIMPLE_URL)
    monkeypatch.setenv("BUNDLE_DIR", str(bundle_directory))
    monkeypatch.setenv("STAGING_DIR", str(tmp_path / "staging"))
    monkeypatch.setenv("PRERELEASE", "false")
    monkeypatch.setenv(
        "CURL_RESPONSES",
        json.dumps([
            {"status": "404"},
            {"status": "200", "body": _index_body(pypi_files)},
        ]),
    )
    assets = {**pypi_files, _BUNDLE: _BUNDLE_BYTES}
    view = _release_view(assets)
    monkeypatch.setenv(
        "GH_RESPONSES",
        json.dumps([{"stdout": view}, {"stdout": view}, {"stdout": view}, {}]),
    )

    result = run_named_workflow_step(
        "release.yml", "publish-release", "Reconcile and publish the GitHub Release"
    )

    assert result.returncode == 0, (
        f"a delayed Simple-index update must still publish: {result.stderr}"
    )
    curl_calls = [json.loads(line) for line in curl_argv_log.read_text().splitlines()]
    assert len(curl_calls) == 2, (
        "the release step must retry a missing index before accepting its files"
    )
    assert gh_argv_log.is_file(), "reconciliation must continue after the index updates"
