"""Recording command stand-ins for release workflow script tests."""

from __future__ import annotations

import os
import stat
import typing as typ

import pytest

if typ.TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def curl_argv_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Install a recording curl stand-in for index and file requests."""
    bin_directory = tmp_path / "curl-bin"
    bin_directory.mkdir()
    curl = bin_directory / "curl"
    curl.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n\n"
        "arguments = sys.argv[1:]\n"
        "record = Path(os.environ['CURL_ARGV_PATH'])\n"
        "calls = (\n"
        "    [json.loads(line) for line in record.read_text().splitlines()]\n"
        "    if record.exists() else []\n"
        ")\n"
        "calls.append(arguments)\n"
        "record.write_text(\n"
        "    ''.join(json.dumps(call) + '\\n' for call in calls),\n"
        "    encoding='utf-8',\n"
        ")\n"
        "responses = json.loads(os.environ.get('CURL_RESPONSES', '[]'))\n"
        "response = (\n"
        "    responses[min(len(calls) - 1, len(responses) - 1)]\n"
        "    if responses else {}\n"
        ")\n"
        "if '--output' in arguments:\n"
        "    output = Path(arguments[arguments.index('--output') + 1])\n"
        "    downloads = json.loads(os.environ.get('CURL_DOWNLOAD_CONTENTS', '{}'))\n"
        "    output.write_bytes(downloads[arguments[-1]].encode())\n"
        "else:\n"
        "    body = response.get('body', os.environ.get('CURL_BODY', ''))\n"
        "    status = response.get('status', os.environ.get('CURL_STATUS', '200'))\n"
        "    sys.stdout.write(body)\n"
        "    sys.stdout.write('\\n' + status)\n"
        "sys.stderr.write(response.get('stderr', os.environ.get('CURL_STDERR', '')))\n"
        "exit_code = response.get('exit_code', os.environ.get('CURL_EXIT', '0'))\n"
        "raise SystemExit(int(exit_code))\n",
        encoding="utf-8",
    )
    curl.chmod(curl.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    record = tmp_path / "curl-argv.jsonl"
    monkeypatch.setenv("CURL_ARGV_PATH", str(record))
    monkeypatch.setenv("PATH", f"{bin_directory}{os.pathsep}{os.environ['PATH']}")
    return record


@pytest.fixture
def gh_argv_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Install a recording gh stand-in with per-call scripted responses."""
    bin_directory = tmp_path / "gh-bin"
    bin_directory.mkdir()
    gh = bin_directory / "gh"
    gh.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n\n"
        "record = Path(os.environ['GH_ARGV_PATH'])\n"
        "calls = (\n"
        "    [json.loads(line) for line in record.read_text().splitlines()]\n"
        "    if record.exists() else []\n"
        ")\n"
        "calls.append(sys.argv[1:])\n"
        "record.write_text(\n"
        "    ''.join(json.dumps(call) + '\\n' for call in calls),\n"
        "    encoding='utf-8',\n"
        ")\n"
        "responses = json.loads(os.environ.get('GH_RESPONSES', '[{}]'))\n"
        "response = responses[min(len(calls) - 1, len(responses) - 1)]\n"
        "sys.stdout.write(response.get('stdout', ''))\n"
        "sys.stderr.write(response.get('stderr', ''))\n"
        "raise SystemExit(int(response.get('exit_code', 0)))\n",
        encoding="utf-8",
    )
    gh.chmod(gh.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    record = tmp_path / "gh-argv.jsonl"
    monkeypatch.setenv("GH_ARGV_PATH", str(record))
    monkeypatch.setenv("PATH", f"{bin_directory}{os.pathsep}{os.environ['PATH']}")
    return record


@pytest.fixture
def pypi_stage_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, Path]:
    """Configure common environment paths for a PyPI staging workflow step."""
    distributions = tmp_path / "dist"
    staging = tmp_path / "staging"
    output = tmp_path / "github-output"
    monkeypatch.setenv("DIST_DIR", str(distributions))
    monkeypatch.setenv("STAGING_DIR", str(staging))
    monkeypatch.setenv("SIMPLE_INDEX_URL", "https://pypi.org/simple/falcon-correlate/")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    return distributions, staging, output
