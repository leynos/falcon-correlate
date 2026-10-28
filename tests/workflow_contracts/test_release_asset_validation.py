"""Contracts for release distribution and GitHub metadata validation."""

from __future__ import annotations

import json
import typing as typ

import pytest

from scripts import release_assets
from tests.workflow_contracts.release_payloads import (
    BUNDLE as _BUNDLE,
)
from tests.workflow_contracts.release_payloads import (
    SDIST as _SDIST,
)
from tests.workflow_contracts.release_payloads import (
    WHEEL as _WHEEL,
)
from tests.workflow_contracts.workflow_step_runner import run_named_workflow_step

if typ.TYPE_CHECKING:
    from pathlib import Path


class TestDistributionCollection:
    """Contracts for distribution collection."""

    @pytest.mark.parametrize(
        "invalid_set",
        [
            ((), "empty release artefact set"),
            ((_WHEEL,), "exactly one source distribution"),
            ((_WHEEL, _SDIST, "falcon_correlate-1.1.0.tar.gz"), "exactly one"),
            ((_WHEEL, _SDIST, "README.txt"), "unknown release entries"),
        ],
        ids=["empty", "missing-sdist", "duplicate-sdist", "unknown-file"],
    )
    def test_collect_command_rejects_invalid_distribution_sets(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        invalid_set: tuple[tuple[str, ...], str],
    ) -> None:
        """The workflow entry point rejects an empty, incomplete or unknown set."""
        entries, expected_message = invalid_set
        source = tmp_path / "source"
        source.mkdir()
        for name in entries:
            (source / name).write_bytes(b"distribution")
        monkeypatch.setenv("SOURCE_DIR", str(source))
        monkeypatch.setenv("DIST_DIR", str(tmp_path / "dist"))

        result = run_named_workflow_step(
            "release.yml", "attest", "Collect and validate release distributions"
        )

        assert result.returncode == 1, "invalid distribution sets must fail collection"
        assert expected_message in result.stderr, (
            "the failure annotation must explain the rejected distribution set"
        )

    def test_collect_command_copies_every_wheel_and_one_sdist(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Collection carries all wheels and the only source archive forward."""
        source = tmp_path / "source"
        source.mkdir()
        names = (_WHEEL, "falcon_correlate-1.2.0-py2.py3-none-any.whl", _SDIST)
        for name in names:
            (source / name).write_bytes(name.encode())
        destination = tmp_path / "dist"
        monkeypatch.setenv("SOURCE_DIR", str(source))
        monkeypatch.setenv("DIST_DIR", str(destination))

        result = run_named_workflow_step(
            "release.yml", "attest", "Collect and validate release distributions"
        )

        assert result.returncode == 0, "a complete distribution set must be collected"
        assert sorted(path.name for path in destination.iterdir()) == sorted(names), (
            "collection must preserve every wheel and the source archive"
        )


class TestGitHubDigestParsing:
    """Contracts for git hub digest parsing."""

    def test_parse_github_assets_extracts_valid_and_missing_digests(self) -> None:
        """GitHub asset parsing preserves names and represents unavailable hashes."""
        body = json.dumps({
            "assets": [
                {"name": _WHEEL, "digest": f"sha256:{'a' * 64}"},
                {"name": _SDIST},
            ]
        })

        assets = release_assets.parse_github_asset_digests(body)

        assert assets == {_WHEEL: "a" * 64, _SDIST: None}, (
            "valid digests and missing digest values must be represented distinctly"
        )

    @pytest.mark.parametrize(
        "body",
        [
            '{"assets": ["not-an-object"]}',
            json.dumps({"assets": [{"name": _WHEEL}, {"name": _WHEEL}]}),
            '{"assets": {}}',
        ],
        ids=["asset-entry-shape", "duplicate-name", "assets-shape"],
    )
    def test_parse_github_assets_rejects_malformed_responses(self, body: str) -> None:
        """Malformed release data cannot silently suppress an upload."""
        with pytest.raises(release_assets.ReleaseAssetError):
            release_assets.parse_github_asset_digests(body)


class TestFinalReleaseValidation:
    """Contracts for final release validation."""

    @pytest.mark.parametrize(
        ("missing_name", "message"),
        [
            (_SDIST, "missing from GitHub Release"),
            (_BUNDLE, "GitHub Release is missing"),
        ],
        ids=["missing-distribution", "missing-bundle"],
    )
    def test_final_release_validation_rejects_missing_assets(
        self, missing_name: str, message: str
    ) -> None:
        """A release cannot be finalized without both distributions and provenance."""
        index = {
            _WHEEL: release_assets.PypiFile("a" * 64, "https://example.org/wheel"),
            _SDIST: release_assets.PypiFile("b" * 64, "https://example.org/sdist"),
        }
        assets: dict[str, str | None] = {
            _WHEEL: "a" * 64,
            _SDIST: "b" * 64,
            _BUNDLE: None,
        }
        del assets[missing_name]

        with pytest.raises(release_assets.ReleaseAssetError, match=message):
            release_assets.require_github_release_digests(
                (_WHEEL, _SDIST), index, assets, _BUNDLE
            )
