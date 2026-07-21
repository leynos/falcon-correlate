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

import tomllib
import typing as typ
from pathlib import Path

PYPROJECT_PATH = Path(__file__).resolve().parents[2] / "pyproject.toml"


def _mutmut_config() -> dict[str, typ.Any]:
    """Return the parsed ``[tool.mutmut]`` table."""
    data = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    tool = typ.cast("dict[str, typ.Any]", data.get("tool", {}))
    mutmut = typ.cast("dict[str, typ.Any]", tool.get("mutmut", {}))
    assert mutmut, "pyproject.toml must declare a [tool.mutmut] table"
    return mutmut


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


def test_selected_bdd_tree_is_covered_by_source_paths_or_also_copy() -> None:
    """Every package the selected BDD tests import from must be mirrored.

    Guards against future imports of other out-of-tree packages by
    scanning the selected ``tests/bdd/`` tree for
    ``importlib.import_module`` calls naming a top-level package, and
    asserting each named package is either a source path or explicitly
    copied.
    """
    config = _mutmut_config()
    source_paths = typ.cast("list[str]", config.get("source_paths", []))
    also_copy = typ.cast("list[str]", config.get("also_copy", []))
    mirrored_roots = {
        Path(p).parts[0] for p in (*source_paths, *also_copy) if Path(p).parts
    }

    bdd_dir = PYPROJECT_PATH.parent / "tests" / "bdd"
    support_file = PYPROJECT_PATH.parent / "tests" / "_quickstart_support.py"
    imported_roots: set[str] = set()
    for py_file in (*bdd_dir.glob("*.py"), support_file):
        text = py_file.read_text(encoding="utf-8")
        if 'import_module(f"examples.' in text or "import_module('examples." in text:
            imported_roots.add("examples")

    assert imported_roots <= mirrored_roots, (
        f"tests/bdd/ imports packages {imported_roots - mirrored_roots} "
        "that are not covered by [tool.mutmut] source_paths or also_copy; "
        "add them to also_copy or the mutation baseline will fail"
    )
