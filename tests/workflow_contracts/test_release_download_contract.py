"""Contracts for downloading canonical PyPI release files."""

from __future__ import annotations

import hashlib
import json
import os
import time
import typing as typ
import urllib.parse
from pathlib import Path

import pytest

from scripts import release_assets, release_assets_cli, release_commands
from tests.workflow_contracts.release_payloads import (
    BUNDLE,
    BUNDLE_BYTES,
    SDIST,
    WHEEL,
    release_view,
    sha256,
)
from tests.workflow_contracts.workflow_step_runner import run_named_workflow_step

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from tests.workflow_contracts.https_index_server import LocalHttpsServer


def _recorded(path: Path) -> list[list[str]]:
    """Read every command line recorded by a stand-in."""
    return [json.loads(line) for line in path.read_text().splitlines()]


def _download_calls(path: Path) -> list[list[str]]:
    """Return only the recorded curl invocations carrying ``--output``."""
    return [call for call in _recorded(path) if "--output" in call]


def _glob_index_body(pypi_bytes: dict[str, bytes], relative: str) -> str:
    """Build a PEP 691 body with one absolute and one relative glob URL."""
    return json.dumps({
        "files": [
            {
                "filename": WHEEL,
                "hashes": {"sha256": sha256(pypi_bytes[WHEEL])},
                "url": f"https://files.pythonhosted.org/{WHEEL}",
            },
            {
                "filename": SDIST,
                "hashes": {"sha256": sha256(pypi_bytes[SDIST])},
                "url": relative,
            },
        ]
    })


@pytest.fixture
def stalled_download_pid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    configure_publish: cabc.Callable[..., None],
    curl_argv_log: Path,
) -> Path:
    """Configure a publication whose second curl call outlives the deadline."""
    pypi_bytes = {WHEEL: b"canonical wheel", SDIST: b"canonical sdist"}
    configure_publish(pypi_bytes, local_files=pypi_bytes)
    view = release_view({**pypi_bytes, BUNDLE: BUNDLE_BYTES}, (WHEEL, BUNDLE))
    monkeypatch.setenv("GH_RESPONSES", json.dumps([{"stdout": view}, {"stdout": view}]))
    monkeypatch.setenv("CURL_RESPONSES", json.dumps([{}, {"sleep": 30}]))
    pid_path = tmp_path / "curl.pid"
    monkeypatch.setenv("CURL_PID_PATH", str(pid_path))
    monkeypatch.setattr(release_commands, "PYPI_DOWNLOAD_DEADLINE_SECONDS", 1)
    return pid_path


class TestPypiDownload:
    """Exercise the real download boundary through a recording curl stand-in."""

    def test_download_uses_bounded_https_and_output_arguments(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        curl_argv_log: Path,
    ) -> None:
        """Downloads have bounded retries and write the requested file."""
        url = "https://files.pythonhosted.org/packages/example.tar.gz"
        content = "canonical distribution"
        destination = tmp_path / "example.tar.gz"
        monkeypatch.setenv("CURL_DOWNLOAD_CONTENTS", json.dumps({url: content}))
        entry = release_assets.PypiFile(
            hashlib.sha256(content.encode()).hexdigest(), url
        )

        release_commands.download_pypi_file(entry, destination)

        calls = _recorded(curl_argv_log)
        assert len(calls) == 1, "one distribution must trigger one curl call"
        args = calls[0]
        required_switches = {
            "--fail",
            "--globoff",
            "--retry-all-errors",
            "--location",
        }
        assert required_switches <= set(args), (
            "downloads must fail on HTTP errors, disable URL globbing, retry "
            "errors and follow redirects"
        )
        for flag, value in (
            ("--proto", "=https"),
            ("--proto-redir", "=https"),
            ("--retry", "5"),
            ("--retry-delay", "2"),
            ("--retry-max-time", "300"),
            ("--connect-timeout", "10"),
            ("--max-time", "300"),
            ("--output", str(destination)),
        ):
            assert flag in args, f"download requires {flag}"
            assert args[args.index(flag) + 1] == value, f"{flag} must use {value!r}"
        assert args[-1] == url, "curl must download the canonical PyPI URL"
        assert destination.read_text() == content, (
            "curl must write the distribution to the requested destination"
        )

    @pytest.mark.parametrize(
        "url",
        [
            "https://files.pythonhosted.org/packages/[1-3]/example.tar.gz",
            "https://files.pythonhosted.org/packages/{a,b}/example.tar.gz",
        ],
        ids=["bracket-range", "brace-list"],
    )
    def test_glob_syntax_in_an_index_url_is_one_literal_download(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        curl_argv_log: Path,
        url: str,
    ) -> None:
        """Curl glob syntax in index metadata stays one literal transfer."""
        content = "literal distribution"
        destination = tmp_path / "example.tar.gz"
        monkeypatch.setenv("CURL_DOWNLOAD_CONTENTS", json.dumps({url: content}))
        entry = release_assets.PypiFile(
            hashlib.sha256(content.encode()).hexdigest(), url
        )

        release_commands.download_pypi_file(entry, destination)

        calls = _recorded(curl_argv_log)
        assert len(calls) == 1, "glob syntax must not expand into more transfers"
        assert "--globoff" in calls[0], "curl must treat the URL literally"
        assert calls[0][-1] == url, "the index URL must reach curl unchanged"
        assert destination.read_text() == content, (
            "one literal URL must write the expected bytes"
        )

    def test_publication_downloads_a_relative_glob_url_literally(
        self,
        monkeypatch: pytest.MonkeyPatch,
        configure_publish: cabc.Callable[..., None],
        curl_argv_log: Path,
        gh_argv_log: Path,
    ) -> None:
        """A relative index URL with glob syntax resolves and downloads once."""
        pypi_bytes = {WHEEL: b"canonical wheel", SDIST: b"canonical sdist"}
        configure_publish(pypi_bytes)
        relative = f"packages/[1-3]/{{a,b}}/{SDIST}"
        resolved = (
            f"https://pypi.org/simple/falcon-correlate/packages/[1-3]/{{a,b}}/{SDIST}"
        )
        monkeypatch.setenv("CURL_BODY", _glob_index_body(pypi_bytes, relative))
        first_view = release_view({**pypi_bytes, BUNDLE: BUNDLE_BYTES}, (WHEEL, BUNDLE))
        final_view = release_view(
            {**pypi_bytes, BUNDLE: BUNDLE_BYTES}, (WHEEL, SDIST, BUNDLE)
        )
        monkeypatch.setenv(
            "GH_RESPONSES",
            json.dumps([
                {"stdout": first_view},
                {"stdout": first_view},
                {},
                {"stdout": final_view},
                {},
            ]),
        )
        monkeypatch.setenv(
            "CURL_DOWNLOAD_CONTENTS",
            json.dumps({resolved: pypi_bytes[SDIST].decode()}),
        )

        result = run_named_workflow_step(
            "release.yml", "publish-release", "Reconcile and publish the GitHub Release"
        )

        assert result.returncode == 0, f"the release step failed: {result.stderr}"
        downloads = _download_calls(curl_argv_log)
        assert len(downloads) == 1, "the index URL must cause one download"
        assert "--globoff" in downloads[0], "the download must disable globbing"
        assert downloads[0][-1] == resolved, "curl must receive the literal URL"
        gh_calls = _recorded(gh_argv_log)
        upload = next(call for call in gh_calls if call[:2] == ["release", "upload"])
        uploaded = next(Path(path) for path in upload[3:] if Path(path).name == SDIST)
        assert uploaded.read_bytes() == pypi_bytes[SDIST], (
            "the literal download must be uploaded with PyPI's bytes"
        )
        assert any(call[:2] == ["release", "edit"] for call in gh_calls), (
            "a successful literal download must allow publication"
        )

    def test_download_deadline_stops_publication_and_reports_it(
        self,
        stalled_download_pid: Path,
        gh_argv_log: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """An overlong download terminates promptly and blocks publication."""
        started = time.monotonic()
        result = release_assets_cli.main(["publish-release"])
        elapsed = time.monotonic() - started

        assert result == 1, "a timed-out download must fail the release step"
        assert elapsed < 15, "the deadline must terminate the download promptly"
        error = capsys.readouterr().err
        assert "::error title=release-assets::" in error, (
            "the failure must use the release-assets annotation"
        )
        assert "1s deadline" in error, "the failure must show the deadline in seconds"
        pid = int(stalled_download_pid.read_text())
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
        gh_calls = _recorded(gh_argv_log)
        assert not any(call[:2] == ["release", "upload"] for call in gh_calls), (
            "a timed-out download must not reach the upload"
        )
        assert not any(call[:2] == ["release", "edit"] for call in gh_calls), (
            "a timed-out download must leave the release unpublished"
        )

    def test_real_curl_downloads_glob_syntax_as_one_literal_path(
        self,
        tmp_path: Path,
        https_index_server: LocalHttpsServer,
        curl_environment: None,
    ) -> None:
        """Real curl with ``--globoff`` requests one literal, unexpanded path."""
        relative = f"packages/[1-3]/{{a,b}}/{SDIST}"
        content = b"literal distribution"
        index_url = f"{https_index_server.url}simple/falcon-correlate/"
        body = json.dumps({
            "files": [
                {
                    "filename": SDIST,
                    "hashes": {"sha256": sha256(content)},
                    "url": relative,
                }
            ]
        })
        https_index_server.respond(status=200, body=content)
        files = release_assets.parse_pep691_index(body, index_url)
        destination = tmp_path / SDIST

        release_commands.download_pypi_file(files[SDIST], destination)

        assert destination.read_bytes() == content, (
            "curl must write the served distribution bytes"
        )
        assert len(https_index_server.requests) == 1, (
            "glob syntax must produce exactly one request"
        )
        request_path = urllib.parse.urlparse(https_index_server.requests[0]).path
        assert urllib.parse.unquote(request_path) == (
            f"/simple/falcon-correlate/{relative}"
        ), "the server must receive the literal, unexpanded path"

    def test_retry_window_is_bounded_by_the_download_deadline(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        https_index_server: LocalHttpsServer,
        curl_environment: None,
    ) -> None:
        """Curl retries stop when the whole-subprocess deadline expires."""
        https_index_server.respond(status=503, body=b"unavailable")
        url = f"{https_index_server.url}files/{SDIST}"
        entry = release_assets.PypiFile(hashlib.sha256(b"unused").hexdigest(), url)
        monkeypatch.setattr(release_commands, "PYPI_DOWNLOAD_DEADLINE_SECONDS", 3)

        started = time.monotonic()
        with pytest.raises(release_assets.ReleaseAssetError, match="deadline"):
            release_commands.download_pypi_file(entry, tmp_path / SDIST)
        elapsed = time.monotonic() - started

        assert 2.5 <= elapsed < 10, (
            "the deadline must terminate the retry loop near its budget"
        )
        assert 1 <= len(https_index_server.requests) <= 5, (
            "curl must retry a few times before the deadline stops it"
        )

    def test_production_deadline_exceeds_the_curl_time_limits(self) -> None:
        """The Python deadline outlasts both curl time limits."""
        arguments = release_commands.PYPI_DOWNLOAD_CURL_ARGUMENTS
        max_time = float(arguments[arguments.index("--max-time") + 1])
        retry_max_time = float(arguments[arguments.index("--retry-max-time") + 1])
        deadline = release_commands.PYPI_DOWNLOAD_DEADLINE_SECONDS

        assert deadline > max_time, "the deadline must outlast one transfer"
        assert deadline > retry_max_time, "the deadline must outlast the retries"
