"""Tests for adapter dependencies on shared middleware primitives."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

_ADAPTER_DIRECTORY = Path(__file__).resolve().parents[1]


def _targets_middleware(node: ast.AST) -> bool:
    """Return whether an import node targets the middleware orchestration."""
    match node:
        case ast.Import(names=names):
            return any(
                alias.name == "falcon_correlate.middleware"
                or alias.name.startswith("falcon_correlate.middleware.")
                for alias in names
            )
        case ast.ImportFrom(level=level, module="middleware") if level >= 1:
            return True
        case ast.ImportFrom(module="falcon_correlate.middleware"):
            return True
        case ast.ImportFrom(module="falcon_correlate", names=names):
            return any(alias.name == "middleware" for alias in names)
        case ast.ImportFrom(level=level, module=None, names=names) if level >= 1:
            return any(alias.name == "middleware" for alias in names)
        case _:
            return False


@pytest.mark.parametrize(
    "adapter_name",
    [
        pytest.param("httpx", id="httpx"),
        pytest.param("celery", id="celery"),
    ],
)
def test_adapter_source_does_not_import_middleware(
    adapter_name: str,
) -> None:
    """Adapters should not depend on Falcon middleware orchestration."""
    source_path = _ADAPTER_DIRECTORY / f"{adapter_name}.py"
    syntax_tree = ast.parse(source_path.read_text(encoding="utf-8"))
    forbidden_imports = [
        node for node in ast.walk(syntax_tree) if _targets_middleware(node)
    ]

    assert not forbidden_imports, (
        f"{adapter_name} imports middleware orchestration: {forbidden_imports}"
    )


def test_adapters_share_the_public_correlation_context() -> None:
    """Adapter primitives should be identical to their public exports."""
    package = importlib.import_module("falcon_correlate")
    httpx_adapter = importlib.import_module("falcon_correlate.httpx")
    celery_adapter = importlib.import_module("falcon_correlate.celery")
    middleware = importlib.import_module("falcon_correlate.middleware")

    assert httpx_adapter.correlation_id_var is package.correlation_id_var, (
        "HTTPX adapter should reuse the package correlation context."
    )
    assert celery_adapter.correlation_id_var is package.correlation_id_var, (
        "Celery adapter should reuse the package correlation context."
    )
    assert httpx_adapter.DEFAULT_HEADER_NAME is middleware.DEFAULT_HEADER_NAME, (
        "HTTPX adapter should retain the public middleware header constant."
    )
