"""Structural contracts for project typecheck and isolated pytest commands."""

from __future__ import annotations

import json
import shlex
import subprocess  # noqa: S404 - fixed local parser command.
import typing as typ
from pathlib import Path

import yaml

_MAKEUTIL_COMMAND: typ.Final = ("makeutil", "parse", "Makefile")
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_OPTIONAL_CELERY_TEST_TOKENS: typ.Final = (
    "src/falcon_correlate/unittests/test_optional_celery_dependency.py",
)
_PROJECT_PYTEST_EXCLUDE_TOKENS: typ.Final = ("--ignore=$(OPTIONAL_CELERY_TEST)",)
_TYPECHECK_PREREQUISITES: typ.Final = ("build",)
_TYPECHECK_RECIPE_TOKENS: typ.Final = (
    ("$(UV_ENV)", "$(UV)", "run", "ty", "--version"),
    ("$(UV_ENV)", "$(UV)", "run", "ty", "check"),
)
_PROJECT_TEST_RECIPE_TOKENS: typ.Final = (
    "$(UV_ENV)",
    "$(UV)",
    "run",
    "pytest",
    "-v",
    "-n",
    "auto",
    "$(PROJECT_PYTEST_EXCLUDES)",
)
_OPTIONAL_CELERY_RECIPE_TOKENS: typ.Final = (
    ("$(UV_ENV)", "$(UV)", "run", "pytest", "-v", "$(OPTIONAL_CELERY_TEST)"),
)
_CI_PARALLEL_TEST_COMMAND: typ.Final = (
    "uv run pytest -v -n auto --ignore=tests/workflows "
    "--ignore=src/falcon_correlate/unittests/test_optional_celery_dependency.py"
)
_CI_SERIAL_OPTIONAL_CELERY_COMMAND: typ.Final = "make test-optional-celery"


def _makefile_report() -> dict[str, object]:
    """Return a fresh successful Makeutil parse of the repository Makefile."""
    completed = subprocess.run(  # noqa: S603 - fixed parser command.
        _MAKEUTIL_COMMAND,
        capture_output=True,
        check=True,
        cwd=_PROJECT_ROOT,
        text=True,
    )
    report = typ.cast("dict[str, object]", json.loads(completed.stdout))
    parse = report.get("parse")
    assert isinstance(parse, dict), "Makeutil must return a parse status object"
    assert parse.get("status") == "complete", (
        f"Makeutil must complete the Makefile parse: {parse!r}"
    )
    return report


def _objects(value: object, *, subject: str) -> list[dict[str, object]]:
    """Return an array of JSON objects, naming the malformed `subject`."""
    assert isinstance(value, list), f"{subject} must be a JSON array"
    assert all(isinstance(item, dict) for item in value), (
        f"{subject} must contain only JSON objects"
    )
    return typ.cast("list[dict[str, object]]", value)


def _recipe_tokens(target: str) -> tuple[tuple[str, ...], ...]:
    """Return parsed recipe tokens for the sole recipe-bearing `target`."""
    rules = _objects(_makefile_report().get("rules"), subject="Makefile rules")
    matches = []
    for rule in rules:
        targets = rule.get("targets")
        recipes = rule.get("recipes")
        assert isinstance(targets, list), "Makeutil rule targets must be an array"
        assert isinstance(recipes, list), "Makeutil rule recipes must be an array"
        if target in targets and recipes:
            matches.append(rule)
    assert len(matches) == 1, (
        f"expected one recipe-bearing Makefile rule named {target!r}, "
        f"found {len(matches)}"
    )
    recipes = _objects(matches[0].get("recipes"), subject=f"{target} recipes")
    commands = []
    for recipe in recipes:
        text = recipe.get("text")
        assert isinstance(text, str), f"{target} recipes must expose command text"
        commands.append(
            tuple(argument for argument in shlex.split(text) if argument != "\n")
        )
    return tuple(commands)


def _variable_tokens(name: str) -> tuple[str, ...]:
    """Return shell-like tokens from a Makeutil variable's raw value."""
    variables = _objects(
        _makefile_report().get("variables"), subject="Makefile variables"
    )
    matches = [variable for variable in variables if variable.get("name") == name]
    assert len(matches) == 1, (
        f"expected one Makefile variable named {name!r}, found {len(matches)}"
    )
    raw_value = matches[0].get("raw_value")
    assert isinstance(raw_value, str), f"Makefile variable {name!r} must be textual"
    return tuple(argument for argument in shlex.split(raw_value) if argument != "\n")


def _rule_prerequisites(target: str) -> tuple[str, ...]:
    """Return prerequisites for the sole recipe-bearing `target`."""
    rules = _objects(_makefile_report().get("rules"), subject="Makefile rules")
    matches = []
    for rule in rules:
        targets = rule.get("targets")
        recipes = rule.get("recipes")
        assert isinstance(targets, list), "Makeutil rule targets must be an array"
        assert isinstance(recipes, list), "Makeutil rule recipes must be an array"
        if target in targets and recipes:
            matches.append(rule)
    assert len(matches) == 1, (
        f"expected one recipe-bearing Makefile rule named {target!r}, "
        f"found {len(matches)}"
    )
    prerequisites = matches[0].get("prerequisites")
    assert isinstance(prerequisites, list), (
        f"Makefile rule {target!r} prerequisites must be an array"
    )
    assert all(isinstance(item, str) for item in prerequisites), (
        f"Makefile rule {target!r} prerequisites must be text"
    )
    return typ.cast("tuple[str, ...]", tuple(prerequisites))


def _workflow_step(job_name: str, step_name: str) -> dict[str, object]:
    """Return the sole named step from the CI workflow job."""
    workflow = yaml.safe_load((_PROJECT_ROOT / ".github/workflows/ci.yml").read_text())
    assert isinstance(workflow, dict), "CI workflow document must be a mapping"
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict), "CI workflow jobs must be a mapping"
    job = jobs.get(job_name)
    assert isinstance(job, dict), f"CI workflow must define the {job_name!r} job"
    steps = _objects(job.get("steps"), subject=f"CI {job_name} steps")
    matches = [step for step in steps if step.get("name") == step_name]
    assert len(matches) == 1, (
        f"expected one CI {step_name!r} step in {job_name!r}, found {len(matches)}"
    )
    return matches[0]


def test_typecheck_and_pytest_targets_use_project_commands() -> None:
    """Typecheck and pytest targets must use uv and isolate Celery tests."""
    assert _rule_prerequisites("typecheck") == _TYPECHECK_PREREQUISITES, (
        "typecheck must not require a globally installed ty executable"
    )
    assert _recipe_tokens("typecheck") == _TYPECHECK_RECIPE_TOKENS, (
        "typecheck must run both ty commands through the project uv environment"
    )
    assert _variable_tokens("OPTIONAL_CELERY_TEST") == _OPTIONAL_CELERY_TEST_TOKENS, (
        "optional-Celery exclusion must name the isolated unit-test module"
    )
    assert (
        _variable_tokens("PROJECT_PYTEST_EXCLUDES") == _PROJECT_PYTEST_EXCLUDE_TOKENS
    ), "project pytest exclusions must omit the optional-Celery module"
    assert _recipe_tokens("test") == (_PROJECT_TEST_RECIPE_TOKENS,), (
        "make test must consume the project pytest exclusion variable"
    )
    assert _recipe_tokens("test-optional-celery") == _OPTIONAL_CELERY_RECIPE_TOKENS, (
        "optional-Celery target must run its module serially without xdist"
    )


def test_ci_runs_the_optional_celery_test_serially() -> None:
    """CI must exclude Celery subprocess work from xdist and run it serially."""
    parallel_test_step = _workflow_step("test", "Run tests")
    assert parallel_test_step.get("run") == _CI_PARALLEL_TEST_COMMAND, (
        "CI xdist test command must exclude the isolated optional-Celery module"
    )
    serial_test_step = _workflow_step("test", "Run optional-Celery tests serially")
    assert serial_test_step.get("run") == _CI_SERIAL_OPTIONAL_CELERY_COMMAND, (
        "CI must run optional-Celery tests through the serial Make target"
    )
    assert serial_test_step.get("if") is None, (
        "CI serial optional-Celery target must run on every test matrix leg"
    )
