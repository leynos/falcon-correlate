"""Subprocess contracts for the isolated Pylint toolchains."""

from __future__ import annotations

import dataclasses as dc
import json
import os
import re
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import] - tests intentionally validate CLI toolchains.
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE_PATH = REPOSITORY_ROOT / "Makefile"
WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
PEP_695_FIXTURE = REPOSITORY_ROOT / "testdata" / "pylint_toolchain" / "valid_pep695.py"
TOOL_TIMEOUT_SECONDS = 180
PYLINT_ANALYSIS_MESSAGES = (
    "syntax-error,astroid-error,parse-error,config-parse-error,method-check-failed,"
    "raw-checker-failed,bad-plugin-value"
)


@dc.dataclass(frozen=True, slots=True)
class _Toolchains:
    """Commands for the isolated classic and DF12 Pylint environments."""

    classic: tuple[str, ...]
    df12: tuple[str, ...]


def _makefile_pin(name: str) -> str:
    """Return one Makefile pin."""
    match = re.search(
        rf"^{name} \?= ([^\s]+)$", MAKEFILE_PATH.read_text(), re.MULTILINE
    )
    assert match is not None, f"Makefile must pin {name}"
    value = match.group(1)
    reference = re.fullmatch(r"\$\(([^)]+)\)", value)
    return _makefile_pin(reference.group(1)) if reference is not None else value


def _run(command: list[str] | tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    """Run one toolchain command from the repository root."""
    environment = os.environ | {
        "UV_CACHE_DIR": str(REPOSITORY_ROOT / ".uv-cache"),
        "UV_TOOL_DIR": str(REPOSITORY_ROOT / ".uv-tools"),
    }
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - fixed commands validate repository-owned tools.
        command,
        check=False,
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        env=environment,
        text=True,
        timeout=TOOL_TIMEOUT_SECONDS,
    )


def _require_success(result: subprocess.CompletedProcess[str]) -> None:
    """Fail with complete process diagnostics unless a command succeeded."""
    assert result.returncode == 0, (
        f"Command failed with {result.returncode}:\nstdout:\n{result.stdout}"
        f"\nstderr:\n{result.stderr}"
    )


def _tool_command(*, python: str, source: str) -> tuple[str, ...]:
    """Build the same isolated tool command used by the Makefile."""
    uv = shutil.which("uv")
    assert uv is not None, "uv must be available to run Pylint toolchains"
    return (
        uv,
        "tool",
        "run",
        "--isolated",
        "--python",
        python,
        "--from",
        source,
        "--with",
        f"pylint=={_makefile_pin('PYLINT_VERSION')}",
        "--with",
        f"astroid=={_makefile_pin('ASTROID_VERSION')}",
    )


@pytest.fixture(scope="module")
def toolchains() -> _Toolchains:
    """Provision the pinned PyPy binary and return both lint tool commands."""
    _require_success(_run(["make", "--no-print-directory", "prepare-pylint-python"]))
    lint_runtime = REPOSITORY_ROOT / ".lint-tools" / "pypy3.12-v8.0.0-linux64"
    classic_python = lint_runtime / "bin" / "pypy3.12"
    assert classic_python.is_file(), "The pinned PyPy executable must be provisioned"
    return _Toolchains(
        classic=_tool_command(
            python=str(classic_python),
            source=f"pylint=={_makefile_pin('PYLINT_VERSION')}",
        ),
        df12=_tool_command(
            python=_makefile_pin("DF12_PYTHON"),
            source=(
                "git+https://github.com/leynos/df12-python-lints.git@"
                f"{_makefile_pin('DF12_PYTHON_LINTS_REF')}"
            ),
        ),
    )


def test_classic_pylint_toolchain_has_the_pinned_pypy_identity(
    toolchains: _Toolchains,
) -> None:
    """Classic Pylint must run on the pinned PyPy 3.12 binary."""
    identity = textwrap.dedent(
        """
        import astroid
        import json
        import pylint
        import sys

        print(json.dumps({
            "implementation": sys.implementation.name,
            "python": sys.version_info[:2],
            "pypy": sys.pypy_version_info[:3],
            "pylint": pylint.__version__,
            "astroid": astroid.__version__,
        }))
        """
    )
    result = _run([*toolchains.classic, "python", "-c", identity])
    _require_success(result)
    expected = {
        "implementation": "pypy",
        "python": [3, 12],
        "pypy": [8, 0, 0],
        "pylint": _makefile_pin("PYLINT_VERSION"),
        "astroid": _makefile_pin("ASTROID_VERSION"),
    }
    assert json.loads(result.stdout) == expected, (
        "Classic Pylint must run with the Makefile's pinned PyPy toolchain"
    )


def test_df12_pylint_toolchain_has_the_pinned_cpython_identity(
    toolchains: _Toolchains,
) -> None:
    """DF12 Pylint must run separately under CPython 3.14."""
    identity = textwrap.dedent(
        """
        import astroid
        import importlib.util
        import json
        import pylint
        import sys

        print(json.dumps({
            "implementation": sys.implementation.name,
            "python": sys.version_info[:2],
            "pylint": pylint.__version__,
            "astroid": astroid.__version__,
            "df12": importlib.util.find_spec("df12_python_lints") is not None,
        }))
        """
    )
    result = _run([*toolchains.df12, "python", "-c", identity])
    _require_success(result)
    expected = {
        "implementation": "cpython",
        "python": [3, 14],
        "pylint": _makefile_pin("DF12_PYLINT_VERSION"),
        "astroid": _makefile_pin("DF12_ASTROID_VERSION"),
        "df12": True,
    }
    assert json.loads(result.stdout) == expected, (
        "DF12 Pylint must run with its separately pinned CPython toolchain"
    )


def test_classic_astroid_parses_python_312_generic_syntax(
    toolchains: _Toolchains,
) -> None:
    """Astroid must produce PEP 695 nodes rather than merely avoid a crash."""
    parser = textwrap.dedent(
        """
        from astroid import nodes, parse
        from pathlib import Path
        import sys

        module = parse(Path(sys.argv[1]).read_text(encoding="utf-8"))
        type_alias = next(
            node for node in module.body if isinstance(node, nodes.TypeAlias)
        )
        function = next(
            node for node in module.body if isinstance(node, nodes.FunctionDef)
        )
        assert type_alias.type_params
        assert function.type_params
        print(type_alias.name.name, function.name)
        """
    )
    result = _run([*toolchains.classic, "python", "-c", parser, str(PEP_695_FIXTURE)])
    _require_success(result)
    assert result.stdout.strip() == "Pair pair", (
        "Astroid must expose both the generic alias and generic function"
    )


def test_classic_pylint_reports_an_enabled_diagnostic_for_python_312_syntax(
    tmp_path: Path, toolchains: _Toolchains
) -> None:
    """Classic Pylint must analyse, and fail on, a valid Python 3.12 module."""
    source = tmp_path / "classic_violation.py"
    source.write_text(
        (
            "type Pair[T] = tuple[T, T]\n\n"
            "def contains[T](item: T) -> bool:\n"
            '    return item == "a" or item == "b"\n'
        ),
        encoding="utf-8",
    )
    result = _run([
        *toolchains.classic,
        "pylint",
        "--rcfile=pyproject.toml",
        "--jobs=1",
        "--disable=all",
        f"--enable=consider-using-in,{PYLINT_ANALYSIS_MESSAGES}",
        str(source),
    ])
    assert result.returncode != 0, "An enabled classic Pylint diagnostic must fail"
    assert "consider-using-in" in result.stdout, (
        "Classic Pylint must report the enabled diagnostic for PEP 695 source"
    )


def test_classic_pylint_reports_syntax_errors_directly(
    tmp_path: Path, toolchains: _Toolchains
) -> None:
    """Direct Pylint must fail a syntax error without relying on Ruff."""
    source = tmp_path / "invalid.py"
    source.write_text("def broken(:\n", encoding="utf-8")
    result = _run([
        *toolchains.classic,
        "pylint",
        "--rcfile=pyproject.toml",
        "--jobs=1",
        "--disable=all",
        f"--enable={PYLINT_ANALYSIS_MESSAGES}",
        str(source),
    ])
    assert result.returncode != 0, "A syntax error must make direct Pylint fail"
    assert "syntax-error" in result.stdout, (
        "Classic Pylint must report a syntax diagnostic for invalid source"
    )


def test_make_propagates_classic_pylint_failures(
    tmp_path: Path, toolchains: _Toolchains
) -> None:
    """The Make entry point must preserve Pylint's non-zero exit status."""
    source = tmp_path / "invalid.py"
    source.write_text("def broken(:\n", encoding="utf-8")
    result = _run([
        "make",
        "--no-print-directory",
        "classic-pylint",
        f"PYLINT_TARGETS={source}",
    ])
    assert result.returncode != 0, "make classic-pylint must fail when Pylint fails"
    assert "syntax-error" in result.stdout, (
        "make classic-pylint must retain Pylint's syntax diagnostic"
    )


def test_pypy_live_object_inspection_needs_no_shim(toolchains: _Toolchains) -> None:
    """Astroid must inspect the historical PyPy descriptor paths without a shim."""
    inspection = textwrap.dedent(
        """
        from astroid import MANAGER
        import builtins
        import types

        function_module = MANAGER.ast_from_module(types)
        builtins_module = MANAGER.ast_from_module(builtins)
        function_type = next(function_module.getattr("FunctionType")[0].infer())
        assert function_type.getattr("__text_signature__")
        list_node = builtins_module.getattr("list")[0]
        assert list_node.getattr("__class_getitem__")
        print("live objects inspected")
        """
    )
    result = _run([*toolchains.classic, "python", "-c", inspection])
    _require_success(result)
    assert result.stdout.strip() == "live objects inspected", (
        "Astroid must inspect PyPy descriptor and generic live-object paths"
    )


def test_df12_pylint_reports_a_configured_plugin_diagnostic(
    tmp_path: Path, toolchains: _Toolchains
) -> None:
    """DF12 Pylint must fail an enabled plug-in diagnostic on CPython 3.14."""
    source = tmp_path / "df12_violation.py"
    source.write_text("assert True\n", encoding="utf-8")
    result = _run([
        *toolchains.df12,
        "pylint",
        "--rcfile=pyproject.toml",
        "--jobs=1",
        "--disable=all",
        "--load-plugins=df12_python_lints",
        f"--enable=assert-missing-message,{PYLINT_ANALYSIS_MESSAGES}",
        str(source),
    ])
    assert result.returncode != 0, "An enabled DF12 diagnostic must fail"
    assert "assert-missing-message" in result.stdout, (
        "DF12 Pylint must report the enabled plug-in diagnostic"
    )


def test_classic_toolchain_cannot_load_the_df12_plugin(toolchains: _Toolchains) -> None:
    """The baseline PyPy environment must remain independent of DF12."""
    result = _run([
        *toolchains.classic,
        "python",
        "-c",
        (
            "import importlib.util; "
            "assert importlib.util.find_spec('df12_python_lints') is None"
        ),
    ])
    _require_success(result)


def test_pylint_toolchains_leave_the_project_virtualenv_unchanged(
    toolchains: _Toolchains,
) -> None:
    """Lint tool environments must not replace the project virtual environment."""
    interpreter = REPOSITORY_ROOT / ".venv" / "bin" / "python"
    assert interpreter.is_file(), (
        "make test must run from the project virtual environment"
    )
    before = _run([str(interpreter), "-c", "import sys; print(sys.executable)"])
    _require_success(before)
    verification = _run(["make", "--no-print-directory", "verify-pylint-toolchains"])
    _require_success(verification)
    after = _run([str(interpreter), "-c", "import sys; print(sys.executable)"])
    _require_success(after)
    assert after.stdout == before.stdout, "Pylint toolchains must not replace .venv"


@pytest.mark.parametrize(
    ("target", "assignment"),
    [
        ("verify-classic-pylint", f"PYLINT_PYTHON={sys.executable}"),
        ("verify-df12-pylint", "DF12_PYTHON=3.12"),
    ],
)
def test_make_rejects_lint_runtime_overrides(target: str, assignment: str) -> None:
    """Make must verify the executable selected by caller overrides."""
    result = _run(["make", "--no-print-directory", target, assignment])
    assert result.returncode != 0, (
        "Lint toolchain verification must reject an override with the wrong runtime"
    )


def test_ci_runs_make_lint_without_making_failure_optional() -> None:
    """The CI lint lane must propagate the Makefile lint result."""
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    lint_job = workflow["jobs"]["lint"]
    lint_step = next(
        step for step in lint_job["steps"] if step.get("name") == "Run linters"
    )
    assert lint_step["run"] == "make lint", (
        "The CI lint step must run the complete Makefile lint target"
    )
    assert lint_step.get("continue-on-error") is not True, (
        "The CI lint step must not make failures optional"
    )
