"""Contracts for verification of PyPI downloads before GitHub publication."""

from __future__ import annotations

import json
import typing as typ

from tests.workflow_contracts.release_payloads import (
    BUNDLE,
    BUNDLE_BYTES,
    SDIST,
    WHEEL,
    release_view,
)
from tests.workflow_contracts.test_release_reconciliation import _configure_publish
from tests.workflow_contracts.workflow_step_runner import run_named_workflow_step

if typ.TYPE_CHECKING:
    from pathlib import Path

    import pytest


class TestDownloadIntegrity:
    """Downloaded release assets must match the Simple index digest."""

    def test_corrupt_pypi_bytes_stop_upload_and_publication(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        curl_argv_log: Path,
        gh_argv_log: Path,
    ) -> None:
        """A corrupt download cannot reach a draft release or publish it."""
        pypi_bytes = {WHEEL: b"canonical wheel", SDIST: b"canonical sdist"}
        _configure_publish(tmp_path, monkeypatch, pypi_bytes)
        view = release_view({**pypi_bytes, BUNDLE: BUNDLE_BYTES}, (WHEEL, BUNDLE))
        monkeypatch.setenv(
            "GH_RESPONSES", json.dumps([{"stdout": view}, {"stdout": view}])
        )
        monkeypatch.setenv(
            "CURL_DOWNLOAD_CONTENTS",
            json.dumps({f"https://files.pythonhosted.org/{SDIST}": "corrupt sdist"}),
        )

        result = run_named_workflow_step(
            "release.yml", "publish-release", "Reconcile and publish the GitHub Release"
        )

        assert result.returncode == 1, "corrupt PyPI bytes must fail publication"
        assert "download sha256" in result.stderr, (
            "the digest mismatch must be reported"
        )
        curl_calls = [
            json.loads(line) for line in curl_argv_log.read_text().splitlines()
        ]
        assert any("--output" in call for call in curl_calls), (
            "the test must exercise an actual PyPI download"
        )
        gh_calls = [json.loads(line) for line in gh_argv_log.read_text().splitlines()]
        assert not any(call[:2] == ["release", "upload"] for call in gh_calls), (
            "corrupt bytes must never be uploaded"
        )
        assert not any(call[:2] == ["release", "edit"] for call in gh_calls), (
            "a release with corrupt bytes must remain unpublished"
        )
