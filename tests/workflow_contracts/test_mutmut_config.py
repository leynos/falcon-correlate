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
import tomllib
import typing as typ
from collections import deque
from pathlib import Path

import pytest

PYPROJECT_PATH = Path(__file__).resolve().parents[2] / "pyproject.toml"
REPOSITORY_ROOT = PYPROJECT_PATH.parent


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


def _dynamic_import_name(call: ast.Call) -> str | None:
    """Return the statically known portion of an ``import_module`` call."""
    function = call.func
    is_import_module = (
        isinstance(function, ast.Name) and function.id == "import_module"
    ) or (isinstance(function, ast.Attribute) and function.attr == "import_module")
    if not is_import_module or not call.args:
        return None

    argument = call.args[0]
    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
        return argument.value
    if isinstance(argument, ast.JoinedStr):
        prefix = ""
        for value in argument.values:
            if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
                break
            prefix += value.value
        return prefix.rstrip(".") or None
    return None


def _imported_modules(source: str) -> set[str]:
    """Return absolute module names imported by Python source."""
    modules: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module_name = node.module if node.level == 0 else None
            if module_name:
                modules.add(module_name)
        elif isinstance(node, ast.Call) and (module_name := _dynamic_import_name(node)):
            modules.add(module_name)
    return modules


def _selected_python_files(config: dict[str, typ.Any]) -> set[Path]:
    """Return every Python file selected by mutmut's pytest configuration."""
    selected_files: set[Path] = set()
    for configured_path in _configured_paths(
        config, "pytest_add_cli_args_test_selection"
    ):
        path = REPOSITORY_ROOT / configured_path
        if path.is_dir():
            selected_files.update(path.rglob("*.py"))
        elif path.suffix == ".py":
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


def _selected_and_support_files(config: dict[str, typ.Any]) -> set[Path]:
    """Return selected tests and repository support modules they import."""
    selected_files = _selected_python_files(config)
    source_roots = {
        _import_root(path) for path in _configured_paths(config, "source_paths")
    }
    support_roots = {
        _import_root(path)
        for path in _configured_paths(config, "pytest_add_cli_args_test_selection")
    } - source_roots

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


def test_also_copy_mirrors_the_quickstart_examples_package() -> None:
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
    source: str, expected_root: str
) -> None:
    """The scanner detects static and dynamic package imports."""
    imported_roots = {
        module_name.partition(".")[0] for module_name in _imported_modules(source)
    }
    assert imported_roots == {expected_root}


def test_selected_tests_are_covered_by_mutmut_sandbox_paths() -> None:
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
