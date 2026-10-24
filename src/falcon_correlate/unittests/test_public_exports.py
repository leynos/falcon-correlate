"""Unit tests for package public exports."""

from __future__ import annotations

import ast
import importlib
import importlib.util
import inspect
import os
import subprocess  # ruff: ignore[suspicious-subprocess-import] -- child isolates module state.
import sys
from pathlib import Path

import pytest

from falcon_correlate.unittests.uuid7_helpers import assert_uuid7_hex

ATTRIBUTE_DOCSTRING_EXPORT_MODULES = {
    "MetricsRecorder": "falcon_correlate.middleware_metrics",
    "RECOMMENDED_LOG_FORMAT": "falcon_correlate.middleware_utils",
    "correlation_id_var": "falcon_correlate.middleware_utils",
    "user_id_var": "falcon_correlate.middleware_utils",
}
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_NATIVE_MODULE_IMPORT_TIMEOUT_SECONDS = 120


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
        case ast.TypeAlias(name=ast.Name(id=target_name)):
            return target_name == name
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


def _assert_public_export_is_documented(name: str, exported: object) -> None:
    """Assert that a public export has documentation appropriate to its kind."""
    if name in ATTRIBUTE_DOCSTRING_EXPORT_MODULES:
        assert _has_inline_attribute_docstring(
            ATTRIBUTE_DOCSTRING_EXPORT_MODULES[name], name
        ), f"expected {name} to have an inline attribute docstring"
        return

    documentation = inspect.getdoc(exported)
    if not (inspect.isclass(exported) or callable(exported)):
        type_documentation = inspect.getdoc(type(exported))
        assert documentation, f"expected {name} to have value-specific documentation"
        assert documentation != type_documentation, (
            f"expected {name} to have value-specific documentation rather than "
            "documentation inherited from its type"
        )
        msg = (
            f"expected non-callable export {name} to be listed in "
            "ATTRIBUTE_DOCSTRING_EXPORT_MODULES"
        )
        raise AssertionError(msg)

    assert documentation, f"expected {name} to have a docstring"


class TestPublicExports:
    """Tests for package public exports."""

    def test_public_exports_in_all(self) -> None:
        """Verify __all__ contains exactly the intended package API names."""
        import falcon_correlate
        from falcon_correlate import CorrelationIDMiddlewareASGI

        expected_exports = {
            "RECOMMENDED_LOG_FORMAT",
            "AsyncCorrelationIDTransport",
            "ContextualLogFilter",
            "CorrelationIDConfig",
            "CorrelationIDMiddleware",
            "CorrelationIDMiddlewareASGI",
            "CorrelationIDSelectionEvent",
            "CorrelationIDTransport",
            "IncomingIDOutcome",
            "MetricsRecorder",
            "SourceTrust",
            "async_request_with_correlation_id",
            "clear_correlation_id_in_worker",
            "configure_celery_correlation",
            "correlation_id_var",
            "default_uuid7_generator",
            "default_uuid_validator",
            "propagate_correlation_id_to_celery",
            "request_with_correlation_id",
            "setup_correlation_id_in_worker",
            "user_id_var",
        }
        actual_exports = set(falcon_correlate.__all__)
        missing_exports = expected_exports.difference(actual_exports)
        unexpected_exports = actual_exports.difference(expected_exports)
        assert not missing_exports, (
            f"expected exports missing from __all__: {sorted(missing_exports)}"
        )
        assert not unexpected_exports, (
            f"unexpected exports in __all__: {sorted(unexpected_exports)}"
        )
        failure_message = (
            "expected condition: CorrelationIDMiddlewareASGI is falcon_cor..."
        )
        assert (
            CorrelationIDMiddlewareASGI is falcon_correlate.CorrelationIDMiddlewareASGI
        ), failure_message

    def test_removed_hello_api_and_modules_are_absent(self) -> None:
        """Verify the removed template API has no importable remnants.

        Notes
        -----
        The root package must not expose the function, and import resolution
        must not find either deleted implementation module.
        """
        import falcon_correlate

        assert not hasattr(falcon_correlate, "hello"), (
            "package root must not expose the removed hello function"
        )
        assert importlib.util.find_spec("falcon_correlate.pure") is None, (
            "removed pure module must not be importable"
        )
        assert importlib.util.find_spec("falcon_correlate._hello") is None, (
            "removed hello shim must not be importable"
        )

    def test_package_import_does_not_load_optional_native_module(self) -> None:
        """Verify package import does not load the optional native module.

        Notes
        -----
        A child interpreter starts with an empty module cache, so this check
        observes the package import boundary directly.
        """
        script = """
import sys

import falcon_correlate

assert "_falcon_correlate_rs" not in sys.modules
"""
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("PYTEST_")
        }
        result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed child interpreter and script.
            [sys.executable, "-c", script],
            check=False,
            cwd=_PROJECT_ROOT,
            env=environment,
            text=True,
            capture_output=True,
            timeout=_NATIVE_MODULE_IMPORT_TIMEOUT_SECONDS,
        )

        assert result.returncode == 0, (
            "Package import should not load the optional native module.\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    def test_default_uuid7_generator_importable_from_root(self) -> None:
        """Verify default_uuid7_generator can be imported from package root."""
        from falcon_correlate import default_uuid7_generator as gen

        value = gen()
        assert_uuid7_hex(value)

    def test_metrics_symbols_importable_from_middleware(self) -> None:
        """Verify metrics API symbols are also exposed from middleware."""
        from falcon_correlate import middleware

        expected = {
            "CorrelationIDSelectionEvent",
            "IncomingIDOutcome",
            "MetricsRecorder",
            "SourceTrust",
        }
        assert expected.issubset(middleware.__all__), (
            f"expected middleware exports {expected!r}"
        )

    def test_public_exports_are_documented(self) -> None:
        """Verify every public export has user-facing documentation."""
        import falcon_correlate

        for name in falcon_correlate.__all__:
            exported = getattr(falcon_correlate, name)
            _assert_public_export_is_documented(name, exported)

    def test_plain_builtin_instance_requires_attribute_docstring_mapping(self) -> None:
        """Reject builtin instances documented only by their type."""
        exported = "plain instance"

        failure_message = (
            "expected condition: inspect.getdoc(exported) == inspect.getdo..."
        )
        assert inspect.getdoc(exported) == inspect.getdoc(type(exported)), (
            failure_message
        )
        with pytest.raises(AssertionError, match="inherited from its type"):
            _assert_public_export_is_documented("plain_instance", exported)

    def test_mapped_attribute_export_uses_inline_docstring(self) -> None:
        """Accept mapped attributes with an inline attribute docstring."""
        import falcon_correlate

        name = "RECOMMENDED_LOG_FORMAT"
        _assert_public_export_is_documented(name, getattr(falcon_correlate, name))
