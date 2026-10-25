"""Unit contracts for release validation and PyPI index handling."""

from __future__ import annotations

import doctest
import json
import os
import stat
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


@pytest.fixture
def curl_argv_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Install a recording curl stand-in at the front of PATH."""
    bin_directory = tmp_path / "bin"
    bin_directory.mkdir()
    curl = bin_directory / "curl"
    curl.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n\n"
        "record = Path(os.environ['CURL_ARGV_PATH'])\n"
        "with record.open('a', encoding='utf-8') as stream:\n"
        "    stream.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "sys.stdout.write(os.environ.get('CURL_BODY', ''))\n"
        "sys.stdout.write('\\n' + os.environ.get('CURL_STATUS', '200'))\n"
        "sys.stderr.write(os.environ.get('CURL_STDERR', ''))\n"
        "raise SystemExit(int(os.environ.get('CURL_EXIT', '0')))\n",
        encoding="utf-8",
    )
    curl.chmod(curl.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    record = tmp_path / "curl-argv.jsonl"
    monkeypatch.setenv("CURL_ARGV_PATH", str(record))
    monkeypatch.setenv("PATH", f"{bin_directory}{os.pathsep}{os.environ['PATH']}")
    return record


def _configure_curl(
    monkeypatch: pytest.MonkeyPatch,
    response: dict[str, str | int],
) -> None:
    """Set the response returned by the recording curl stand-in."""
    for name, value in response.items():
        monkeypatch.setenv(f"CURL_{name.upper()}", str(value))


def test_required_environment_value_names_missing_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing workflow setting fails with its name in the diagnostic."""
    monkeypatch.delenv("RELEASE_TAG", raising=False)

    with pytest.raises(release_assets.ReleaseAssetError, match="RELEASE_TAG"):
        release_assets_cli._required("RELEASE_TAG")


def test_read_index_treats_project_404_as_unpublished(
    curl_argv_log: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A project without a Simple index has no published filenames to skip."""
    _configure_curl(monkeypatch, {"status": "404"})

    assert release_assets_cli._read_index(_SIMPLE_URL) == {}, (
        "an unpublished project must have no filenames to skip"
    )
    assert curl_argv_log.is_file(), "the unpublished project lookup must call curl"
    arguments = json.loads(curl_argv_log.read_text(encoding="utf-8").splitlines()[0])
    assert arguments == _EXPECTED_INDEX_CURL_ARGUMENTS, (
        "PyPI lookups must use retrying, time-limited PEP 691 requests"
    )


def test_read_index_parses_pep691_filename_digests(
    curl_argv_log: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A successful PEP 691 response maps filenames to digest and URL."""
    _configure_curl(monkeypatch, {"status": "200", "body": _SIMPLE_BODY})

    files = release_assets_cli._read_index(_SIMPLE_URL)

    assert curl_argv_log.is_file(), "the PEP 691 request must reach curl"
    assert files == {
        "falcon_correlate-1.2.0-py3-none-any.whl": release_assets.PypiFile(
            _FILE_DIGEST, "https://files.pythonhosted.org/packages/falcon.whl"
        )
    }, "the Simple index entry must retain its digest and download URL"


def test_read_index_fails_on_non_success_http_status(
    curl_argv_log: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An HTTP error other than the absent-project 404 fails the step."""
    _configure_curl(monkeypatch, {"status": "500", "body": "server error"})

    with pytest.raises(release_assets.ReleaseAssetError, match="HTTP 500"):
        release_assets_cli._read_index(_SIMPLE_URL)
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

    result = release_assets_cli._main(["stage-pypi"])

    error_line = capsys.readouterr().err.rstrip("\n")
    assert result == 1, "a failed curl request must fail the release step"
    assert curl_argv_log.is_file(), "the release step must call curl"
    assert "failure%25%0Aforged%0A::warning::forged" in error_line, (
        "remote newlines must be escaped before becoming a workflow command"
    )
    assert "\r" not in error_line, "remote CR characters must be escaped"
    assert "\n" not in error_line, "remote LF characters must be escaped"


def test_workflow_command_data_escapes_percent_and_carriage_return() -> None:
    """Percent and CR are encoded before workflow command interpolation."""
    escaped = release_assets_cli._escape_workflow_command_data("100%\rwarning")

    assert escaped == "100%25%0Dwarning", "percent and CR must be encoded"


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
