"""Tests for the ``show_path_sim`` interpreter-diagnostics script."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

import show_path_sim


@pytest.mark.parametrize("sitecustomize_present", [True, False])
def test_main_prints_interpreter_diagnostics(
    *,
    sitecustomize_present: bool,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """main() prints the sitecustomize flag, the cwd and the truncated path."""
    fake_path = ["/first", "/second", "/third"]
    monkeypatch.setattr(show_path_sim.sys, "path", fake_path)
    monkeypatch.setattr(show_path_sim.Path, "cwd", lambda: Path("/fake/cwd"))
    if sitecustomize_present:
        monkeypatch.setitem(
            sys.modules,
            "sitecustomize",
            types.ModuleType("sitecustomize"),
        )
    else:
        monkeypatch.delitem(sys.modules, "sitecustomize", raising=False)

    result = show_path_sim.main()

    assert result is None, "main() should return None"
    assert capsys.readouterr().out == (
        f"sitecustomize_loaded {sitecustomize_present}\n"
        "cwd /fake/cwd\n"
        f"sys.path[:8] {fake_path}\n"
    ), "main() printed unexpected interpreter diagnostics"
