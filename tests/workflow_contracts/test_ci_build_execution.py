"""Execute checked-in build and clean-import steps with a recording uv."""

from __future__ import annotations

import json
import os
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import] - runs checked-in Bash steps.
import sys
import textwrap
import typing as typ
from pathlib import Path

import pytest

from tests.workflow_contracts.workflow_documents import (
    REPO_ROOT,
    WORKFLOWS_DIR,
    parse_workflow,
)

_WHEEL = "falcon_correlate-0.2.0-py3-none-any.whl"
_SDIST = "falcon_correlate-0.2.0.tar.gz"


def _recording_uv(directory: Path) -> dict[str, str]:
    """Create a uv stand-in and its isolated command environment."""
    bin_directory = directory / "bin"
    bin_directory.mkdir()
    uv = bin_directory / "uv"
    uv.write_text(
        textwrap.dedent(r"""
            #!/usr/bin/env python3
            import json
            import os
            import shutil
            import sys
            from pathlib import Path

            args = sys.argv[1:]
            with Path(os.environ["UV_RECORD"]).open("a", encoding="utf-8") as log:
                log.write(json.dumps(args) + "\n")
            if args[:1] == ["build"]:
                destination = Path(args[args.index("--out-dir") + 1])
                destination.mkdir(parents=True, exist_ok=True)
                (destination / os.environ["WHEEL_NAME"]).write_bytes(b"wheel")
                (destination / os.environ["SDIST_NAME"]).write_bytes(b"sdist")
            elif args[:1] == ["venv"]:
                python = Path(args[-1]) / "bin" / "python"
                python.parent.mkdir(parents=True, exist_ok=True)
                python.write_text('#!/bin/sh\nexec "$TEST_PYTHON" -S "$@"\n')
                python.chmod(0o755)
                Path(os.environ["TEST_SITE"]).mkdir(parents=True, exist_ok=True)
            elif args[:2] == ["pip", "install"]:
                if not Path(args[-1]).is_file():
                    raise SystemExit("wheel is missing")
                source = Path(os.environ["PACKAGE_SOURCE"])
                if source.exists():
                    shutil.copyfile(
                        source, Path(os.environ["TEST_SITE"]) / "falcon_correlate.py"
                    )
            else:
                raise SystemExit(f"unexpected uv invocation: {args!r}")
        """).lstrip(),
        encoding="utf-8",
    )
    uv.chmod(0o755)
    environment = os.environ.copy()
    environment.pop("BASH_ENV", None)
    environment.pop("PYTHONHOME", None)
    environment.pop("PYTHONOPTIMIZE", None)
    environment.update({
        "PATH": f"{bin_directory}{os.pathsep}{environment.get('PATH', '')}",
        "UV_RECORD": str(directory / "uv-argv.jsonl"),
        "TEST_PYTHON": sys.executable,
        "TEST_SITE": str(directory / "site"),
        "PYTHONPATH": str(directory / "site"),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PACKAGE_SOURCE": str(directory / "package.py"),
        "IMPORT_MARKER": str(directory / "imported"),
        "WHEEL_NAME": _WHEEL,
        "SDIST_NAME": _SDIST,
    })
    return environment


def _run_script(
    script: str, cwd: Path, environment: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    """Execute a checked-in run body from an isolated working directory."""
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("the checked-in workflow step requires Bash")
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - checked-in run body.
        [bash, "-c", script],
        cwd=cwd,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
    )


def _named_step(steps: list[dict[str, typ.Any]], name: str) -> dict[str, typ.Any]:
    """Read the named step from a strictly parsed workflow."""
    return next(step for step in steps if step.get("name") == name)


def _recorded_calls(environment: dict[str, str]) -> list[list[str]]:
    """Read the uv argument vectors captured by the stand-in."""
    log = Path(environment["UV_RECORD"])
    assert log.is_file(), "the checked-in step must invoke uv"
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def test_composite_build_executes_uv_for_both_distributions(tmp_path: Path) -> None:
    """The checked-in composite build invokes uv and produces both artefacts."""
    action_path = REPO_ROOT / ".github/actions/pure-python-wheel/action.yml"
    action = parse_workflow(action_path.read_text(encoding="utf-8"), str(action_path))
    step = _named_step(action["runs"]["steps"], "Build sdist and wheel")
    environment = _recording_uv(tmp_path)
    environment["OUT_DIR"] = "dist"

    result = _run_script(step["run"], tmp_path, environment)

    assert result.returncode == 0, f"the build step failed: {result.stderr}"
    assert _recorded_calls(environment) == [["build", "--out-dir", "dist"]], (
        "the build must use the shared uv distribution path"
    )
    assert sorted(path.name for path in (tmp_path / "dist").iterdir()) == sorted([
        _SDIST,
        _WHEEL,
    ]), "the build step must produce an sdist and a wheel"


@pytest.mark.parametrize(
    ("import_mode", "expected_code"),
    [("clean", 0), ("celery", 1), ("httpx", 1), ("missing", 1)],
)
def test_clean_wheel_step_executes_import_and_rejects_extras(
    tmp_path: Path, import_mode: str, expected_code: int
) -> None:
    """The checked-in step imports the installed package and checks both extras."""
    ci_path = WORKFLOWS_DIR / "ci.yml"
    workflow = parse_workflow(ci_path.read_text(encoding="utf-8"), "ci.yml")
    step = _named_step(
        workflow["jobs"]["build"]["steps"], "Check the wheel imports without extras"
    )
    environment = _recording_uv(tmp_path)
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / _WHEEL).touch()
    site = tmp_path / "site"
    site.mkdir()
    for name in ("celery", "httpx"):
        (site / f"{name}.py").write_text("", encoding="utf-8")
    if import_mode != "missing":
        optional_import = f"import {import_mode}\n" if import_mode != "clean" else ""
        Path(environment["PACKAGE_SOURCE"]).write_text(
            "import os\nfrom pathlib import Path\n"
            "Path(os.environ['IMPORT_MARKER']).write_text('imported')\n"
            + optional_import,
            encoding="utf-8",
        )
    environment["DIST_DIR"] = str(dist)
    environment["VENV_DIR"] = str(tmp_path / "venv")

    result = _run_script(step["run"], tmp_path, environment)

    assert result.returncode == expected_code, (
        f"{import_mode} returned {result.returncode}: {result.stderr}"
    )
    expected_calls = [
        ["venv", "--clear", "--python", "3.13", environment["VENV_DIR"]],
        [
            "pip",
            "install",
            "--python",
            f"{environment['VENV_DIR']}/bin/python",
            str(dist / _WHEEL),
        ],
    ]
    assert _recorded_calls(environment) == expected_calls, (
        "the step must create a clean environment and install its built wheel"
    )
    if import_mode != "missing":
        assert Path(environment["IMPORT_MARKER"]).is_file(), (
            "the step must actually import the installed package"
        )


def test_bundle_step_uses_only_the_release_tag(tmp_path: Path) -> None:
    """The checked-in bundle step produces one tag-named provenance file."""
    release_path = WORKFLOWS_DIR / "release.yml"
    workflow = parse_workflow(release_path.read_text(encoding="utf-8"), "release.yml")
    step = _named_step(
        workflow["jobs"]["attest"]["steps"], "Name the provenance bundle after the tag"
    )
    source = tmp_path / "source.sigstore.json"
    source.write_bytes(b"signed provenance")
    environment = os.environ.copy()
    environment.pop("BASH_ENV", None)
    environment.update({"BUNDLE_PATH": str(source), "RELEASE_TAG": "v1.2.3rc1"})

    result = _run_script(step["run"], tmp_path, environment)

    assert result.returncode == 0, f"the bundle step failed: {result.stderr}"
    bundle_directory = tmp_path / "dist" / "attestations"
    assert [path.name for path in bundle_directory.iterdir()] == [
        "v1.2.3rc1.sigstore.json"
    ], "the bundle name must depend only on the tag"
    assert (bundle_directory / "v1.2.3rc1.sigstore.json").read_bytes() == (
        b"signed provenance"
    ), "the bundle step must preserve the provenance bytes"
