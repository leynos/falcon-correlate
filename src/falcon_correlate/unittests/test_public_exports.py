"""Unit tests for package public exports."""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path

from falcon_correlate.unittests.uuid7_helpers import assert_uuid7_hex

ATTRIBUTE_DOCSTRING_EXPORT_MODULES = {
    "RECOMMENDED_LOG_FORMAT": "falcon_correlate.middleware_utils",
    "correlation_id_var": "falcon_correlate.middleware_utils",
    "user_id_var": "falcon_correlate.middleware_utils",
}


def _module_syntax_tree(module_name: str) -> ast.Module:
    """Parse the source for a module.

    Parameters
    ----------
    module_name : str
        The importable module name to inspect.

    Returns
    -------
    ast.Module
        The parsed module syntax tree.

    """
    module = importlib.import_module(module_name)
    source_path = Path(inspect.getsourcefile(module) or "")
    return ast.parse(source_path.read_text(encoding="utf-8"))


def _assigns_name(node: ast.stmt, name: str) -> bool:
    """Return whether an AST node assigns a named module attribute.

    Parameters
    ----------
    node : ast.stmt
        The module-level statement to inspect.
    name : str
        The module attribute name to find.

    Returns
    -------
    bool
        True when the statement assigns ``name``.

    """
    match node:
        case ast.AnnAssign(target=ast.Name(id=target_name)):
            return target_name == name
        case ast.Assign(targets=targets):
            return any(
                isinstance(target, ast.Name) and target.id == name for target in targets
            )
        case _:
            return False


def _has_inline_attribute_docstring(module_name: str, name: str) -> bool:
    """Return whether a module attribute has an inline docstring.

    Parameters
    ----------
    module_name : str
        The importable module containing the attribute assignment.
    name : str
        The module attribute name to inspect.

    Returns
    -------
    bool
        True when a string literal immediately follows the assignment.

    """
    module_tree = _module_syntax_tree(module_name)
    for node, next_node in zip(module_tree.body, module_tree.body[1:], strict=False):
        if not _assigns_name(node, name):
            continue
        return (
            isinstance(next_node, ast.Expr)
            and isinstance(next_node.value, ast.Constant)
            and isinstance(next_node.value.value, str)
            and bool(next_node.value.value.strip())
        )
    return False


class TestPublicExports:
    """Tests for package public exports."""

    def test_public_exports_in_all(self) -> None:
        """Verify expected names are present in __all__."""
        import falcon_correlate
        from falcon_correlate import CorrelationIDMiddlewareASGI

        assert "CorrelationIDMiddleware" in falcon_correlate.__all__
        assert "CorrelationIDMiddlewareASGI" in falcon_correlate.__all__
        assert "CorrelationIDConfig" in falcon_correlate.__all__
        assert "default_uuid7_generator" in falcon_correlate.__all__
        assert (
            CorrelationIDMiddlewareASGI is falcon_correlate.CorrelationIDMiddlewareASGI
        ), (
            "expected imported CorrelationIDMiddlewareASGI to be "
            "falcon_correlate.CorrelationIDMiddlewareASGI but got different objects"
        )

    def test_default_uuid7_generator_importable_from_root(self) -> None:
        """Verify default_uuid7_generator can be imported from package root."""
        from falcon_correlate import default_uuid7_generator as gen

        value = gen()
        assert_uuid7_hex(value)

    def test_public_exports_are_documented(self) -> None:
        """Verify every public export has user-facing documentation."""
        import falcon_correlate

        for name in falcon_correlate.__all__:
            if name in ATTRIBUTE_DOCSTRING_EXPORT_MODULES:
                assert _has_inline_attribute_docstring(
                    ATTRIBUTE_DOCSTRING_EXPORT_MODULES[name], name
                ), f"expected {name} to have an inline attribute docstring"
                continue

            exported = getattr(falcon_correlate, name)
            assert inspect.getdoc(exported), f"expected {name} to have a docstring"
