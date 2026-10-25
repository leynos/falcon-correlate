"""End-to-end contracts for PyPI-backed GitHub release reconciliation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import release_assets_cli

_SIMPLE_URL = "https://pypi.org/simple/falcon-correlate/"
_TAG = "v1.2.0"
_WHEEL = "falcon_correlate-1.2.0-py3-none-any.whl"
_SDIST = "falcon_correlate-1.2.0.tar.gz"
_BUNDLE = f"{_TAG}.sigstore.json"
_BUNDLE_BYTES = b"attestation bundle"


def _sha256(content: bytes) -> str:
    """Return the digest format used by PyPI and GitHub release assets."""
    return hashlib.sha256(content).hexdigest()


def _simple_body(files: dict[str, bytes]) -> str:
    """Build a PEP 691 index for the canonical bytes in the test."""
    return json.dumps({
        "files": [
            {
                "filename": name,
                "hashes": {"sha256": _sha256(content)},
                "url": f"https://files.pythonhosted.org/{name}",
            }
            for name, content in files.items()
        ]
    })


def _release_view(files: dict[str, bytes], names: tuple[str, ...]) -> str:
    """Build a gh release view response for a named subset of assets."""
    return json.dumps({
        "assets": [
            {"name": name, "digest": f"sha256:{_sha256(files[name])}"} for name in names
        ]
    })


def _configure_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pypi_files: dict[str, bytes],
) -> None:
    """Set release inputs and provide a tag-named bundle."""
    distributions = tmp_path / "dist"
    distributions.mkdir()
    (distributions / _WHEEL).write_bytes(b"local wheel")
    (distributions / _SDIST).write_bytes(b"local sdist")
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    bundle = bundle_dir / _BUNDLE
    bundle.write_bytes(_BUNDLE_BYTES)
    monkeypatch.setenv("DIST_DIR", str(distributions))
    monkeypatch.setenv("RELEASE_TAG", _TAG)
    monkeypatch.setenv("SIMPLE_INDEX_URL", _SIMPLE_URL)
    monkeypatch.setenv("BUNDLE_DIR", str(bundle_dir))
    monkeypatch.setenv("STAGING_DIR", str(tmp_path / "staging"))
    monkeypatch.setenv("PRERELEASE", "true")
    monkeypatch.setenv("CURL_BODY", _simple_body(pypi_files))
    monkeypatch.setenv("CURL_STATUS", "200")


def _set_gh_responses(
    monkeypatch: pytest.MonkeyPatch,
    first_view: str,
    second_view: str,
) -> None:
    """Script the before/after views, upload and edit calls."""
    monkeypatch.setenv(
        "GH_RESPONSES",
        json.dumps([
            {"stdout": first_view},
            {},
            {"stdout": second_view},
            {},
        ]),
    )


def test_publish_downloads_pypi_bytes_for_missing_release_assets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    curl_argv_log: Path,
    gh_argv_log: Path,
) -> None:
    """Missing distribution assets come from PyPI and are verified before upload."""
    pypi_bytes = {
        _WHEEL: b"canonical wheel",
        _SDIST: b"canonical sdist",
    }
    _configure_publish(tmp_path, monkeypatch, pypi_bytes)
    assets = {**pypi_bytes, _BUNDLE: _BUNDLE_BYTES}
    _set_gh_responses(
        monkeypatch,
        _release_view(assets, (_WHEEL,)),
        _release_view(assets, (_WHEEL, _SDIST, _BUNDLE)),
    )
    monkeypatch.setenv(
        "CURL_DOWNLOAD_CONTENTS",
        json.dumps({
            f"https://files.pythonhosted.org/{_SDIST}": pypi_bytes[_SDIST].decode()
        }),
    )

    result = release_assets_cli.main(["publish-release"])

    gh_calls = [json.loads(line) for line in gh_argv_log.read_text().splitlines()]
    upload = next(call for call in gh_calls if call[:2] == ["release", "upload"])
    uploaded_paths = [Path(path) for path in upload[3:]]
    staged_sdist = next(path for path in uploaded_paths if path.name == _SDIST)
    assert result == 0, "the matching PyPI and GitHub bytes must publish"
    assert staged_sdist.read_bytes() == pypi_bytes[_SDIST], (
        "the uploaded source archive must use PyPI's canonical bytes"
    )
    assert any(path.name == _BUNDLE for path in uploaded_paths), (
        "the tag-named attestation bundle must be attached when absent"
    )
    assert "--clobber" not in upload, (
        "release reconciliation must never overwrite assets"
    )
    curl_calls = [json.loads(line) for line in curl_argv_log.read_text().splitlines()]
    download = next(call for call in curl_calls if "--output" in call)
    assert download[download.index("--proto") + 1] == "=https", (
        "PyPI downloads must restrict their initial protocol to HTTPS"
    )
    assert download[download.index("--proto-redir") + 1] == "=https", (
        "PyPI downloads must prevent HTTPS redirects from downgrading"
    )
    edit = next(call for call in gh_calls if call[:2] == ["release", "edit"])
    assert "--draft=false" in edit, "the reconciled release must be un-drafted"
    assert "--prerelease=true" in edit, (
        "the reconciled release must retain its pre-release status"
    )
    assert (tmp_path / "dist" / _SDIST).read_bytes() != staged_sdist.read_bytes(), (
        "the test must distinguish PyPI bytes from the original build artifact"
    )
    assert curl_argv_log.is_file(), "reconciliation must query PyPI's Simple index"


@pytest.mark.usefixtures("curl_argv_log")
def test_noop_rerun_still_un_drafts_the_fully_reconciled_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    gh_argv_log: Path,
) -> None:
    """An idempotent rerun performs no upload but still publishes the draft."""
    pypi_bytes = {_WHEEL: b"wheel", _SDIST: b"sdist"}
    _configure_publish(tmp_path, monkeypatch, pypi_bytes)
    view = _release_view(
        {**pypi_bytes, _BUNDLE: _BUNDLE_BYTES}, (_WHEEL, _SDIST, _BUNDLE)
    )
    monkeypatch.setenv(
        "GH_RESPONSES", json.dumps([{"stdout": view}, {"stdout": view}, {}])
    )

    result = release_assets_cli.main(["publish-release"])

    calls = [json.loads(line) for line in gh_argv_log.read_text().splitlines()]
    assert result == 0, "a fully reconciled rerun must succeed"
    assert not any(call[:2] == ["release", "upload"] for call in calls), (
        "a rerun must not upload assets already held by the release"
    )
    assert calls[-1] == [
        "release",
        "edit",
        _TAG,
        "--draft=false",
        "--prerelease=true",
    ], "a no-op rerun must still ensure the release is published"


@pytest.mark.usefixtures("curl_argv_log")
def test_existing_github_digest_mismatch_fails_before_upload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    gh_argv_log: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A pre-existing asset with non-PyPI bytes blocks publication."""
    pypi_bytes = {_WHEEL: b"canonical wheel", _SDIST: b"canonical sdist"}
    _configure_publish(tmp_path, monkeypatch, pypi_bytes)
    wrong_assets = json.dumps({
        "assets": [{"name": _WHEEL, "digest": f"sha256:{_sha256(b'wrong wheel')}"}]
    })
    monkeypatch.setenv("GH_RESPONSES", json.dumps([{"stdout": wrong_assets}]))

    result = release_assets_cli.main(["publish-release"])

    calls = [json.loads(line) for line in gh_argv_log.read_text().splitlines()]
    assert result == 1, "a conflicting GitHub digest must fail reconciliation"
    assert "differs from PyPI" in capsys.readouterr().err, (
        "the failure annotation must identify the canonical destination"
    )
    assert not any(call[:2] == ["release", "upload"] for call in calls), (
        "mismatched pre-existing bytes must not be overwritten"
    )


def test_publish_release_refuses_an_empty_distribution_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    gh_argv_log: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An empty release cannot reach GitHub publication commands."""
    distributions = tmp_path / "dist"
    distributions.mkdir()
    monkeypatch.setenv("DIST_DIR", str(distributions))
    monkeypatch.setenv("RELEASE_TAG", _TAG)

    result = release_assets_cli.main(["publish-release"])

    assert result == 1, "an empty distribution set must fail the release step"
    assert "empty release artefact set" in capsys.readouterr().err, (
        "the failure annotation must say why publication was refused"
    )
    assert not gh_argv_log.exists(), "empty artefacts must fail before GitHub access"
