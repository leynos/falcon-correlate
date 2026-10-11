"""Contract test for the ``[tool.mutmut]`` sandbox configuration.

``tests/bdd/test_quickstart_steps.py`` imports the runnable quickstart
example (via ``tests/_quickstart_support.py``) to keep the guide, the
example, and the behavioural scenario aligned. mutmut copies
``source_paths`` and the test tree into an isolated ``mutants/`` working
copy before running the suite; ``examples/`` sits outside
``source_paths``, so without an explicit ``also_copy`` entry the sandbox
lacks the package and the quickstart import fails with
``ModuleNotFoundError`` during baseline collection -- before any mutant
is generated (issue #100). This test pins that configuration so a future
edit cannot silently drop the entry and reintroduce the failing
baseline.
"""

from __future__ import annotations

import ast
import re
import tomllib
import typing as typ
from collections import deque
from pathlib import Path

import pytest
import yaml

PYPROJECT_PATH = Path(__file__).resolve().parents[2] / "pyproject.toml"
REPOSITORY_ROOT = PYPROJECT_PATH.parent
CI_WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"


def _mutmut_config() -> dict[str, typ.Any]:
    """Return the parsed ``[tool.mutmut]`` table."""
    data = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    tool = typ.cast("dict[str, typ.Any]", data.get("tool", {}))
    mutmut = typ.cast("dict[str, typ.Any]", tool.get("mutmut", {}))
    assert mutmut, "pyproject.toml must declare a [tool.mutmut] table"
    return mutmut


def _configured_paths(config: dict[str, typ.Any], key: str) -> tuple[str, ...]:
    """Return a mutmut path-list setting as an immutable sequence."""
    value = config.get(key, [])
    assert isinstance(value, list), f"{key} must be a list of paths"
    assert all(isinstance(path, str) for path in value), (
        f"{key} must contain only paths"
    )
    return tuple(typ.cast("list[str]", value))


def _import_root(path: str) -> str:
    """Return the importable root represented by a repository path."""
    parts = Path(path).parts
    if parts[0] == "src":
        return parts[1]
    return parts[0]


def _is_import_module(function: ast.expr) -> bool:
    """Return whether an expression names ``importlib.import_module``."""
    return bool(
        isinstance(function, ast.Name) and function.id == "import_module"
    ) or bool(isinstance(function, ast.Attribute) and function.attr == "import_module")


def _literal_module_name(argument: ast.expr) -> str | None:
    """Return the statically known module name prefix in an expression."""
    match argument:
        case ast.Constant(value=str() as module_name):
            return module_name
        case ast.JoinedStr(values=[ast.Constant(value=str() as prefix), *_]):
            return prefix.rstrip(".") or None
        case _:
            return None


def _dynamic_import_name(call: ast.Call) -> str | None:
    """Return the statically known portion of an ``import_module`` call."""
    if not _is_import_module(call.func) or not call.args:
        return None
    return _literal_module_name(call.args[0])


def _modules_for_node(node: ast.AST) -> tuple[str, ...]:
    """Return the absolute module names represented by one AST node."""
    match node:
        case ast.Import(names=names):
            return tuple(alias.name for alias in names)
        case ast.ImportFrom(level=0, module=str() as module_name):
            return (module_name,)
        case ast.Call():
            module_name = _dynamic_import_name(node)
            return (module_name,) if module_name else ()
        case _:
            return ()


def _imported_modules(source: str) -> set[str]:
    """Return absolute module names imported by Python source."""
    return {
        module_name
        for node in ast.walk(ast.parse(source))
        for module_name in _modules_for_node(node)
    }


def _selected_python_files(
    config: dict[str, typ.Any], repository_root: Path
) -> set[Path]:
    """Return every Python file selected by mutmut's pytest configuration."""
    selected_files: set[Path] = set()
    for configured_path in _configured_paths(
        config, "pytest_add_cli_args_test_selection"
    ):
        path = repository_root / configured_path
        assert path.is_dir() or (path.is_file() and path.suffix == ".py"), (
            f"pytest_add_cli_args_test_selection entry {configured_path!r} "
            "must name an existing directory or Python file"
        )
        if path.is_dir():
            selected_files.update(path.rglob("*.py"))
        else:
            selected_files.add(path)
    return selected_files


def _repository_module_path(module_name: str) -> Path | None:
    """Resolve a repository module name to its Python source file."""
    relative_path = Path(*module_name.split("."))
    for search_root in (REPOSITORY_ROOT, REPOSITORY_ROOT / "src"):
        module_path = (search_root / relative_path).with_suffix(".py")
        if module_path.is_file():
            return module_path
        package_path = search_root / relative_path / "__init__.py"
        if package_path.is_file():
            return package_path
    return None


def _configured_support_roots(config: dict[str, typ.Any]) -> set[str]:
    """Return copied roots available to selected tests outside source paths."""
    source_roots = {
        _import_root(path) for path in _configured_paths(config, "source_paths")
    }
    selected_roots = {
        _import_root(path)
        for path in _configured_paths(config, "pytest_add_cli_args_test_selection")
    }
    copied_roots = {
        _import_root(path) for path in _configured_paths(config, "also_copy")
    }
    return (selected_roots | copied_roots) - source_roots


def _repository_support_files(
    selected_files: set[Path], support_roots: set[str]
) -> set[Path]:
    """Return local support modules imported from copied sandbox roots."""
    files = set(selected_files)
    pending = deque(selected_files)
    while pending:
        source = pending.popleft().read_text(encoding="utf-8")
        for module_name in _imported_modules(source):
            if module_name.partition(".")[0] not in support_roots:
                continue
            support_file = _repository_module_path(module_name)
            if support_file is None or support_file in files:
                continue
            files.add(support_file)
            pending.append(support_file)
    return files


def _selected_and_support_files(config: dict[str, typ.Any]) -> set[Path]:
    """Return selected tests and repository support modules they import."""
    selected_files = _selected_python_files(config, REPOSITORY_ROOT)
    support_roots = _configured_support_roots(config)
    return _repository_support_files(selected_files, support_roots)


def _repository_import_roots() -> set[str]:
    """Return top-level Python package and module names in the repository."""
    roots = {
        child.name
        for child in REPOSITORY_ROOT.iterdir()
        if child.is_dir()
        and not child.name.startswith(".")
        and child.name != "src"
        and any(child.rglob("*.py"))
    }
    roots.update(path.stem for path in REPOSITORY_ROOT.glob("*.py"))
    source_root = REPOSITORY_ROOT / "src"
    roots.update(
        child.name
        for child in source_root.iterdir()
        if child.is_dir() and any(child.rglob("*.py"))
    )
    return roots


class TestMutmutConfig:
    """Keep mutmut's configured sandbox paths valid and complete."""

    def test_also_copy_mirrors_the_quickstart_examples_package(self) -> None:
        """``also_copy`` must mirror ``examples/`` into mutmut's sandbox.

        ``tests/bdd/`` is part of ``pytest_add_cli_args_test_selection``, and
        its quickstart steps import ``examples.quickstart.*``; the sandbox
        must contain that package or the baseline fails before mutants run.
        """
        also_copy = _mutmut_config().get("also_copy", [])
        assert isinstance(also_copy, list), "also_copy must be a list of paths"
        assert "examples/" in also_copy, (
            "also_copy must include 'examples/' so mutmut's mutants/ sandbox "
            "can resolve the quickstart example import "
            "(examples.quickstart.*) that tests/bdd/test_quickstart_steps.py "
            "depends on; without it the mutation baseline fails with "
            "ModuleNotFoundError before any mutant is generated (issue #100)"
        )

    def test_source_and_copy_paths_exist(self) -> None:
        """Configured source and copied sandbox paths must still exist."""
        config = _mutmut_config()
        for key in ("source_paths", "also_copy"):
            for configured_path in _configured_paths(config, key):
                assert (REPOSITORY_ROOT / configured_path).exists(), (
                    f"[tool.mutmut] {key} entry {configured_path!r} "
                    "must name an existing path"
                )

    @pytest.mark.parametrize(
        ("source", "expected_root"),
        [
            ("import fixtures.widget", "fixtures"),
            ("from fixtures import widget", "fixtures"),
            ('import_module("fixtures.widget")', "fixtures"),
            ('importlib.import_module(f"fixtures.{name}")', "fixtures"),
        ],
        ids=("import", "from-import", "dynamic", "dynamic-f-string"),
    )
    def test_import_scanner_detects_repository_package_imports(
        self, source: str, expected_root: str
    ) -> None:
        """The scanner detects static and dynamic package imports."""
        imported_roots = {
            module_name.partition(".")[0] for module_name in _imported_modules(source)
        }
        assert imported_roots == {expected_root}, (
            f"expected the scanner to detect repository root {expected_root!r}, "
            f"found {imported_roots!r}"
        )

    def test_missing_selected_file_has_a_clear_configuration_error(
        self, tmp_path: Path
    ) -> None:
        """Missing selected files fail at the config entry, not during reading."""
        config = {"pytest_add_cli_args_test_selection": ["tests/missing.py"]}
        error_message = (
            "pytest_add_cli_args_test_selection entry 'tests/missing.py' "
            "must name an existing directory or Python file"
        )
        with pytest.raises(
            AssertionError,
            match=re.escape(error_message),
        ):
            _selected_python_files(config, tmp_path)

    def test_selected_tests_are_covered_by_mutmut_sandbox_paths(self) -> None:
        """Every repository package selected tests import from must be mirrored.

        Guards against future imports of other out-of-tree packages by
        parsing all selected tests and their repository-local support modules,
        then asserting each imported repository package is a source path,
        selected test tree, or explicitly copied.
        """
        config = _mutmut_config()
        mirrored_roots = {
            _import_root(path)
            for key in (
                "source_paths",
                "also_copy",
                "pytest_add_cli_args_test_selection",
            )
            for path in _configured_paths(config, key)
        }
        repository_roots = _repository_import_roots()
        imported_roots = {
            module_name.partition(".")[0]
            for py_file in _selected_and_support_files(config)
            for module_name in _imported_modules(py_file.read_text(encoding="utf-8"))
        } & repository_roots

        assert imported_roots <= mirrored_roots, (
            f"selected tests import packages {imported_roots - mirrored_roots} "
            "that are not covered by [tool.mutmut] source_paths or also_copy; "
            "add them to also_copy or the mutation baseline will fail"
        )

    def test_pull_request_ci_checks_the_mutmut_sandbox(self) -> None:
        """The required Python 3.13 pull-request lane runs the real sandbox."""
        workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
        check_steps = [
            step
            for step in workflow["jobs"]["test"]["steps"]
            if step.get("name") == "Check mutmut sandbox"
        ]

        assert check_steps == [
            {
                "name": "Check mutmut sandbox",
                "if": "matrix.python-version == '3.13' "
                "&& github.event_name == 'pull_request'",
                "run": "make test-mutmut-sandbox",
            }
        ], "CI must run the mutmut sandbox for Python 3.13 pull requests"
