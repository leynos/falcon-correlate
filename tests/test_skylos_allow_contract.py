"""Behavioural contracts for the `skylos-allow` Makefile boundary.

Make dry-run output cannot prove the arguments that a shell ultimately passes to
Skylos. These tests use a temporary executable recorder instead, avoiding any
mutation of the committed Skylos allow list.
"""

from __future__ import annotations

import json
import operator
import os
import shutil
import string
import subprocess  # ruff: ignore[suspicious-subprocess-import] - contracts invoke a fixed local executable.
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory

import hypothesis as hyp
import hypothesis.strategies as st

_MAKE_EXECUTABLE = shutil.which("make") or "make"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SHELL_ARGUMENT_TEXT = st.builds(
    lambda prefix, content, suffix: prefix + content + suffix,
    st.text(alphabet=" \t", max_size=4),
    st.text(
        alphabet=string.ascii_letters + string.digits + "_$;|&'\"()[]{}*?!\\`",
        min_size=1,
        max_size=40,
    ),
    st.text(alphabet=" \t", max_size=4),
)


def _run_skylos_allow(*arguments: str) -> subprocess.CompletedProcess[str]:
    """Run the whitelist boundary with `NAME` injected as it is under WSL."""
    make = shutil.which("make")
    assert make is not None, "the Skylos whitelist contract requires make on PATH"
    environment: dict[str, str] = {**os.environ, "NAME": "wsl-hostname"}
    environment.pop("REASON", None)
    environment.pop("SYMBOL", None)
    requested_values: dict[str, str] = {}
    for argument in arguments:
        name, value = argument.split("=", maxsplit=1)
        requested_values[name] = value
    environment.update(requested_values)
    command: list[str] = [make, "skylos-allow"]
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - fixed Make target and arguments.
        command,
        capture_output=True,
        check=False,
        cwd=_PROJECT_ROOT,
        env=environment,
        text=True,
    )


@hyp.settings(max_examples=25, deadline=None)
@hyp.given(value=st.text(alphabet=" \t", min_size=1, max_size=8))
def test_skylos_allow_rejects_missing_or_whitespace_values(value: str) -> None:
    """The whitelist target must reject absent and whitespace-only inputs."""
    requests = (
        ((), "SYMBOL"),
        (("SYMBOL=handler",), "REASON"),
        ((f"SYMBOL={value}", "REASON=reason"), "SYMBOL"),
        (("SYMBOL=handler", f"REASON={value}"), "REASON"),
    )
    for arguments, missing_name in requests:
        completed = _run_skylos_allow(*arguments)
        assert completed.returncode == 2, (
            f"Skylos whitelist boundary must reject {missing_name} with exit 2"
        )
        assert (
            f"Error: {missing_name} is required for a named whitelist exception"
            in completed.stderr
        ), f"Skylos whitelist boundary must name the missing {missing_name}"


@hyp.settings(max_examples=25, deadline=None)
@hyp.example(symbol="$(handler);*", reason='Loaded "$plugin" | registry')
@hyp.given(symbol=_SHELL_ARGUMENT_TEXT, reason=_SHELL_ARGUMENT_TEXT)
def test_skylos_allow_forwards_generated_argument_boundaries(
    symbol: str, reason: str
) -> None:
    """Every non-empty generated value reaches Skylos as one argument."""
    configuration_path = _PROJECT_ROOT / "pyproject.toml"
    configuration_before = configuration_path.read_bytes()
    with TemporaryDirectory() as temporary_directory:
        recorded_arguments = Path(temporary_directory, "arguments.json")
        recorder = Path(temporary_directory, "skylos-recorder")
        recorder.write_text(
            "#!/usr/bin/env python3\n"
            "import json\n"
            "import os\n"
            "import sys\n"
            "from pathlib import Path\n\n"
            'Path(os.environ["SKYLOS_ARGUMENTS_PATH"]).write_text(\n'
            "    json.dumps(sys.argv[1:]), encoding='utf-8'\n"
            ")\n",
            encoding="utf-8",
        )
        recorder.chmod(0o755)
        environment = {
            **os.environ,
            "NAME": "wsl-hostname",
            "SKYLOS_ARGUMENTS_PATH": str(recorded_arguments),
            "SKYLOS_WHITELIST_LOCK": str(
                Path(temporary_directory, "skylos-whitelist.lock")
            ),
            "SYMBOL": symbol,
            "REASON": reason,
        }
        completed = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - fixed Make target and recorder.
            (
                _MAKE_EXECUTABLE,
                "--no-print-directory",
                f"SKYLOS_CLI={recorder}",
                "skylos-allow",
            ),
            capture_output=True,
            check=False,
            cwd=_PROJECT_ROOT,
            env=environment,
            text=True,
        )

        assert completed.returncode == 0, (
            "Skylos whitelist forwarding must complete successfully: "
            f"{completed.stderr}"
        )
        assert json.loads(recorded_arguments.read_text(encoding="utf-8")) == [
            "whitelist",
            symbol,
            "--reason",
            reason,
        ], "Skylos must receive each generated value as exactly one argument"
    assert configuration_path.read_bytes() == configuration_before, (
        "Skylos whitelist forwarding must not mutate pyproject.toml"
    )


def _write_concurrent_whitelist_recorder(recorder: Path) -> None:
    """Write a delayed fake Skylos CLI for concurrent whitelist updates."""
    recorder.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import os\n"
        "import sys\n"
        "import time\n"
        "from pathlib import Path\n\n"
        "if (len(sys.argv) != 5 or sys.argv[1] != 'whitelist'\n"
        "        or sys.argv[3] != '--reason'):\n"
        "    raise SystemExit('unexpected Skylos whitelist arguments')\n"
        "whitelist = Path(os.environ['SKYLOS_WHITELIST_PATH'])\n"
        "entries = (json.loads(whitelist.read_text(encoding='utf-8'))\n"
        "           if whitelist.exists() else {})\n"
        "time.sleep(float(os.environ['SKYLOS_DELAY_SECONDS']))\n"
        "entries[sys.argv[2]] = sys.argv[4]\n"
        "whitelist.write_text(json.dumps(entries), encoding='utf-8')\n",
        encoding="utf-8",
    )
    recorder.chmod(0o755)


@hyp.settings(max_examples=8, deadline=None)
@hyp.example(
    updates=[
        ("handler$(one)", 'reason "one"', 65),
        ("handler;two", "reason | two", 20),
        ("handler three", "reason `three`", 45),
    ]
)
@hyp.given(
    updates=st.lists(
        st.tuples(
            _SHELL_ARGUMENT_TEXT,
            _SHELL_ARGUMENT_TEXT,
            st.integers(min_value=20, max_value=80),
        ),
        min_size=2,
        max_size=5,
        unique_by=operator.itemgetter(0),
    )
)
def test_skylos_allow_serializes_concurrent_whitelist_updates(
    updates: list[tuple[str, str, int]],
) -> None:
    """Concurrent whitelist updates retain each generated symbol-reason pair."""
    with TemporaryDirectory() as temporary_directory:
        temporary_root = Path(temporary_directory)
        whitelist_path = temporary_root / "whitelist.json"
        lock_path = temporary_root / "skylos-whitelist.lock"
        recorder = temporary_root / "skylos-recorder"
        _write_concurrent_whitelist_recorder(recorder)

        processes: list[subprocess.Popen[str]] = []
        with ExitStack() as process_context:
            try:
                for symbol, reason, delay_milliseconds in updates:
                    environment = {
                        **os.environ,
                        "NAME": "wsl-hostname",
                        "SYMBOL": symbol,
                        "REASON": reason,
                        "SKYLOS_DELAY_SECONDS": str(delay_milliseconds / 1000),
                        "SKYLOS_WHITELIST_PATH": str(whitelist_path),
                    }
                    command = [
                        _MAKE_EXECUTABLE,
                        "--no-print-directory",
                        "-f",
                        str(_PROJECT_ROOT / "Makefile"),
                        f"SKYLOS_CLI={recorder}",
                        f"SKYLOS_WHITELIST_LOCK={lock_path}",
                        "skylos-allow",
                    ]
                    processes.append(
                        process_context.enter_context(
                            subprocess.Popen(  # ruff: ignore[subprocess-without-shell-equals-true] - fixed Make target and recorder.
                                command,
                                cwd=temporary_root,
                                env=environment,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True,
                            )
                        )
                    )

                for process, update in zip(processes, updates, strict=True):
                    _, stderr = process.communicate(timeout=30)
                    assert process.returncode == 0, (
                        "concurrent Skylos whitelist update must succeed for "
                        f"{update[0]!r}: {stderr}"
                    )
            finally:
                for process in processes:
                    if process.poll() is None:
                        process.kill()
                for process in processes:
                    process.communicate()

        assert json.loads(whitelist_path.read_text(encoding="utf-8")) == {
            symbol: reason for symbol, reason, _ in updates
        }, "serialized Skylos updates must preserve every symbol and its reason"
