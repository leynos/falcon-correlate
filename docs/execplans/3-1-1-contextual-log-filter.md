# Implement ContextualLogFilter (3.1.1)

This Execution Plan (ExecPlan) is a living document. The sections
`Constraints`, `Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`,
`Decision log`, and `Outcomes & retrospective` must be kept up to date as work
proceeds.

Status: COMPLETE

## Purpose / big picture

The middleware stores correlation IDs and user IDs in `contextvars` context
variables (`correlation_id_var` and `user_id_var`), but there is currently no
way to automatically inject these values into Python log records. Task 3.1.1
creates a `ContextualLogFilter(logging.Filter)` class that enriches every
`LogRecord` with `correlation_id` and `user_id` attributes, enabling standard
`logging.Formatter` format strings to include these values without any manual
per-call effort.

Success is observable when:

- `ContextualLogFilter` is a `logging.Filter` subclass defined in
  `src/falcon_correlate/middleware.py`.
- When attached to a logger or handler, every `LogRecord` gains
  `record.correlation_id` and `record.user_id` attributes.
- When context variables are set, the filter copies their values to the record.
- When context variables are not set (i.e. `None`), the filter substitutes the
  placeholder string `"-"`.
- The filter always returns `True` (it enriches records, never suppresses them).
- `ContextualLogFilter` is importable from the package root:
  `from falcon_correlate import ContextualLogFilter`.
- `ContextualLogFilter` appears in `falcon_correlate.__all__`.
- All existing tests continue to pass unchanged.
- New unit tests (pytest) and behavioural tests (pytest-bdd) cover every code
  path.
- `docs/users-guide.md` documents the logging filter and its usage.
- `docs/roadmap.md` shows task 3.1.1 as complete.
- All quality gates pass (`make check-fmt`, `make typecheck`, `make lint`,
  `make test`).

## Constraints

- Follow test-driven development (TDD): write tests first, then implement.
- Do not change existing public function signatures or existing tests.
- Do not add external dependencies. The filter uses only `logging` and
  `contextvars` from the standard library.
- Define the class in `src/falcon_correlate/middleware.py` (co-located with the
  context variables it reads), following the project convention of grouping by
  feature.
- Follow the project's British English spelling conventions in documentation.
- Markdown must wrap at 80 columns (paragraphs and bullets); code blocks at
  120 columns. Use `-` for list bullets.
- Python line length limit is 88 characters.

## Tolerances (exception triggers)

- Scope: if implementation requires more than 10 files or 250 net lines
  changed, stop and escalate.
- Interface: if any existing public API signature must change, stop and
  escalate.
- Dependencies: if a new external dependency is required, stop and escalate.
- Iterations: if tests still fail after two fix attempts for the same root
  cause, stop and escalate with findings.
- Ambiguity: if placeholder semantics conflict with the design document, stop
  and present options with trade-offs.

## Risks

- Risk: `LogRecord` attribute injection may conflict with attributes added by
  other filters or handlers. Severity: low. Likelihood: low. Mitigation: the
  attribute names `correlation_id` and `user_id` are specific to this library
  and do not collide with standard `LogRecord` attributes. Document that users
  should avoid naming conflicts in their own filters.

- Risk: test isolation — context variables set in tests may leak between tests.
  Severity: medium. Likelihood: medium. Mitigation: all tests that call
  `.set()` on context variables must run inside
  `contextvars.copy_context().run()` to isolate state. The existing
  `isolated_context` fixture provides this.

- Risk: the `ty` type checker may flag dynamic attribute assignment on
  `LogRecord` (`record.correlation_id = ...`). Severity: low. Likelihood:
  medium. Mitigation: `LogRecord` attributes are dynamically assigned by design
  in the `logging` module; if `ty` flags this, a targeted suppression comment
  will be added.

## Progress

- [x] (2026-02-23 00:00Z) Write ExecPlan.
- [x] (2026-02-23 00:05Z) Add unit tests (TDD red phase).
- [x] (2026-02-23 00:10Z) Add BDD feature file and step definitions (TDD red
  phase).
- [x] (2026-02-23 00:15Z) Implement `ContextualLogFilter` in `middleware.py`.
- [x] (2026-02-23 00:15Z) Export `ContextualLogFilter` in `__init__.py` and
  `__all__`.
- [x] (2026-02-23 00:20Z) Run tests to confirm they pass (TDD green phase).
- [x] (2026-02-23 00:25Z) Update `docs/users-guide.md` with logging filter
  documentation.
- [x] (2026-02-23 00:25Z) Record design decisions in design document.
- [x] (2026-02-23 00:30Z) Mark task 3.1.1 complete in `docs/roadmap.md`.
- [x] (2026-02-23 00:35Z) Run all quality gates (`make check-fmt`,
  `make typecheck`, `make lint`, `make test`, `make markdownlint`).

## Surprises & discoveries

- Observation: BDD step definitions that set context variables directly (without
  `contextvars.copy_context().run()`) leak state into other tests running in
  the same pytest-xdist worker. This caused the pre-existing
  `test_context_variable_is_cleared_after_response` test to fail when it
  observed a correlation ID value set by the new BDD scenarios. Evidence: the
  assertion error showed `'req-789'` instead of `None`. Impact: added an
  `autouse` fixture `_reset_context_variables` in the BDD step file that resets
  both context variables to `None` after each scenario. This is a complement to
  the `isolated_context` pattern used in unit tests — BDD tests need a
  different approach because the step functions cannot easily be wrapped in
  `copy_context().run()`.

- Observation: the `ty` type checker (v0.0.18) does not flag dynamic attribute
  assignment on `logging.LogRecord` objects, so `# type: ignore[attr-defined]`
  comments were unnecessary and were flagged as unused. Impact: removed the
  suppression comments from the production code. Test files retain the comments
  as they are checked by `mypy`/`pyright`-style checkers.

## Decision log

- Decision: Use the string `"-"` as the placeholder when context variables are
  not set, rather than forwarding `None`. Rationale: the roadmap specifies
  "e.g., `-`" and a string placeholder is safer for format strings — using
  `None` would render as the string `"None"` in `%(correlation_id)s` format
  expressions, which is misleading. A dash is a conventional log placeholder
  that clearly signals "not available". Date/Author: 2026-02-23.

- Decision: Define `ContextualLogFilter` in `middleware.py` alongside the
  context variables it reads. Rationale: follows the project's "group by
  feature, not layer" convention. The filter's sole purpose is reading
  `correlation_id_var` and `user_id_var`, which are defined in the same module.
  Date/Author: 2026-02-23.

- Decision: The `filter` method always returns `True`. Rationale: the design
  document (§3.4.1) specifies this — the filter enriches records with
  contextual attributes but never suppresses them. Date/Author: 2026-02-23.

- Decision: Expose the placeholder as a module-level constant
  `_MISSING_CONTEXT_PLACEHOLDER = "-"`. Rationale: avoids magic strings in the
  filter method and makes the value easy to find and change if needed. The
  underscore prefix indicates it is an internal implementation detail, not a
  public API. Date/Author: 2026-02-23.

## Outcomes & retrospective

The `ContextualLogFilter` implementation is complete. A `logging.Filter`
subclass is defined in `middleware.py` alongside the context variables it
reads, and is exported via `__init__.py` as part of the public API. The filter
injects `correlation_id` and `user_id` attributes into every `LogRecord`, using
`"-"` as a placeholder when context variables are not set.

New tests: 14 unit tests in `test_contextual_log_filter.py` covering six
categories (class identity, attribute injection, placeholder behaviour, return
value, logging integration, and public API exports) plus 4 BDD scenarios in
`contextual_log_filter.feature`. Total test suite: 246 passed, 11 skipped
(CI-only workflow tests).

All quality gates passed: `make check-fmt`, `make lint`, `make typecheck`,
`make test`, `make markdownlint`.

Key lesson: BDD step definitions that set context variables must include
cleanup (via an `autouse` fixture) to prevent cross-test contamination in
parallel test execution. This differs from unit tests which use
`contextvars.copy_context().run()` for isolation.

## Context and orientation

The project is `falcon-correlate`, a correlation ID middleware for the Falcon
web framework. The package source lives under `src/falcon_correlate/`. The
middleware class (`CorrelationIDMiddleware`) and the two context variables
(`correlation_id_var`, `user_id_var`) are defined in
`src/falcon_correlate/middleware.py`. The public API is exported from
`src/falcon_correlate/__init__.py` via an `__all__` list.

Unit tests are co-located in `src/falcon_correlate/unittests/` and follow a
class-based pattern with descriptive docstrings (one test file per concern).
Shared unit-test fixtures (`request_response_factory`, `isolated_context`) live
in `src/falcon_correlate/unittests/conftest.py`. Behavioural tests live in
`tests/bdd/` as Gherkin `.feature` files with accompanying `test_*_steps.py`
step definition files using `pytest-bdd`. Step definition files use a `Context`
TypedDict for passing state between steps.

The design specification[^1] describes the `ContextualLogFilter` in §3.4.1
(requirements) and §4.2 (reference implementation).

[^1]: `docs/falcon-correlation-id-middleware-design.md`

### Key files

- `src/falcon_correlate/middleware.py` — Edit — Add `ContextualLogFilter`
  class and `_MISSING_CONTEXT_PLACEHOLDER` constant.
- `src/falcon_correlate/__init__.py` — Edit — Add `ContextualLogFilter` to
  imports and `__all__`.
- `src/falcon_correlate/unittests/test_contextual_log_filter.py` — Create —
  Unit tests.
- `tests/bdd/contextual_log_filter.feature` — Create — BDD feature file.
- `tests/bdd/test_contextual_log_filter_steps.py` — Create — BDD step
  definitions.
- `docs/users-guide.md` — Edit — Add logging filter section; update current
  status.
- `docs/roadmap.md` — Edit — Mark 3.1.1 subtasks as `[x]`.
- `docs/falcon-correlation-id-middleware-design.md` — Edit — Record
  implementation decisions.

### Existing patterns to reuse

- Unit test structure: class-based tests with descriptive docstrings, as in
  `test_context_variables.py` and `test_uuid_validator.py`.
- `isolated_context` fixture from
  `src/falcon_correlate/unittests/conftest.py` for context variable isolation.
- BDD step definitions: `Context` TypedDict,
  `scenarios("feature_name.feature")`, `@given`/`@when`/`@then` decorators, as
  in `test_context_variables_steps.py`.
- Public export test pattern from `test_public_exports.py` and
  `test_context_variables.py`.

## Plan of work

### Stage A: Add unit tests (TDD red phase)

Create `src/falcon_correlate/unittests/test_contextual_log_filter.py` with the
following test classes and methods:

**1. `TestContextualLogFilterIsLoggingFilter`** — class identity:

- `test_is_logging_filter_subclass` — Verify `ContextualLogFilter` is a
  subclass of `logging.Filter`.
- `test_can_be_instantiated` — Verify the filter can be instantiated with no
  arguments.

**2. `TestContextualLogFilterAttributeInjection`** — attribute enrichment:

- `test_injects_correlation_id_from_context` — Set `correlation_id_var` in an
  isolated context, create a `LogRecord`, call `filter()`, assert
  `record.correlation_id` matches the set value.
- `test_injects_user_id_from_context` — Set `user_id_var` in an isolated
  context, create a `LogRecord`, call `filter()`, assert `record.user_id`
  matches the set value.
- `test_injects_both_attributes_simultaneously` — Set both context variables,
  call `filter()`, assert both attributes present and correct.

**3. `TestContextualLogFilterPlaceholder`** — placeholder when context empty:

- `test_placeholder_for_correlation_id_when_not_set` — Without setting
  `correlation_id_var`, call `filter()`, assert `record.correlation_id == "-"`.
- `test_placeholder_for_user_id_when_not_set` — Without setting `user_id_var`,
  call `filter()`, assert `record.user_id == "-"`.
- `test_placeholder_for_both_when_not_set` — Without setting either variable,
  assert both attributes are `"-"`.

**4. `TestContextualLogFilterReturnValue`** — filter method return:

- `test_filter_returns_true` — Call `filter()` and assert the return value is
  `True`.
- `test_filter_returns_true_when_context_set` — Set context variables, call
  `filter()`, assert `True`.

**5. `TestContextualLogFilterLoggingIntegration`** — standard logging
integration:

- `test_filter_works_with_logger` — Create a `logging.Logger`, add a
  `logging.Handler` with `ContextualLogFilter`, emit a log record in an
  isolated context with context variables set, capture the formatted output via
  a format string containing `%(correlation_id)s` and `%(user_id)s`, assert the
  output contains the expected values.
- `test_filter_works_with_dict_config` — Configure logging via
  `logging.config.dictConfig` using `ContextualLogFilter` as a filter class,
  emit a record, capture output, assert contextual attributes appear.

**6. `TestContextualLogFilterExports`** — public API:

- `test_contextual_log_filter_in_all` — Assert `"ContextualLogFilter"` is in
  `falcon_correlate.__all__`.
- `test_contextual_log_filter_importable_from_root` — Assert
  `from falcon_correlate import ContextualLogFilter` succeeds and the imported
  class is a `logging.Filter` subclass.

All tests that interact with context variables must use the `isolated_context`
fixture or `contextvars.copy_context().run()` to prevent leakage.

### Stage B: Add BDD scenarios (TDD red phase)

Create `tests/bdd/contextual_log_filter.feature`:

    Feature: Contextual log filter
      As a developer using falcon-correlate
      I want a logging filter that injects correlation ID and user ID
        into log records
      So that my application logs include request context automatically

      Scenario: Filter injects correlation ID into log record
        Given a contextual log filter
        And the correlation ID is set to "abc-123"
        When the filter processes a log record
        Then the log record should have correlation_id "abc-123"

      Scenario: Filter injects user ID into log record
        Given a contextual log filter
        And the user ID is set to "user-456"
        When the filter processes a log record
        Then the log record should have user_id "user-456"

      Scenario: Filter uses placeholder when context is empty
        Given a contextual log filter
        And no context variables are set
        When the filter processes a log record
        Then the log record should have correlation_id "-"
        And the log record should have user_id "-"

      Scenario: Filter integrates with standard logging
        Given a logger configured with the contextual log filter
        And the correlation ID is set to "req-789"
        And the user ID is set to "admin"
        When a log message "test entry" is emitted
        Then the formatted output should contain "req-789"
        And the formatted output should contain "admin"

Create `tests/bdd/test_contextual_log_filter_steps.py` with step definitions
following the `test_context_variables_steps.py` pattern: `Context` TypedDict,
`scenarios()` call, `@given`/`@when`/`@then` decorators. All steps that set
context variables must use `contextvars.copy_context().run()`.

### Stage C: Implement production code

1. In `src/falcon_correlate/middleware.py`, after the `user_id_var` definition
   (around line 30), add:

   - A module-level constant: `_MISSING_CONTEXT_PLACEHOLDER = "-"`
   - The `ContextualLogFilter` class:

         class ContextualLogFilter(logging.Filter):
             """Logging filter that injects correlation and user IDs
             into log records.

             This filter reads ``correlation_id_var`` and ``user_id_var``
             and copies their values onto the ``LogRecord`` as
             ``correlation_id`` and ``user_id`` attributes. When a
             context variable is not set, the placeholder ``"-"`` is used.

             The filter never suppresses records; it always returns
             ``True``.

             Examples

______________________________________________________________________
             Attach to a handler::

                 import logging
                 from falcon_correlate import ContextualLogFilter

                 handler = logging.StreamHandler()
                 handler.addFilter(ContextualLogFilter())
                 handler.setFormatter(
                     logging.Formatter(
                         "%(asctime)s [%(correlation_id)s] "
                         "[%(user_id)s] %(message)s"
                     )
                 )

             """

             def filter(self, record: logging.LogRecord) -> bool:
                 cid = correlation_id_var.get()
                 record.correlation_id = (
                     cid if cid is not None
                     else _MISSING_CONTEXT_PLACEHOLDER
                 )
                 uid = user_id_var.get()
                 record.user_id = (
                     uid if uid is not None
                     else _MISSING_CONTEXT_PLACEHOLDER
                 )
                 return True

1. In `src/falcon_correlate/__init__.py`:
   - Add `ContextualLogFilter` to the import block from `.middleware`.
   - Add `"ContextualLogFilter"` to the `__all__` list (in alphabetical order).

### Stage D: Update documentation

1. **`docs/users-guide.md`**:
   - Add a new `## Logging Integration` section after the "Accessing the
     correlation ID" section. Include:
     - Description of `ContextualLogFilter` and its purpose.
     - Basic usage example (adding the filter to a handler).
     - Format string example showing `%(correlation_id)s` and `%(user_id)s`.
     - `dictConfig` example.
     - Note about placeholder value `"-"` when context is not set.
   - Update the "Current Status" section to list logging filter integration.
   - Update the "future releases" bullet to remove mention of task 3.1 (or
     update to mention only remaining 3.1.2 and 3.2).

2. **`docs/roadmap.md`**:
   - Mark all 3.1.1 subtasks as `[x]`.

3. **`docs/falcon-correlation-id-middleware-design.md`**:
   - Add an implementation decision noting the placeholder choice (`"-"`) and
     the co-location in `middleware.py`.

### Stage E: Quality gates

Run all quality gates using `set -o pipefail` and `tee` to capture output:

    set -o pipefail
    make check-fmt 2>&1 | tee /tmp/falcon-correlate-check-fmt.log
    make typecheck 2>&1 | tee /tmp/falcon-correlate-typecheck.log
    make lint 2>&1 | tee /tmp/falcon-correlate-lint.log
    make test 2>&1 | tee /tmp/falcon-correlate-test.log
    make markdownlint 2>&1 | tee /tmp/falcon-correlate-markdownlint.log

If formatting fails, run `make fmt` and re-run `make check-fmt`.

## Validation and acceptance

Quality criteria:

- Tests: `make test` passes. All new tests in
  `test_contextual_log_filter.py` fail before implementation and pass after.
  All new BDD scenarios in `contextual_log_filter.feature` fail before and pass
  after. All existing tests pass throughout.
- Lint: `make lint` passes with no new warnings.
- Formatting: `make check-fmt` passes.
- Type checking: `make typecheck` passes (or the only failures are
  pre-existing and unrelated to this change).
- Markdown: `make markdownlint` passes.

Behavioural acceptance:

- `from falcon_correlate import ContextualLogFilter` succeeds.
- `isinstance(ContextualLogFilter(), logging.Filter)` returns `True`.
- When `correlation_id_var` is set to `"test-123"` and `user_id_var` is set to
  `"user-abc"`, calling `ContextualLogFilter().filter(record)` sets
  `record.correlation_id` to `"test-123"` and `record.user_id` to `"user-abc"`.
- When neither context variable is set, calling
  `ContextualLogFilter().filter(record)` sets `record.correlation_id` to `"-"`
  and `record.user_id` to `"-"`.
- A logger configured with `ContextualLogFilter` and a format string
  `"%(correlation_id)s %(user_id)s %(message)s"` emits output containing the
  context variable values.

## Idempotence and recovery

All steps are safe to re-run. If a test fails after implementation, adjust the
implementation or tests and re-run `make test`. If formatting fails, run
`make fmt` and re-run `make check-fmt`. The quality gate commands can be
repeated without side effects.

## Artifacts and notes

Keep the log files created via `tee` for evidence of passing checks:

- `/tmp/falcon-correlate-check-fmt.log`
- `/tmp/falcon-correlate-typecheck.log`
- `/tmp/falcon-correlate-lint.log`
- `/tmp/falcon-correlate-test.log`
- `/tmp/falcon-correlate-markdownlint.log`

## Interfaces and dependencies

New public name added to `falcon_correlate.__all__`:

- `ContextualLogFilter` — a `logging.Filter` subclass.

New internal constant (not exported):

- `_MISSING_CONTEXT_PLACEHOLDER: str = "-"` — the placeholder value used when
  context variables are not set.

Dependencies: standard library `logging` module only (already imported in
`middleware.py`). No new external dependencies.

## Files to modify

- `src/falcon_correlate/middleware.py` — Edit — Add
  `_MISSING_CONTEXT_PLACEHOLDER` constant and `ContextualLogFilter` class.
- `src/falcon_correlate/__init__.py` — Edit — Add `ContextualLogFilter` to
  imports and `__all__`.
- `src/falcon_correlate/unittests/test_contextual_log_filter.py` — Create —
  Unit tests.
- `tests/bdd/contextual_log_filter.feature` — Create — BDD feature file.
- `tests/bdd/test_contextual_log_filter_steps.py` — Create — BDD step
  definitions.
- `docs/users-guide.md` — Edit — Add logging filter section and update
  current status.
- `docs/roadmap.md` — Edit — Mark 3.1.1 complete.
- `docs/falcon-correlation-id-middleware-design.md` — Edit — Record
  implementation decisions.
- `docs/execplans/3-1-1-contextual-log-filter.md` — Create — This ExecPlan
  file.

## Revision note (required when editing an ExecPlan)

2026-02-23: Initial draft created to cover roadmap task 3.1.1 — implement
`ContextualLogFilter` with unit tests, BDD tests, and documentation updates.

2026-02-23: Marked plan complete. Updated progress, surprises, decisions, and
outcomes to reflect the implemented `ContextualLogFilter`, quality gate
results, and the BDD context variable cleanup lesson.
