"""Verify the opt-in workflow integration marker and availability fixtures."""

from __future__ import annotations

import typing as typ

import pytest

from tests.workflows import conftest, test_ci_workflow

if typ.TYPE_CHECKING:
    import collections.abc as cabc


def test_runtime_tests_are_marked_and_have_time_to_run() -> None:
    """Runtime jobs must be selectable and have a longer timeout."""
    marks = {mark.name: mark for mark in test_ci_workflow.pytestmark}
    assert "integration" in marks, "Workflow runtime tests must carry integration"
    assert marks["timeout"].args == (600,), "Workflow jobs need a 600-second timeout"
    assert set(marks["usefixtures"].args) == {"act_available", "docker_available"}, (
        "Workflow runtime tests must request both availability fixtures"
    )


@pytest.mark.parametrize(
    "probe_case",
    [
        (conftest.act_available, "act", ["--version"], "act is not installed"),
        (conftest.docker_available, "docker", ["info"], "Docker is not available"),
    ],
    ids=["act", "docker"],
)
@pytest.mark.parametrize("available", [True, False], ids=["available", "missing"])
def test_availability_fixture(
    monkeypatch: pytest.MonkeyPatch,
    probe_case: tuple[object, str, list[str], str],
    *,
    available: bool,
) -> None:
    """Each fixture probes its own tool and skips with an actionable reason."""
    fixture, tool, args, message = probe_case
    calls: list[tuple[str, list[str]]] = []

    def probe(name: str, options: list[str]) -> bool:
        calls.append((name, options))
        return available

    monkeypatch.setattr(conftest, "_check_tool_available", probe)
    assert hasattr(fixture, "__wrapped__"), "Availability fixture must expose its body"
    fixture_body = fixture.__wrapped__
    assert callable(fixture_body), "Availability fixture body must be callable"
    fixture_body = typ.cast("cabc.Callable[[], bool]", fixture_body)
    if available:
        assert fixture_body() is True, f"Available {tool} must pass its fixture"
    else:
        with pytest.raises(pytest.skip.Exception, match=message):
            fixture_body()
    assert calls == [(tool, args)], f"{tool} fixture must run its designated probe"
