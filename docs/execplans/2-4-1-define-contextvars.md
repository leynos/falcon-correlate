# Define context variables (2.4.1)

This Execution Plan (ExecPlan) is a living document. The sections
`Constraints`, `Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`,
`Decision log`, and `Outcomes & retrospective` must be kept up to date as work
proceeds.

Status: COMPLETE

## Purpose / big picture

The middleware currently stores the correlation ID only on Falcon's
`req.context.correlation_id`, which couples consumers to the Falcon request
object. Task 2.4.1 introduces two `contextvars.ContextVar` instances —
`correlation_id_var` and `user_id_var` — at module level, making request-scoped
data available throughout the application without a direct dependency on the
Falcon `req` object. This is the foundation for task 2.4.2 (lifecycle
management: set in `process_request`, reset in `process_response`) and task
2.4.3 (`req.context` integration).

Success is observable when:

- `correlation_id_var` is a `ContextVar[str | None]` with `default=None` and
  name `"correlation_id"`.
- `user_id_var` is a `ContextVar[str | None]` with `default=None` and name
  `"user_id"`.
- Both variables are importable from the package root:
  `from falcon_correlate import correlation_id_var, user_id_var`.
- Both variables appear in `falcon_correlate.__all__`.
- `.get()` returns `None` by default; `.set()` and `.reset()` work correctly.
- All existing tests continue to pass unchanged.
- New unit and behaviour-driven development (BDD) tests cover every new code
  path.
- `docs/users-guide.md` documents the new context variables.
- `docs/roadmap.md` shows task 2.4.1 as complete.
- All quality gates pass (`make check-fmt`, `make typecheck`, `make lint`,
  `make test`).

## Constraints

- This task defines the variables and exports them only. Lifecycle management
  (setting/resetting in `process_request`/`process_response`) is deferred to
  task 2.4.2.
- No new external dependencies.
- Follow test-driven development (TDD): write tests first, then implement.
- Follow the project's British English spelling conventions in documentation.
- Markdown must wrap at 80 columns (code blocks at 120). Use `-` for bullets.
- Python line length limit is 88 characters. Maximum cyclomatic complexity
  is 9.

## Tolerances (exception triggers)

- Scope: more than 10 files or more than 250 lines (net) changed requires
  escalation.
- Interface: any change to existing public function signatures requires
  escalation.
- Dependencies: any new external dependency requires escalation.
- Tests: if tests fail after two fix attempts, stop and escalate.
- Ambiguity: if context variable semantics conflict with the design document,
  stop and present options with trade-offs.

## Risks

- Risk: Test isolation — `ContextVar.set()` persists within a thread and could
  leak between tests. Severity: medium. Likelihood: medium. Mitigation: all
  tests that call `.set()` must run inside `contextvars.copy_context().run()`
  to isolate state.

- Risk: `from __future__ import annotations` interaction with `ContextVar`
  runtime type parameter. Severity: low. Likelihood: low. Mitigation: the type
  annotation `contextvars.ContextVar[str | None]` is deferred by the future
  import and never evaluated at runtime. The `ContextVar(...)` constructor call
  is a runtime expression and is unaffected.

## Progress

- [x] (2026-02-16 00:00Z) Research and scope confirmation.
- [x] (2026-02-16 00:05Z) Write ExecPlan.
- [x] (2026-02-16 00:10Z) Add unit tests (TDD red phase).
- [x] (2026-02-16 00:15Z) Add BDD scenarios and step definitions (TDD red
  phase).
- [x] (2026-02-16 00:20Z) Implement context variable definitions in
  `middleware.py`.
- [x] (2026-02-16 00:20Z) Export context variables in `__init__.py`.
- [x] (2026-02-16 00:25Z) Run tests to confirm they pass (TDD green phase).
- [x] (2026-02-16 00:30Z) Update `docs/users-guide.md`.
- [x] (2026-02-16 00:30Z) Record design decisions in design document.
- [x] (2026-02-16 00:30Z) Mark task 2.4.1 complete in `docs/roadmap.md`.
- [x] (2026-02-16 00:35Z) Run all quality gates.

## Surprises & discoveries

- Observation: The `make typecheck` gate (`ty check`) fails on the baseline
  commit with an `unresolved-import` error for `uuid_utils`. This is the same
  pre-existing issue documented in the 2.3.2 ExecPlan. Impact: none for this
  task; the error is unrelated to the context variable changes.

## Decision log

- Decision: Define both `ContextVar` instances in `middleware.py` at module
  level, after the `logger` constant and before function definitions.
  Rationale: the design document (§3.3.1) specifies "At the module level where
  the middleware is defined." Co-location prepares for task 2.4.2 lifecycle
  management. Date/Author: 2026-02-16.

- Decision: Use `import contextvars` (not `from contextvars import ContextVar`)
  and fully qualified `contextvars.ContextVar[str | None]` annotations.
  Rationale: matches the design document's example code and keeps the
  dependency explicit. Date/Author: 2026-02-16.

- Decision: Create a dedicated `test_context_variables.py` unit test file and
  `context_variables.feature` BDD feature file rather than extending existing
  files. Rationale: follows the project convention of one test file per
  concern, matching `test_uuid7_generator.py`, `test_uuid_validator.py`, and
  `uuidv7.feature`. Date/Author: 2026-02-16.

- Decision: Use `contextvars.copy_context().run()` for test isolation in all
  tests that call `.set()`. Rationale: prevents test pollution from
  `ContextVar` state persisting within a thread between tests. Date/Author:
  2026-02-16.

## Outcomes & retrospective

The context variable definitions are now complete. Two `ContextVar[str | None]`
instances — `correlation_id_var` (name: `"correlation_id"`) and `user_id_var`
(name: `"user_id"`) — are defined at module level in `middleware.py` and
exported via `__init__.py` as part of the public API. Both default to `None`.

New tests: 14 unit tests in `test_context_variables.py` covering three
categories (variable definitions, set/get/reset operations, and public API
exports) plus 4 BDD scenarios in `context_variables.feature`. Total test suite:
207 passed, 11 skipped (continuous integration (CI)-only workflow tests).

All quality gates passed: `make check-fmt`, `make lint`, `make test`,
`make markdownlint`. The `make typecheck` failure is pre-existing and unrelated
(see Surprises & discoveries).

## Context and orientation

The project is `falcon-correlate`, a correlation ID middleware for the Falcon
web framework. The middleware intercepts every request, retrieves or generates
a correlation ID, stores it on `req.context.correlation_id`, and optionally
echoes it in the response.

### Design specification

The design document[^1] specifies:

```python
import contextvars

correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)
user_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "user_id", default=None
)
```

These are defined at module level in `middleware.py` and exported via
`__init__.py`.

[^1]: `docs/falcon-correlation-id-middleware-design.md` — §3.3.1, lines
    338–357.

### Key files

- `src/falcon_correlate/middleware.py` — Module-level definitions target.
- `src/falcon_correlate/__init__.py` — Public exports.
- `src/falcon_correlate/unittests/test_context_variables.py` — Create — Unit
  tests.
- `tests/bdd/context_variables.feature` — Create — BDD feature file.
- `tests/bdd/test_context_variables_steps.py` — Create — BDD step definitions.
- `docs/users-guide.md` — User documentation.
- `docs/roadmap.md` — Task tracking.
- `docs/falcon-correlation-id-middleware-design.md` — Design decisions.

### Existing patterns to reuse

- Unit test structure from `test_uuid7_generator.py` and
  `test_uuid_validator.py`: class-based tests with descriptive docstrings.
- BDD step definitions from `test_uuidv7_steps.py`: `Context` TypedDict,
  `scenarios()` call, `@given`/`@when`/`@then` decorators.
- Public export test pattern from `test_public_exports.py`.

## Plan of work

### Stage A: Add unit tests (TDD red phase)

Create `src/falcon_correlate/unittests/test_context_variables.py` with three
test classes:

**1. `TestContextVariableDefinitions`** — variable existence, type, naming,
defaults:

- `test_correlation_id_var_is_context_var`
- `test_user_id_var_is_context_var`
- `test_correlation_id_var_name`
- `test_user_id_var_name`
- `test_correlation_id_var_default_is_none`
- `test_user_id_var_default_is_none`

**2. `TestContextVariableOperations`** — set/get/reset (isolated via
`contextvars.copy_context().run()`):

- `test_correlation_id_var_set_and_get`
- `test_user_id_var_set_and_get`
- `test_correlation_id_var_reset_restores_default`
- `test_user_id_var_reset_restores_default`

**3. `TestContextVariableExports`** — public API:

- `test_correlation_id_var_in_all`
- `test_user_id_var_in_all`
- `test_correlation_id_var_importable_from_root`
- `test_user_id_var_importable_from_root`

### Stage B: Add BDD scenarios

Create `tests/bdd/context_variables.feature` with four scenarios:

1. Correlation ID context variable exists with None default.
2. User ID context variable exists with None default.
3. Correlation ID context variable can be set and retrieved.
4. User ID context variable can be set and retrieved.

Create `tests/bdd/test_context_variables_steps.py` with step definitions
following the `test_uuidv7_steps.py` pattern.

### Stage C: Implement production code

1. Add `import contextvars` to `middleware.py` (alphabetically before
   `import dataclasses`).
2. Add `correlation_id_var` and `user_id_var` definitions after `logger`.
3. Add both to imports in `__init__.py`.
4. Add both to `__all__` in `__init__.py`.

### Stage D: Update documentation

1. `docs/users-guide.md`: Add "Context Variables" section; update "Current
   Status".
2. `docs/falcon-correlation-id-middleware-design.md`: Add A.2 decision record.
3. `docs/roadmap.md`: Mark 2.4.1 subtasks as `[x]`.

### Stage E: Quality gates

```bash
set -o pipefail
make check-fmt 2>&1 | tee /tmp/falcon-correlate-check-fmt.log
make typecheck 2>&1 | tee /tmp/falcon-correlate-typecheck.log
make lint 2>&1 | tee /tmp/falcon-correlate-lint.log
make test 2>&1 | tee /tmp/falcon-correlate-test.log
make markdownlint 2>&1 | tee /tmp/falcon-correlate-markdownlint.log
```

## Validation and acceptance

Quality criteria:

- Tests: `make test` passes. All new tests in `test_context_variables.py` fail
  before implementation and pass after. All new BDD scenarios in
  `context_variables.feature` fail before and pass after. All existing tests
  pass throughout.
- Lint: `make lint` passes with no warnings.
- Formatting: `make check-fmt` passes.
- Type checking: `make typecheck` passes.
- Markdown: `make markdownlint` passes.

Behavioural acceptance:

- `from falcon_correlate import correlation_id_var, user_id_var` succeeds.
- `correlation_id_var.get()` returns `None`.
- `user_id_var.get()` returns `None`.
- `correlation_id_var.name == "correlation_id"`.
- `user_id_var.name == "user_id"`.

## Idempotence and recovery

All steps are safe to re-run. If a test fails after implementation, adjust the
implementation or tests and re-run `make test`. If formatting fails, run
`make fmt` and rerun `make check-fmt`.

## Artifacts and notes

Keep the log files created via `tee` for evidence of passing checks:

- `/tmp/falcon-correlate-check-fmt.log`
- `/tmp/falcon-correlate-typecheck.log`
- `/tmp/falcon-correlate-lint.log`
- `/tmp/falcon-correlate-test.log`
- `/tmp/falcon-correlate-markdownlint.log`

## Interfaces and dependencies

New public names added to `falcon_correlate.__all__`:

- `correlation_id_var: contextvars.ContextVar[str | None]`
- `user_id_var: contextvars.ContextVar[str | None]`

Dependencies: Standard library `contextvars` module only (no new external
dependencies).

## Files to modify

- `src/falcon_correlate/middleware.py` — Edit — Add `import contextvars`,
  define `correlation_id_var` and `user_id_var`.
- `src/falcon_correlate/__init__.py` — Edit — Add both variables to imports
  and `__all__`.
- `src/falcon_correlate/unittests/test_context_variables.py` — Create — Unit
  tests.
- `tests/bdd/context_variables.feature` — Create — BDD feature file.
- `tests/bdd/test_context_variables_steps.py` — Create — BDD step
  definitions.
- `docs/users-guide.md` — Edit — Document context variables.
- `docs/roadmap.md` — Edit — Mark 2.4.1 complete.
- `docs/falcon-correlation-id-middleware-design.md` — Edit — Add A.2 decision
  record.
- `docs/execplans/2-4-1-define-contextvars.md` — Create — This ExecPlan file.

## Revision note (required when editing an ExecPlan)

2026-02-16: Initial draft created to cover roadmap task 2.4.1 — define context
variables for correlation ID and user ID with unit tests, BDD tests, and
documentation updates.

2026-02-16: Marked the plan complete, recorded execution details, and updated
progress, decisions, surprises, and outcomes to reflect the implemented context
variable definitions and quality gate results.
