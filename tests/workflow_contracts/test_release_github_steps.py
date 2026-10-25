"""Contracts for draft release creation and reuse."""

from __future__ import annotations

import json
import typing as typ

import pytest

from scripts import release_assets_cli

if typ.TYPE_CHECKING:
    from pathlib import Path

_TAG = "v1.2.0"
_WHEEL = "falcon_correlate-1.2.0-py3-none-any.whl"
_SDIST = "falcon_correlate-1.2.0.tar.gz"
_EXPECTED_DRAFT_CREATE = [
    "release",
    "create",
    _TAG,
    "--draft",
    "--verify-tag",
    "--generate-notes",
    "--title",
    _TAG,
]


def _configure_release(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide a non-empty distribution set to the release helper."""
    distributions = tmp_path / "dist"
    distributions.mkdir()
    (distributions / _WHEEL).touch()
    (distributions / _SDIST).touch()
    monkeypatch.setenv("DIST_DIR", str(distributions))
    monkeypatch.setenv("RELEASE_TAG", _TAG)


def test_ensure_draft_creates_only_after_repeated_not_found(
    tmp_path: Path,
    gh_argv_log: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A tag is verified and a draft is created after release lookups settle."""
    _configure_release(tmp_path, monkeypatch)
    missing = {"exit_code": 1, "stderr": "release not found"}
    monkeypatch.setenv(
        "GH_RESPONSES",
        json.dumps([missing, missing, missing, {}]),
    )
    monkeypatch.setattr(release_assets_cli.time, "sleep", lambda _seconds: None)

    result = release_assets_cli.main(["ensure-draft"])

    calls = [json.loads(line) for line in gh_argv_log.read_text().splitlines()]
    assert result == 0, "a stable not-found result must create a draft"
    assert len(calls) == 4, "the helper must retry release lookup before creation"
    assert calls[-1] == _EXPECTED_DRAFT_CREATE, (
        "a missing release must be created as a verified draft"
    )
    assert "Created a draft" in capsys.readouterr().out, (
        "successful draft creation must be visible in workflow logs"
    )


@pytest.mark.parametrize(
    "release_json",
    ['{"tagName":"v1.2.0","isDraft":true}', '{"tagName":"v1.2.0","isDraft":false}'],
    ids=["reuse-draft", "reuse-published-release"],
)
def test_ensure_draft_reuses_existing_draft_or_published_release(
    tmp_path: Path,
    gh_argv_log: Path,
    monkeypatch: pytest.MonkeyPatch,
    release_json: str,
) -> None:
    """The helper reuses a release regardless of its current publication state."""
    _configure_release(tmp_path, monkeypatch)
    monkeypatch.setenv(
        "GH_RESPONSES",
        json.dumps([{"stdout": release_json}]),
    )

    result = release_assets_cli.main(["ensure-draft"])

    calls = [json.loads(line) for line in gh_argv_log.read_text().splitlines()]
    assert result == 0, "an existing release must be reused"
    assert calls == [["release", "view", _TAG, "--json", "tagName"]], (
        "an existing draft or published release must not be duplicated"
    )
