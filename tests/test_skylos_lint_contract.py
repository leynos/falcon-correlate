"""Contract tests for Skylos dead-code detection in Make and CI.

Skylos scans accept ``--config-file`` before a source path, while the standalone
``whitelist`` subcommand must appear immediately after ``skylos``. Skylos also
uses its own Python AST, so its tool runtime is pinned to Python 3.14. Makeutil
parses the Makefile into structured rules and variables, so these tests assert
the interface without relying on whitespace or nearby source text.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess  # noqa: S404 - contracts invoke a fixed local executable.
import tomllib
import typing as typ
from pathlib import Path

import yaml

_MAKEUTIL_COMMAND: typ.Final = ("makeutil", "parse", "Makefile")
_MAKEUTIL_REVISION: typ.Final = "29fc5a1634ffbaa18a773eed9dff1b2838a45d9c"
_MAKEUTIL_TOOLCHAIN: typ.Final = "nightly-2026-05-28"
_MAKEUTIL_INSTALL_TOKENS: typ.Final = (
    "rustup",
    "toolchain",
    "install",
    "${MAKEUTIL_TOOLCHAIN}",
    "--profile",
    "minimal",
    "RUSTFLAGS=-Zpolonius=next",
    "cargo",
    "+${MAKEUTIL_TOOLCHAIN}",
    "install",
    "--git",
    "https://github.com/leynos/makeutil",
    "--rev",
    "${MAKEUTIL_REVISION}",
    "--locked",
    "--force",
    "makeutil",
)
_METHOD_ENTRY_POINTS: typ.Final = frozenset({
    "falcon_correlate.middleware_config.CorrelationIDConfig.__post_init__",
    "falcon_correlate.middleware_config.CorrelationIDConfig._validate_header_name",
    "falcon_correlate.middleware_config.CorrelationIDConfig._validate_trusted_sources",
    "falcon_correlate.middleware_config.CorrelationIDConfig._validate_source_not_empty",
    "falcon_correlate.middleware_config.CorrelationIDConfig._parse_network",
    "falcon_correlate.middleware_config.CorrelationIDConfig._validate_generator",
    "falcon_correlate.middleware_config.CorrelationIDConfig._validate_validator",
    "falcon_correlate.middleware.CorrelationIDMiddleware.process_request",
    "falcon_correlate.middleware.CorrelationIDMiddleware.process_response",
    "falcon_correlate.middleware_asgi.CorrelationIDMiddlewareASGI.process_request",
    "falcon_correlate.middleware_asgi.CorrelationIDMiddlewareASGI.process_response",
})
_PARAMETER_ENTRY_POINTS: typ.Final = frozenset({
    "falcon_correlate.middleware.CorrelationIDMiddleware.process_request.resp",
    "falcon_correlate.middleware.CorrelationIDMiddleware.process_response.resource",
    "falcon_correlate.middleware.CorrelationIDMiddleware.process_response.req_succeeded",
    "falcon_correlate.middleware_asgi.CorrelationIDMiddlewareASGI.process_request.resp",
    "falcon_correlate.middleware_asgi.CorrelationIDMiddlewareASGI.process_response.resource",
    "falcon_correlate.middleware_asgi.CorrelationIDMiddlewareASGI.process_response.req_succeeded",
})
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _makefile_report() -> dict[str, object]:
    """Return Makeutil's complete, successfully parsed Makefile report."""
    completed = subprocess.run(  # noqa: S603 - fixed parser command.
        _MAKEUTIL_COMMAND,
        capture_output=True,
        check=True,
        cwd=_PROJECT_ROOT,
        text=True,
    )
    report = typ.cast("dict[str, object]", json.loads(completed.stdout))
    parse = _mapping(report.get("parse"), subject="parse report")
    assert parse.get("status") == "complete", (
        f"makeutil did not complete the Makefile parse: {parse!r}"
    )
    return report


def _mapping(value: object, *, subject: str) -> dict[str, object]:
    """Return a JSON object, naming the unexpected `subject` on failure."""
    assert isinstance(value, dict), f"expected {subject} to be a JSON object"
    return typ.cast("dict[str, object]", value)


def _objects(value: object, *, subject: str) -> list[dict[str, object]]:
    """Return a JSON object array, naming the unexpected `subject` on failure."""
    assert isinstance(value, list), f"expected {subject} to be a JSON array"
    return [_mapping(item, subject=f"{subject} item") for item in value]


def _text_sequence(value: object, *, subject: str) -> tuple[str, ...]:
    """Return a JSON string array, naming the unexpected `subject` on failure."""
    assert isinstance(value, list), f"expected {subject} to be a JSON array"
    assert all(isinstance(item, str) for item in value), (
        f"expected {subject} to contain only JSON strings"
    )
    return tuple(typ.cast("list[str]", value))


def _sole_variable(name: str) -> dict[str, object]:
    """Return Makeutil's sole variable fact for `name`."""
    variables = _objects(_makefile_report().get("variables"), subject="variables")
    matches = [variable for variable in variables if variable.get("name") == name]
    assert len(matches) == 1, (
        f"expected one Makefile variable named {name!r}, found {len(matches)}"
    )
    return matches[0]


def _sole_recipe_rule(target: str) -> dict[str, object]:
    """Return the only parsed rule for `target` that has recipes."""
    rules = _objects(_makefile_report().get("rules"), subject="rules")
    matches = [
        rule
        for rule in rules
        if target in _text_sequence(rule.get("targets"), subject="rule targets")
        and _objects(rule.get("recipes"), subject="rule recipes")
    ]
    assert len(matches) == 1, (
        f"expected one recipe-bearing Makefile rule named {target!r}, found "
        f"{len(matches)}"
    )
    return matches[0]


def _variable_tokens(name: str) -> tuple[str, ...]:
    """Return shell-like tokens from Makeutil's raw variable value."""
    value = _sole_variable(name).get("raw_value")
    assert isinstance(value, str), f"expected {name!r} to have a string value"
    return tuple(argument for argument in shlex.split(value) if argument != "\n")


def _recipe_tokens(target: str) -> tuple[tuple[str, ...], ...]:
    """Return shell-like tokens for every recipe in `target`."""
    recipes = _objects(
        _sole_recipe_rule(target).get("recipes"), subject=f"{target} recipes"
    )
    return tuple(
        tuple(argument for argument in shlex.split(recipe_text) if argument != "\n")
        for recipe in recipes
        if isinstance(recipe_text := recipe.get("text"), str)
    )


def _workflow_job(workflow_path: str, job_name: str) -> dict[str, object]:
    """Return `job_name` from a repository workflow."""
    workflow = yaml.safe_load((_PROJECT_ROOT / workflow_path).read_text())
    workflow_mapping = _mapping(workflow, subject=f"{workflow_path} workflow")
    jobs = _mapping(workflow_mapping.get("jobs"), subject=f"{workflow_path} jobs")
    return _mapping(jobs.get(job_name), subject=f"{workflow_path} job {job_name!r}")


def _sole_workflow_step(
    job_name: str,
    step_name: str,
    *,
    workflow_path: str = ".github/workflows/ci.yml",
) -> dict[str, object]:
    """Return the sole named workflow step from `job_name`."""
    steps = _objects(
        _workflow_job(workflow_path, job_name).get("steps"),
        subject=f"{workflow_path} job {job_name!r} steps",
    )
    matches = [step for step in steps if step.get("name") == step_name]
    assert len(matches) == 1, (
        f"expected one {step_name!r} step in {workflow_path} job {job_name!r}, "
        f"found {len(matches)}"
    )
    return matches[0]


def _run_skylos_allow(*arguments: str) -> subprocess.CompletedProcess[str]:
    """Run a whitelist boundary without invoking Skylos for valid input."""
    make = shutil.which("make")
    assert make is not None, "the Skylos whitelist contract requires make on PATH"
    environment = {**os.environ, "NAME": "wsl-hostname"}
    environment.pop("REASON", None)
    environment.pop("SYMBOL", None)
    return subprocess.run(  # noqa: S603 - fixed Make target and arguments.
        (make, "skylos-allow", *arguments),
        capture_output=True,
        check=False,
        cwd=_PROJECT_ROOT,
        env=environment,
        text=True,
    )


def _assert_makeutil_installation(command: object, *, contract: str) -> None:
    """Assert that `command` installs the pinned Makeutil parser."""
    assert isinstance(command, str), (
        f"{contract} must provide a Makeutil installation shell command"
    )
    assert (
        tuple(shlex.split(command.replace("\\\n", ""))) == _MAKEUTIL_INSTALL_TOKENS
    ), f"{contract} must pin the Makeutil installation command"


def test_lint_recipe_runs_the_production_dead_code_gate() -> None:
    """`make lint` must scan production code with Skylos's strict gate."""
    assert _variable_tokens("SKYLOS_VERSION") == ("4.33.2",), (
        "Skylos version contract must pin 4.33.2"
    )
    assert _variable_tokens("SKYLOS_PRODUCTION_TARGETS") == ("src/falcon_correlate",), (
        "Skylos production-target contract must scan only production modules"
    )
    assert _variable_tokens("SKYLOS_EXCLUDES") == ("unittests",), (
        "Skylos exclusion contract must omit in-package tests"
    )
    commands = [
        command for command in _recipe_tokens("lint") if command[:1] == ("$(SKYLOS)",)
    ]
    assert commands == [
        (
            "$(SKYLOS)",
            "$(SKYLOS_PRODUCTION_TARGETS)",
            "--exclude",
            "$(SKYLOS_EXCLUDES)",
            "--category",
            "dead_code",
            "--gate",
            "--format",
            "concise",
            "--no-upload",
            "--no-provenance",
            "--no-grep-verify",
        )
    ], "Skylos lint command must be a strict production dead-code gate"


def test_whitelist_target_uses_skylos_subcommand_contract() -> None:
    """`skylos whitelist` must precede its named exception and reason."""
    assert _variable_tokens("SKYLOS_CLI") == (
        "$(UV_ENV)",
        "$(UV)",
        "tool",
        "run",
        "--python",
        "3.14",
        "--from",
        "skylos==$(SKYLOS_VERSION)",
        "skylos",
    ), "Skylos CLI contract must pin Python 3.14 and its tool release"
    assert _variable_tokens("SKYLOS") == (
        "$(SKYLOS_CLI)",
        "--config-file",
        "pyproject.toml",
    ), "Skylos scan command must add only scan-specific global options"
    commands = [
        command
        for command in _recipe_tokens("skylos-allow")
        if command[:1] == ("$(SKYLOS_CLI)",)
    ]
    assert commands == [
        (
            "$(SKYLOS_CLI)",
            "whitelist",
            "$${SKYLOS_SYMBOL}",
            "--reason",
            "$${SKYLOS_REASON}",
        )
    ], "Skylos whitelist command must dispatch before its reason option"


def test_skylos_allow_requires_symbol_and_reason() -> None:
    """The whitelist target must reject incomplete input without running Skylos."""
    for arguments, expected_error in (
        ((), "Error: SYMBOL is required for a named whitelist exception"),
        (
            ("SYMBOL=handler",),
            "Error: REASON is required for a named whitelist exception",
        ),
    ):
        completed = _run_skylos_allow(*arguments)

        assert completed.returncode == 2, (
            "Skylos whitelist boundary must reject missing required arguments"
        )
        assert expected_error in completed.stderr, (
            "Skylos whitelist boundary must name the missing required argument"
        )


def test_skylos_allow_dry_run_preserves_whitelist_command_contract() -> None:
    """A valid dry run must reveal the command without writing an exception."""
    make = shutil.which("make")
    assert make is not None, "the Skylos whitelist contract requires make on PATH"
    completed = subprocess.run(  # noqa: S603 - fixed Make target and arguments.
        (
            make,
            "--dry-run",
            "skylos-allow",
            "SYMBOL=handler",
            "REASON=Loaded by plugin registry",
        ),
        capture_output=True,
        check=False,
        cwd=_PROJECT_ROOT,
        text=True,
    )

    assert completed.returncode == 0, (
        "Skylos whitelist dry run must accept complete input"
    )
    assert (
        'skylos whitelist "${SKYLOS_SYMBOL}" --reason "${SKYLOS_REASON}"'
        in completed.stdout
    ), "Skylos whitelist dry run must preserve subcommand argument order"


def test_skylos_configuration_models_implicit_runtime_callers() -> None:
    """Each known false positive must be a typed, explained entry point."""
    with (_PROJECT_ROOT / "pyproject.toml").open("rb") as configuration_file:
        configuration = tomllib.load(configuration_file)

    tool = _mapping(configuration.get("tool"), subject="tool configuration")
    skylos = _mapping(tool.get("skylos"), subject="Skylos configuration")
    gate = _mapping(skylos.get("gate"), subject="Skylos gate configuration")
    assert gate.get("strict") is True, (
        "Skylos gate configuration must enable strict mode"
    )
    assert "whitelist" not in skylos, (
        "Skylos configuration must prefer typed entry points over broad allow lists"
    )
    dead_code = _mapping(
        skylos.get("dead_code"), subject="Skylos dead-code configuration"
    )
    entry_points = _objects(dead_code.get("entrypoints"), subject="Skylos entry points")
    entries_by_type: dict[str, set[str]] = {}
    for entry_point in entry_points:
        entry_type = entry_point.get("type")
        assert isinstance(entry_type, str), (
            "Skylos entry-point contract must classify every runtime caller"
        )
        reason = entry_point.get("reason")
        assert isinstance(reason, str), (
            "Skylos entry-point contract must provide a textual reason"
        )
        assert reason, "Skylos entry-point contract must provide a non-empty reason"
        entries_by_type.setdefault(entry_type, set()).update(
            _text_sequence(entry_point.get("full_name"), subject="entry-point name")
        )
    assert entries_by_type == {
        "method": _METHOD_ENTRY_POINTS,
        "parameter": _PARAMETER_ENTRY_POINTS,
    }, "Skylos entry-point contract must preserve typed runtime exceptions"


def test_ci_runs_lint_and_installs_makeutil_for_full_suites() -> None:
    """CI must share lint and Makeutil contracts with local contributor gates."""
    lint_step = _sole_workflow_step("lint", "Run lint gates")
    assert lint_step.get("run") == "make lint", (
        "CI lint-step contract must invoke the shared make lint target"
    )
    test_rule = _sole_recipe_rule("test")
    prerequisites = _text_sequence(
        test_rule.get("prerequisites"), subject="test prerequisites"
    )
    assert "makeutil" in prerequisites, (
        "make test must require Makeutil before its Skylos contract tests run"
    )

    for workflow_path, job_name in (
        (".github/workflows/ci.yml", "test"),
        (".github/workflows/coverage-main.yml", "coverage-upload"),
    ):
        job = _workflow_job(workflow_path, job_name)
        environment = _mapping(
            job.get("env"), subject=f"{workflow_path} Makeutil environment"
        )
        assert environment.get("MAKEUTIL_REVISION") == _MAKEUTIL_REVISION, (
            f"{workflow_path} Makeutil revision contract must stay pinned"
        )
        assert environment.get("MAKEUTIL_TOOLCHAIN") == _MAKEUTIL_TOOLCHAIN, (
            f"{workflow_path} Makeutil toolchain contract must stay pinned"
        )
        parser_step = _sole_workflow_step(
            job_name, "Install Makefile parser", workflow_path=workflow_path
        )
        _assert_makeutil_installation(
            parser_step.get("run"),
            contract=f"{workflow_path} Makeutil-install contract",
        )
