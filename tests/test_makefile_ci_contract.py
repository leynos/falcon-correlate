"""Structural contracts for project typecheck and isolated pytest commands."""

from __future__ import annotations

import json
import shlex
import subprocess  # ruff: ignore[suspicious-subprocess-import] - fixed local parser command.
import typing as typ
from pathlib import Path

import pytest
import yaml

_MAKEUTIL_COMMAND: typ.Final = ("makeutil", "parse", "Makefile")
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CI_WORKFLOW_PATH = _PROJECT_ROOT / ".github/workflows/ci.yml"
_COVERAGE_MAIN_WORKFLOW_PATH = _PROJECT_ROOT / ".github/workflows/coverage-main.yml"
_OPTIONAL_CELERY_TEST_TOKENS: typ.Final = (
    "src/falcon_correlate/unittests/test_optional_celery_dependency.py",
)
_OBSERVABILITY_SNAPSHOT_TEST_TOKENS: typ.Final = (
    "src/falcon_correlate/unittests/test_observability_contracts.py",
)
_PROJECT_PYTEST_EXCLUDE_TOKENS: typ.Final = (
    "--ignore=$(OPTIONAL_CELERY_TEST)",
    "--ignore=$(OBSERVABILITY_SNAPSHOT_TEST)",
)
_TYPECHECK_PREREQUISITES: typ.Final = ("build",)
_TYPECHECK_RECIPE_TOKENS: typ.Final = (
    ("$(TY)", "--version"),
    ("$(TY)", "check"),
)
_LINT_RECIPE_TOKENS: typ.Final = (
    ("$(RUFF)", "check"),
    (
        "$(UV_ENV)",
        "$(UV)",
        "run",
        "interrogate",
        "--fail-under",
        "100",
        "$(INTERROGATE_TARGETS)",
    ),
    ("$(MAKE)", "--no-print-directory", "classic-pylint"),
    ("$(MAKE)", "--no-print-directory", "df12-pylint"),
    ("$(AMBRLEAKS)", "tests"),
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
    ),
)
_CLASSIC_PYLINT_PREREQUISITES: typ.Final = ("verify-classic-pylint",)
_DF12_PYLINT_PREREQUISITES: typ.Final = ("verify-df12-pylint",)
_PYLINT_TARGET_RECIPE_TOKENS: typ.Final = (("$(PYLINT)", "$(PYLINT_TARGETS)"),)
_DF12_PYLINT_RECIPE_TOKENS: typ.Final = (("$(DF12_PYLINT)", "$(PYLINT_TARGETS)"),)
_TY_WRAPPER_TOKENS: typ.Final = (
    "$(UV_ENV)",
    "$(UV)",
    "run",
    "--with",
    "ty==$(TY_VERSION)",
    "ty",
)
_PROJECT_TEST_RECIPE_TOKENS: typ.Final = (
    ("$(UV_ENV)", "$(UV)", "run", "pytest", "-v", "$(SERIAL_PY_TESTS)"),
    (
        "$(UV_ENV)",
        "$(UV)",
        "run",
        "pytest",
        "-v",
        "-n",
        "$(PYTEST_WORKERS)",
        "--dist=loadgroup",
        "$(SERIAL_PY_TEST_EXCLUDES)",
    ),
)
_SERIAL_PY_TESTS_TOKENS: typ.Final = (
    "$(OPTIONAL_CELERY_TEST)",
    "$(OBSERVABILITY_SNAPSHOT_TEST)",
)
_SERIAL_PY_TEST_EXCLUDES_TOKENS: typ.Final = ("$(PROJECT_PYTEST_EXCLUDES)",)
_PYTEST_WORKERS_TOKENS: typ.Final = ("6",)
_OPTIONAL_CELERY_RECIPE_TOKENS: typ.Final = (
    ("$(UV_ENV)", "$(UV)", "run", "pytest", "-v", "$(OPTIONAL_CELERY_TEST)"),
)
_OBSERVABILITY_RECIPE_TOKENS: typ.Final = (
    (
        "$(UV_ENV)",
        "$(UV)",
        "run",
        "pytest",
        "-v",
        "$(OBSERVABILITY_SNAPSHOT_TEST)",
    ),
)
_CI_PARALLEL_TEST_COMMAND: typ.Final = (
    "uv run pytest -v -n auto --dist=loadgroup --ignore=tests/workflows "
    "--ignore=src/falcon_correlate/unittests/test_optional_celery_dependency.py "
    "--ignore=src/falcon_correlate/unittests/test_observability_contracts.py"
)
_CI_SERIAL_OPTIONAL_CELERY_COMMAND: typ.Final = "make test-optional-celery"
_CI_SERIAL_OBSERVABILITY_COMMAND: typ.Final = "make test-observability-contracts"


def _makefile_report() -> dict[str, object]:
    """Return a fresh successful Makeutil parse of the repository Makefile."""
    completed = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - fixed parser command.
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


def _workflow_step(
    workflow_path: Path,
    job_name: str,
    step_name: str,
) -> dict[str, object]:
    """Return the sole named step from a workflow job."""
    workflow = yaml.safe_load(workflow_path.read_text())
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
    assert _variable_tokens("TY") == _TY_WRAPPER_TOKENS, (
        "typecheck must use the pinned project uv wrapper for ty"
    )
    assert _variable_tokens("OPTIONAL_CELERY_TEST") == _OPTIONAL_CELERY_TEST_TOKENS, (
        "optional-Celery exclusion must name the isolated unit-test module"
    )
    assert (
        _variable_tokens("OBSERVABILITY_SNAPSHOT_TEST")
        == _OBSERVABILITY_SNAPSHOT_TEST_TOKENS
    ), "snapshot test exclusion must name the observability contract module"
    assert (
        _variable_tokens("PROJECT_PYTEST_EXCLUDES") == _PROJECT_PYTEST_EXCLUDE_TOKENS
    ), "project pytest exclusions must omit the optional-Celery module"
    assert _variable_tokens("PYTEST_WORKERS") == _PYTEST_WORKERS_TOKENS, (
        "make test must cap xdist workers at the documented local core count"
    )
    assert _variable_tokens("SERIAL_PY_TESTS") == _SERIAL_PY_TESTS_TOKENS, (
        "make test must run the optional-Celery subprocess module serially"
    )
    assert (
        _variable_tokens("SERIAL_PY_TEST_EXCLUDES") == _SERIAL_PY_TEST_EXCLUDES_TOKENS
    ), "parallel pytest must reuse the project optional-Celery exclusion"
    assert _recipe_tokens("test") == _PROJECT_TEST_RECIPE_TOKENS, (
        "make test must run nested tests serially before bounded xdist"
    )
    assert _recipe_tokens("test-optional-celery") == _OPTIONAL_CELERY_RECIPE_TOKENS, (
        "optional-Celery target must run its module serially without xdist"
    )
    assert (
        _recipe_tokens("test-observability-contracts") == _OBSERVABILITY_RECIPE_TOKENS
    ), "observability snapshots must run serially outside the xdist session"


def test_lint_target_runs_all_six_stages_in_order() -> None:
    """`make lint` must keep every blocking lint stage in its intended order."""
    assert _recipe_tokens("lint") == _LINT_RECIPE_TOKENS, (
        "make lint must run Ruff, Interrogate, both Pylint passes, Ambrleaks, "
        "and Skylos in order"
    )


def test_pylint_targets_share_the_project_target_list() -> None:
    """Both isolated Pylint targets must lint the same project paths."""
    assert _rule_prerequisites("classic-pylint") == _CLASSIC_PYLINT_PREREQUISITES, (
        "classic Pylint must verify its pinned interpreter before analysis"
    )
    assert _recipe_tokens("classic-pylint") == _PYLINT_TARGET_RECIPE_TOKENS, (
        "classic Pylint must analyze the shared PYLINT_TARGETS"
    )
    assert _rule_prerequisites("df12-pylint") == _DF12_PYLINT_PREREQUISITES, (
        "DF12 Pylint must verify its pinned interpreter before analysis"
    )
    assert _recipe_tokens("df12-pylint") == _DF12_PYLINT_RECIPE_TOKENS, (
        "DF12 Pylint must analyze the shared PYLINT_TARGETS"
    )


def test_ci_runs_the_optional_celery_test_serially() -> None:
    """CI must exclude Celery subprocess work from xdist and run it serially."""
    parallel_test_step = _workflow_step(_CI_WORKFLOW_PATH, "test", "Run tests")
    assert parallel_test_step.get("run") == _CI_PARALLEL_TEST_COMMAND, (
        "CI xdist test command must exclude the isolated optional-Celery module"
    )
    serial_test_step = _workflow_step(
        _CI_WORKFLOW_PATH,
        "test",
        "Run optional-Celery tests serially",
    )
    assert serial_test_step.get("run") == _CI_SERIAL_OPTIONAL_CELERY_COMMAND, (
        "CI must run optional-Celery tests through the serial Make target"
    )
    assert serial_test_step.get("if") is None, (
        "CI serial optional-Celery target must run on every test matrix leg"
    )
    serial_snapshot_step = _workflow_step(
        _CI_WORKFLOW_PATH,
        "test",
        "Run observability snapshot tests serially",
    )
    assert serial_snapshot_step.get("run") == _CI_SERIAL_OBSERVABILITY_COMMAND, (
        "CI must run observability snapshots through the serial Make target"
    )
    assert serial_snapshot_step.get("if") is None, (
        "CI serial snapshot target must run on every test matrix leg"
    )


@pytest.mark.parametrize(
    ("workflow_path", "job_name"),
    [
        (_CI_WORKFLOW_PATH, "test"),
        (_COVERAGE_MAIN_WORKFLOW_PATH, "coverage-upload"),
    ],
    ids=["pull-request", "main"],
)
def test_coverage_lanes_run_the_pytest_suite_serially(
    workflow_path: Path,
    job_name: str,
) -> None:
    """Coverage jobs must avoid xdist races in grouped toolchain fixtures."""
    coverage_step = _workflow_step(workflow_path, job_name, "Generate coverage")
    coverage_inputs = coverage_step.get("with")
    assert isinstance(coverage_inputs, dict), (
        f"{workflow_path.name} coverage inputs must be a mapping"
    )
    pytest_workers = coverage_inputs.get("pytest-workers")
    assert isinstance(pytest_workers, str), (
        f"{workflow_path.name} coverage pytest-workers input must be a string"
    )
    assert not pytest_workers, (
        f"{workflow_path.name} coverage must disable xdist because the shared "
        "action does not expose `--dist=loadgroup`"
    )
