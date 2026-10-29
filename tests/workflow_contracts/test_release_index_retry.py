"""Contracts for PyPI index propagation during release publication."""

from __future__ import annotations

import json
import typing as typ

import pytest

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    from pathlib import Path


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
    WHEEL as _WHEEL,
)
from tests.workflow_contracts.release_payloads import (
    release_view as _release_view,
)
from tests.workflow_contracts.release_payloads import (
    simple_body as _index_body,
)
from tests.workflow_contracts.workflow_step_runner import run_named_workflow_step


class TestIndexRetry:
    """Contracts for index retry."""

    @pytest.fixture(autouse=True)
    def _configure_publish_fixture(
        self, configure_publish: cabc.Callable[..., None]
    ) -> None:
        """Share the release setup with tests in this class."""
        self.configure_publish = configure_publish

    def test_publish_retries_until_pypi_indexes_newly_uploaded_files(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        curl_argv_log: Path,
        gh_argv_log: Path,
    ) -> None:
        """The release step waits briefly when PyPI's index initially lags."""
        pypi_files = {_WHEEL: b"wheel", _SDIST: b"sdist"}
        self.configure_publish(pypi_files, local_files=pypi_files)
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
        assert "PyPI index HTTP 404; retry 1/12" in result.stdout, (
            "the retry log must identify the index status and attempt"
        )
        assert "Retry delay: 5s" in result.stdout, (
            "the retry log must show the configured delay"
        )
        curl_calls = [
            json.loads(line) for line in curl_argv_log.read_text().splitlines()
        ]
        assert len(curl_calls) == 2, (
            "the release step must retry a missing index before accepting its files"
        )
        assert gh_argv_log.is_file(), (
            "reconciliation must continue after the index updates"
        )
