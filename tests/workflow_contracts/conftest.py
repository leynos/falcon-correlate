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
        "with record.open('a', encoding='utf-8') as stream:\n"
        "    stream.write(json.dumps(arguments) + '\\n')\n"
        "if '--output' in arguments:\n"
        "    output = Path(arguments[arguments.index('--output') + 1])\n"
        "    downloads = json.loads(os.environ.get('CURL_DOWNLOAD_CONTENTS', '{}'))\n"
        "    output.write_bytes(downloads[arguments[-1]].encode())\n"
        "else:\n"
        "    sys.stdout.write(os.environ.get('CURL_BODY', ''))\n"
        "    sys.stdout.write('\\n' + os.environ.get('CURL_STATUS', '200'))\n"
        "sys.stderr.write(os.environ.get('CURL_STDERR', ''))\n"
        "raise SystemExit(int(os.environ.get('CURL_EXIT', '0')))\n",
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
