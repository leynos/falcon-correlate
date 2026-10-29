"""Contracts for downloading canonical PyPI release files."""

from __future__ import annotations

import hashlib
import json
import typing as typ

from scripts import release_assets, release_assets_cli

if typ.TYPE_CHECKING:
    from pathlib import Path

    import pytest


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

        release_assets_cli._download_pypi_file(entry, destination)

        calls = [json.loads(line) for line in curl_argv_log.read_text().splitlines()]
        assert len(calls) == 1, "one distribution must trigger one curl call"
        args = calls[0]
        required_switches = {"--fail", "--retry-all-errors", "--location"}
        assert required_switches <= set(args), (
            "downloads must fail on HTTP errors, retry errors and follow redirects"
        )
        for flag, value in (
            ("--proto", "=https"),
            ("--proto-redir", "=https"),
            ("--retry", "5"),
            ("--retry-delay", "2"),
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
