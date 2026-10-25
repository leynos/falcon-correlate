"""Unit contracts for release validation and PyPI index handling."""

from __future__ import annotations

import doctest
import json
import typing as typ

import pytest

from scripts import release_assets, release_assets_cli, release_version

if typ.TYPE_CHECKING:
    from pathlib import Path

_SIMPLE_URL = "https://pypi.org/simple/falcon-correlate/"
_FILE_DIGEST = "a" * 64
_EXPECTED_INDEX_CURL_ARGUMENTS = [
    "--silent",
    "--show-error",
    "--location",
    "--proto",
    "=https",
    "--proto-redir",
    "=https",
    "--retry",
    "5",
    "--retry-all-errors",
    "--retry-delay",
    "2",
    "--retry-max-time",
    "90",
    "--connect-timeout",
    "10",
    "--max-time",
    "30",
    "--write-out",
    "\\n%{http_code}",
    "--header",
    "Accept: application/vnd.pypi.simple.v1+json",
    _SIMPLE_URL,
]
_EXPECTED_REUSED_RELEASE_LOOKUPS = (
    ("release", "view", "v1.2.0", "--json", "tagName"),
    ("release", "view", "v1.2.0", "--json", "tagName"),
)
_SIMPLE_BODY = json.dumps({
    "meta": {"api-version": "1.0"},
    "name": "falcon-correlate",
    "files": [
        {
            "filename": "falcon_correlate-1.2.0-py3-none-any.whl",
            "hashes": {"sha256": _FILE_DIGEST},
            "url": "https://files.pythonhosted.org/packages/falcon.whl",
        }
    ],
})


def _configure_curl(
    monkeypatch: pytest.MonkeyPatch,
    response: dict[str, str | int],
) -> None:
    """Set the response returned by the recording curl stand-in."""
    for name, value in response.items():
        monkeypatch.setenv(f"CURL_{name.upper()}", str(value))


def test_required_environment_value_names_missing_variable(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The public CLI reports a missing workflow setting by name."""
    monkeypatch.delenv("SOURCE_DIR", raising=False)

    result = release_assets_cli.main(["collect"])

    assert result == 1, "a missing workflow setting must fail the command"
    assert "SOURCE_DIR" in capsys.readouterr().err, (
        "the failure annotation must identify the missing setting"
    )


def _make_distributions(directory: Path) -> tuple[str, str]:
    """Create a wheel and source archive for CLI contract tests."""
    directory.mkdir(parents=True, exist_ok=True)
    wheel_name = "falcon_correlate-1.2.0-py3-none-any.whl"
    sdist_name = "falcon_correlate-1.2.0.tar.gz"
    (directory / wheel_name).write_bytes(b"wheel bytes")
    (directory / sdist_name).write_bytes(b"sdist bytes")
    return wheel_name, sdist_name


def test_read_index_treats_project_404_as_unpublished(
    tmp_path: Path,
    curl_argv_log: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The public CLI stages every file when the project index is absent."""
    distributions = tmp_path / "dist"
    wheel_name, sdist_name = _make_distributions(distributions)
    staging = tmp_path / "staging"
    output = tmp_path / "github-output"
    monkeypatch.setenv("DIST_DIR", str(distributions))
    monkeypatch.setenv("STAGING_DIR", str(staging))
    monkeypatch.setenv("SIMPLE_INDEX_URL", _SIMPLE_URL)
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    _configure_curl(monkeypatch, {"status": "404"})

    result = release_assets_cli.main(["stage-pypi"])

    assert result == 0, "a missing project index means no upload is already published"
    assert sorted(path.name for path in staging.iterdir()) == [
        wheel_name,
        sdist_name,
    ], "a 404 must leave every distribution staged for its first upload"
    assert output.read_text(encoding="utf-8") == "has-uploads=true\n", (
        "a first upload must expose the conditional publish output"
    )
    assert curl_argv_log.is_file(), "the unpublished project lookup must call curl"
    arguments = json.loads(curl_argv_log.read_text(encoding="utf-8").splitlines()[0])
    assert arguments == _EXPECTED_INDEX_CURL_ARGUMENTS, (
        "PyPI lookups must use retrying, time-limited PEP 691 requests"
    )


def test_read_index_parses_pep691_filename_digests(
    tmp_path: Path,
    curl_argv_log: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The public PyPI staging step drops names already listed by PEP 691."""
    distributions = tmp_path / "dist"
    wheel_name, sdist_name = _make_distributions(distributions)
    staging = tmp_path / "staging"
    output = tmp_path / "github-output"
    monkeypatch.setenv("DIST_DIR", str(distributions))
    monkeypatch.setenv("STAGING_DIR", str(staging))
    monkeypatch.setenv("SIMPLE_INDEX_URL", _SIMPLE_URL)
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    _configure_curl(monkeypatch, {"status": "200", "body": _SIMPLE_BODY})

    result = release_assets_cli.main(["stage-pypi"])

    assert result == 0, "a valid Simple index must be accepted"
    assert curl_argv_log.is_file(), "the PEP 691 request must reach curl"
    assert [path.name for path in staging.iterdir()] == [sdist_name], (
        "only the distribution name absent from PyPI should remain staged"
    )
    assert output.read_text(encoding="utf-8") == "has-uploads=true\n", (
        "the remaining sdist must enable the PyPI upload step"
    )
    parsed = release_assets.parse_pep691_index(_SIMPLE_BODY, _SIMPLE_URL)
    assert parsed[wheel_name] == release_assets.PypiFile(
        _FILE_DIGEST, "https://files.pythonhosted.org/packages/falcon.whl"
    ), "PEP 691 parsing must retain the digest and canonical download URL"


def test_read_index_fails_on_non_success_http_status(
    tmp_path: Path,
    curl_argv_log: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An HTTP error other than 404 fails the public PyPI staging step."""
    distributions = tmp_path / "dist"
    _make_distributions(distributions)
    monkeypatch.setenv("DIST_DIR", str(distributions))
    monkeypatch.setenv("STAGING_DIR", str(tmp_path / "staging"))
    monkeypatch.setenv("SIMPLE_INDEX_URL", _SIMPLE_URL)
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "github-output"))
    _configure_curl(monkeypatch, {"status": "500", "body": "server error"})

    result = release_assets_cli.main(["stage-pypi"])

    assert result == 1, "a PyPI server error must fail the release step"
    assert "HTTP 500" in capsys.readouterr().err, (
        "the failure annotation must identify the HTTP status"
    )
    assert curl_argv_log.is_file(), "the non-success response must reach curl"


def test_cli_escapes_remote_error_text_in_workflow_annotation(
    tmp_path: Path,
    curl_argv_log: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Remote diagnostics cannot inject additional GitHub workflow commands."""
    distributions = tmp_path / "dist"
    distributions.mkdir()
    (distributions / "falcon_correlate-1.2.0-py3-none-any.whl").touch()
    (distributions / "falcon_correlate-1.2.0.tar.gz").touch()
    monkeypatch.setenv("DIST_DIR", str(distributions))
    monkeypatch.setenv("SIMPLE_INDEX_URL", _SIMPLE_URL)
    _configure_curl(
        monkeypatch,
        {
            "status": "000",
            "exit": 7,
            "stderr": "failure%\rforged\r\n::warning::forged",
        },
    )

    result = release_assets_cli.main(["stage-pypi"])

    error_line = capsys.readouterr().err.rstrip("\n")
    assert result == 1, "a failed curl request must fail the release step"
    assert curl_argv_log.is_file(), "the release step must call curl"
    assert "failure%25%0Aforged%0A::warning::forged" in error_line, (
        "remote newlines must be escaped before becoming a workflow command"
    )
    assert "\r" not in error_line, "remote CR characters must be escaped"
    assert "\n" not in error_line, "remote LF characters must be escaped"


def test_ensure_draft_retries_before_creating_a_release(
    tmp_path: Path,
    gh_argv_log: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transient not-found response reuses a draft instead of duplicating it."""
    distributions = tmp_path / "dist"
    distributions.mkdir()
    (distributions / "falcon_correlate-1.2.0-py3-none-any.whl").touch()
    (distributions / "falcon_correlate-1.2.0.tar.gz").touch()
    monkeypatch.setenv("DIST_DIR", str(distributions))
    monkeypatch.setenv("RELEASE_TAG", "v1.2.0")
    monkeypatch.setenv(
        "GH_RESPONSES",
        json.dumps([
            {"exit_code": 1, "stderr": "release not found"},
            {"exit_code": 0, "stdout": '{"tagName":"v1.2.0"}'},
        ]),
    )
    monkeypatch.setattr(release_assets_cli.time, "sleep", lambda _seconds: None)

    result = release_assets_cli.main(["ensure-draft"])

    calls = tuple(
        tuple(json.loads(line)) for line in gh_argv_log.read_text().splitlines()
    )
    assert result == 0, "a visible existing release must be reused"
    assert calls == _EXPECTED_REUSED_RELEASE_LOOKUPS, (
        "a transient not-found response must not create a duplicate draft"
    )


def test_release_version_requires_exact_v_prefixed_tag() -> None:
    """Release tags match only the exact ``v``-prefixed project version."""
    release_version.validate_tag_version("v1.2.0", "1.2.0")

    with pytest.raises(ValueError, match=r"expected 'v1\.2\.0'"):
        release_version.validate_tag_version("1.2.0", "1.2.0")


@pytest.mark.parametrize(
    ("version", "prerelease"),
    [("1.2.0", "false"), ("1.2.0rc1", "true")],
)
def test_release_version_main_writes_workflow_outputs(
    tmp_path: Path, version: str, prerelease: str
) -> None:
    """The version script exposes validated metadata to later jobs."""
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nversion = "{version}"\n', encoding="utf-8"
    )
    output = tmp_path / "github-output"

    result = release_version.main(
        {"RELEASE_TAG": f"v{version}", "GITHUB_OUTPUT": str(output)},
        root=tmp_path,
    )

    assert result == 0, "a matching release tag must pass version validation"
    assert output.read_text(encoding="utf-8") == (
        f"version={version}\nprerelease={prerelease}\n"
    ), "the version script must expose both outputs exactly once"


def test_release_version_reports_missing_workflow_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A missing workflow value is named in the annotation."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nversion = "1.2.0"\n', encoding="utf-8"
    )

    result = release_version.main(
        {"GITHUB_OUTPUT": str(tmp_path / "github-output")},
        root=tmp_path,
    )

    assert result == 1, "a missing release tag must fail version validation"
    assert "required value 'RELEASE_TAG' is missing" in capsys.readouterr().err, (
        "the workflow annotation must name the missing value"
    )


@pytest.mark.parametrize(
    ("version", "expected_status"),
    [("1.2.0", "final"), ("1.2.0rc1", "pre-release"), ("1.2.0.dev2", "pre-release")],
)
def test_release_version_classifies_prerelease(
    version: str, expected_status: str
) -> None:
    """PEP 440 pre-release and development markers select pre-release status."""
    is_prerelease = expected_status == "pre-release"
    assert release_version.is_prerelease(version) is is_prerelease, (
        f"version {version} must be classified as {expected_status}"
    )


def test_release_version_examples_run_as_doctests() -> None:
    """Documented release-version examples stay executable."""
    result = doctest.testmod(release_version)

    assert result.failed == 0, f"release-version doctests failed: {result}"


def test_digest_mismatches_reject_different_github_bytes() -> None:
    """GitHub assets must have the same SHA-256 as the PyPI files."""
    pypi_files = {
        "falcon_correlate-1.2.0.tar.gz": release_assets.PypiFile(
            _FILE_DIGEST, "https://files.pythonhosted.org/packages/falcon.tar.gz"
        )
    }

    mismatches = release_assets.digest_mismatches(
        pypi_files,
        pypi_files,
        {"falcon_correlate-1.2.0.tar.gz": "b" * 64},
    )

    assert len(mismatches) == 1, "one wrong release digest must be reported"
    assert "differs: PyPI sha256" in mismatches[0], (
        "digest diagnostics must identify the mismatching destinations"
    )
