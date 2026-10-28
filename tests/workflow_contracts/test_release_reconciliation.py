"""End-to-end contracts for PyPI-backed GitHub release reconciliation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import release_assets_cli
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
    sha256 as _sha256,
)
from tests.workflow_contracts.release_payloads import (
    simple_body as _simple_body,
)
from tests.workflow_contracts.workflow_step_runner import run_named_workflow_step


def _configure_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pypi_files: dict[str, bytes],
    local_files: dict[str, bytes] | None = None,
) -> None:
    """Set release inputs and provide a tag-named bundle."""
    distributions = tmp_path / "dist"
    distributions.mkdir()
    local_files = local_files or {
        _WHEEL: b"local wheel",
        _SDIST: b"local sdist",
    }
    for name, content in local_files.items():
        (distributions / name).write_bytes(content)
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
    """Script the preflight and reconciliation views, upload and edit calls."""
    monkeypatch.setenv(
        "GH_RESPONSES",
        json.dumps([
            {"stdout": first_view},
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
    """Missing files use PyPI bytes while an existing bundle is preserved."""
    pypi_bytes = {
        _WHEEL: b"canonical wheel",
        _SDIST: b"canonical sdist",
        "falcon_correlate-1.1.0.tar.gz": b"older release sdist",
    }
    _configure_publish(tmp_path, monkeypatch, pypi_bytes)
    assets = {**pypi_bytes, _BUNDLE: _BUNDLE_BYTES}
    _set_gh_responses(
        monkeypatch,
        _release_view(assets, (_WHEEL, _BUNDLE)),
        _release_view(assets, (_WHEEL, _SDIST, _BUNDLE)),
    )
    monkeypatch.setenv(
        "CURL_DOWNLOAD_CONTENTS",
        json.dumps({
            f"https://files.pythonhosted.org/{_SDIST}": pypi_bytes[_SDIST].decode()
        }),
    )

    result = run_named_workflow_step(
        "release.yml", "publish-release", "Reconcile and publish the GitHub Release"
    )

    assert result.returncode == 0, f"the release step failed: {result.stderr}"
    gh_calls = [json.loads(line) for line in gh_argv_log.read_text().splitlines()]
    upload = next(call for call in gh_calls if call[:2] == ["release", "upload"])
    uploaded_paths = [Path(path) for path in upload[3:]]
    staged_sdist = next(path for path in uploaded_paths if path.name == _SDIST)
    assert staged_sdist.read_bytes() == pypi_bytes[_SDIST], (
        "the uploaded source archive must use PyPI's canonical bytes"
    )
    assert not any(path.name == _BUNDLE for path in uploaded_paths), (
        "an existing tag-named attestation bundle must not be replaced"
    )
    assert "--clobber" not in upload, (
        "release reconciliation must never overwrite assets"
    )
    curl_calls = [json.loads(line) for line in curl_argv_log.read_text().splitlines()]
    download = next(call for call in curl_calls if "--output" in call)
    assert (
        "https://files.pythonhosted.org/falcon_correlate-1.1.0.tar.gz" not in download
    ), "reconciliation must not download assets from earlier versions"
    assert not any(
        Path(path).name == "falcon_correlate-1.1.0.tar.gz" for path in upload[3:]
    ), "a release must not attach assets from earlier versions"
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
        "GH_RESPONSES",
        json.dumps([{"stdout": view}, {"stdout": view}, {"stdout": view}, {}]),
    )

    result = run_named_workflow_step(
        "release.yml", "publish-release", "Reconcile and publish the GitHub Release"
    )

    assert result.returncode == 0, f"the release step failed: {result.stderr}"
    calls = [json.loads(line) for line in gh_argv_log.read_text().splitlines()]
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
) -> None:
    """A pre-existing asset with non-PyPI bytes blocks publication."""
    pypi_bytes = {_WHEEL: b"canonical wheel", _SDIST: b"canonical sdist"}
    _configure_publish(tmp_path, monkeypatch, pypi_bytes)
    wrong_assets = json.dumps({
        "assets": [
            {"name": _WHEEL, "digest": f"sha256:{_sha256(b'wrong wheel')}"},
            {"name": _BUNDLE, "digest": f"sha256:{_sha256(_BUNDLE_BYTES)}"},
        ]
    })
    monkeypatch.setenv(
        "GH_RESPONSES",
        json.dumps([{"stdout": wrong_assets}, {"stdout": wrong_assets}]),
    )

    result = run_named_workflow_step(
        "release.yml", "publish-release", "Reconcile and publish the GitHub Release"
    )

    assert result.returncode == 1, f"a conflicting digest must fail: {result.stderr}"
    calls = [json.loads(line) for line in gh_argv_log.read_text().splitlines()]
    assert "differs from PyPI" in result.stderr, (
        "the failure annotation must identify the canonical destination"
    )
    assert not any(call[:2] == ["release", "upload"] for call in calls), (
        "mismatched pre-existing bytes must not be overwritten"
    )


@pytest.mark.usefixtures("curl_argv_log", "gh_argv_log")
@pytest.mark.parametrize(
    "invalid_setting",
    [
        ("STAGING_DIR", None, "STAGING_DIR is missing"),
        ("PRERELEASE", "sometimes", "PRERELEASE must be either true or false"),
    ],
)
def test_publish_release_validates_inputs_before_external_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    invalid_setting: tuple[str, str | None, str],
) -> None:
    """Invalid workflow inputs fail before contacting either destination."""
    variable, value, message = invalid_setting
    _configure_publish(tmp_path, monkeypatch, {_WHEEL: b"wheel", _SDIST: b"sdist"})
    if value is None:
        monkeypatch.delenv(variable)
    else:
        monkeypatch.setenv(variable, value)

    result = release_assets_cli.main(["publish-release"])

    assert result == 1, "invalid workflow input must prevent publication"
    assert message in capsys.readouterr().err, "the failure should identify the input"
    assert not (tmp_path / "curl-argv.jsonl").exists(), (
        "invalid configuration must fail before querying PyPI"
    )
    assert not (tmp_path / "gh-argv.jsonl").exists(), (
        "invalid configuration must fail before querying GitHub"
    )


@pytest.mark.usefixtures("curl_argv_log")
def test_existing_github_asset_without_digest_fails_before_upload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    gh_argv_log: Path,
) -> None:
    """An existing asset without a GitHub digest is reported distinctly."""
    pypi_bytes = {_WHEEL: b"canonical wheel", _SDIST: b"canonical sdist"}
    _configure_publish(tmp_path, monkeypatch, pypi_bytes)
    missing_digest_view = json.dumps({
        "assets": [
            {"name": _WHEEL, "digest": None},
            {"name": _BUNDLE, "digest": f"sha256:{_sha256(_BUNDLE_BYTES)}"},
        ]
    })
    monkeypatch.setenv(
        "GH_RESPONSES",
        json.dumps([{"stdout": missing_digest_view}, {"stdout": missing_digest_view}]),
    )

    result = run_named_workflow_step(
        "release.yml", "publish-release", "Reconcile and publish the GitHub Release"
    )

    assert result.returncode == 1, f"an unknown digest must fail: {result.stderr}"
    calls = [json.loads(line) for line in gh_argv_log.read_text().splitlines()]
    assert "already exists on GitHub without a SHA-256 digest" in result.stderr, (
        "the error should distinguish a missing digest from different bytes"
    )
    assert not any(call[:2] == ["release", "upload"] for call in calls), (
        "an asset with unknown bytes must not be overwritten"
    )


@pytest.mark.usefixtures("curl_argv_log")
def test_new_bundle_is_uploaded_when_local_bytes_match_pypi(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    gh_argv_log: Path,
) -> None:
    """A first-run bundle is attached when it attests PyPI's exact bytes."""
    pypi_bytes = {_WHEEL: b"canonical wheel", _SDIST: b"canonical sdist"}
    _configure_publish(tmp_path, monkeypatch, pypi_bytes, local_files=pypi_bytes)
    _set_gh_responses(
        monkeypatch,
        _release_view(pypi_bytes, (_WHEEL, _SDIST)),
        _release_view(
            {**pypi_bytes, _BUNDLE: _BUNDLE_BYTES}, (_WHEEL, _SDIST, _BUNDLE)
        ),
    )

    result = run_named_workflow_step(
        "release.yml", "publish-release", "Reconcile and publish the GitHub Release"
    )

    assert result.returncode == 0, f"the release step failed: {result.stderr}"
    calls = [json.loads(line) for line in gh_argv_log.read_text().splitlines()]
    upload = next(call for call in calls if call[:2] == ["release", "upload"])
    assert [Path(path).name for path in upload[3:]] == [_BUNDLE], (
        "only the missing tag-named bundle must be uploaded"
    )


@pytest.mark.usefixtures("curl_argv_log")
def test_new_bundle_requires_local_bytes_to_match_pypi(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    gh_argv_log: Path,
) -> None:
    """A new bundle cannot attest bytes that differ from PyPI's files."""
    _configure_publish(
        tmp_path,
        monkeypatch,
        {_WHEEL: b"canonical wheel", _SDIST: b"canonical sdist"},
    )
    monkeypatch.setenv("GH_RESPONSES", json.dumps([{"stdout": '{"assets": []}'}]))

    result = run_named_workflow_step(
        "release.yml", "publish-release", "Reconcile and publish the GitHub Release"
    )

    assert result.returncode == 1, f"non-canonical bytes must fail: {result.stderr}"
    assert "local release distributions differ from PyPI" in result.stderr, (
        "the failure must explain the provenance mismatch"
    )
    calls = [json.loads(line) for line in gh_argv_log.read_text().splitlines()]
    curl_calls = [
        json.loads(line)
        for line in (tmp_path / "curl-argv.jsonl").read_text().splitlines()
    ]
    assert not any(call[:2] == ["release", "upload"] for call in calls), (
        "mismatched distributions must fail before release uploads"
    )
    assert not any("--output" in call for call in curl_calls), (
        "mismatched distributions must fail before downloading release files"
    )


def test_publish_release_refuses_an_empty_distribution_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    gh_argv_log: Path,
) -> None:
    """An empty release cannot reach GitHub publication commands."""
    distributions = tmp_path / "dist"
    distributions.mkdir()
    monkeypatch.setenv("DIST_DIR", str(distributions))
    monkeypatch.setenv("RELEASE_TAG", _TAG)

    result = run_named_workflow_step(
        "release.yml", "publish-release", "Reconcile and publish the GitHub Release"
    )

    assert result.returncode == 1, (
        "an empty distribution set must fail the release step"
    )
    assert "empty release artefact set" in result.stderr, (
        "the failure annotation must say why publication was refused"
    )
    assert not gh_argv_log.exists(), "empty artefacts must fail before GitHub access"
