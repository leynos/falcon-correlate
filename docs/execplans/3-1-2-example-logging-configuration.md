# Provide example logging configuration (3.1.2)

This ExecPlan (execution plan) is a living document. The sections
`Constraints`, `Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`,
`Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work
proceeds.

Status: COMPLETE

## Purpose / big picture

Task 3.1.1 delivered `ContextualLogFilter`, a `logging.Filter` subclass that
injects `correlation_id` and `user_id` into every `LogRecord`. Users can
already attach the filter to handlers, but the library does not yet ship a
recommended format string or a copy-pasteable `dictConfig` example in the class
docstring. Task 3.1.2 fills this gap.

After this change a developer can:

1. Import `RECOMMENDED_LOG_FORMAT` from `falcon_correlate` and pass it
   directly to `logging.Formatter` or embed it in a `dictConfig` dictionary,
   eliminating copy-paste errors.
2. Read the `ContextualLogFilter` class docstring and find a complete
   `dictConfig` example ready to drop into application startup code.

Success is observable when:

- `from falcon_correlate import RECOMMENDED_LOG_FORMAT` succeeds and returns
  a string containing `%(correlation_id)s` and `%(user_id)s`.
- `RECOMMENDED_LOG_FORMAT` appears in `falcon_correlate.__all__`.
- The `ContextualLogFilter` class docstring includes both a recommended-format
  example and a `dictConfig` example.
- `docs/users-guide.md` documents the recommended format string constant.
- All existing tests continue to pass unchanged.
- New unit tests (pytest) and behavioural tests (pytest-bdd) cover the new
  constant and its integration with `logging.Formatter` and `dictConfig`.
- `docs/roadmap.md` shows task 3.1.2 as complete.
- All quality gates pass (`make check-fmt`, `make typecheck`, `make lint`,
  `make test`, `make markdownlint`).

## Constraints

- Follow test-driven development (TDD): write tests first, then implement.
- Do not change existing public function signatures or existing tests.
- Do not add external dependencies.
- Define the constant in `src/falcon_correlate/middleware.py`, co-located
  with `ContextualLogFilter` and `_MISSING_CONTEXT_PLACEHOLDER`, following the
  project convention of grouping by feature.
- The recommended format string must match the design document §3.4.2
  specification.
- Follow the project's British English spelling conventions in documentation.
- Markdown must wrap at 80 columns (paragraphs and bullets); code blocks at
  120 columns. Use `-` for list bullets.
- Python line length limit is 88 characters.

## Tolerances (exception triggers)

- Scope: if implementation requires more than 10 files or 200 net lines
  changed, stop and escalate.
- Interface: if any existing public API signature must change, stop and
  escalate.
- Dependencies: if a new external dependency is required, stop and escalate.
- Iterations: if tests still fail after two fix attempts for the same root
  cause, stop and escalate with findings.
- Ambiguity: if the recommended format string conflicts with the design
  document in a way that cannot be reconciled, stop and present options.

## Risks

- Risk: docstring code examples exceed the 88-character Python line limit.
  Severity: low. Likelihood: medium. Mitigation: the `dictConfig` dictionary in
  the docstring uses the same indentation style as the existing
  `test_filter_works_with_dict_config` test (which fits in 88 columns). Split
  long format-string lines across multiple string literals within parentheses.

- Risk: BDD step name collision with existing steps. Severity: low.
  Likelihood: low. Mitigation: new `Given` step names are distinct from
  existing ones (e.g. "a logger configured with the recommended log format" vs.
  "a logger configured with the contextual log filter").

- Risk: `markdownlint` or `mdformat` reformats the users-guide in unexpected
  ways. Severity: low. Likelihood: medium. Mitigation: run `make fmt` then
  `make markdownlint` and inspect diffs before committing.

## Progress

- [x] (2026-02-25 00:00Z) Write ExecPlan.
- [x] (2026-02-25 00:05Z) Add unit tests for `RECOMMENDED_LOG_FORMAT`
  (TDD red phase).
- [x] (2026-02-25 00:10Z) Add BDD scenarios and step definitions (TDD red
  phase).
- [x] (2026-02-25 00:15Z) Implement `RECOMMENDED_LOG_FORMAT` constant in
  `middleware.py`.
- [x] (2026-02-25 00:15Z) Expand `ContextualLogFilter` docstring with
  recommended-format and `dictConfig` examples.
- [x] (2026-02-25 00:15Z) Export `RECOMMENDED_LOG_FORMAT` in `__init__.py`
  and `__all__`.
- [x] (2026-02-25 00:20Z) Run tests to confirm they pass (TDD green
  phase).
- [x] (2026-02-25 00:25Z) Update `docs/users-guide.md` with recommended
  format string section.
- [x] (2026-02-25 00:25Z) Record design decisions in design document.
- [x] (2026-02-25 00:25Z) Mark task 3.1.2 complete in `docs/roadmap.md`.
- [x] (2026-02-25 00:30Z) Run all quality gates (`make check-fmt`,
  `make typecheck`, `make lint`, `make test`, `make markdownlint`).

## Surprises & discoveries

- Observation: ruff's `RUF022` rule enforces isort-style sorting of
  `__all__`, which places `RECOMMENDED_LOG_FORMAT` (all-uppercase) before
  `ContextualLogFilter` (title-case). This differs from Python's default
  `sorted()` order. Evidence: `ruff check` flagged the initial placement after
  `CorrelationIDMiddleware`. Impact: used `ruff check --fix` to auto-sort and
  adopted the resulting order.

- Observation: ruff's `N811` rule forbids importing a constant with a
  lowercase alias (`RECOMMENDED_LOG_FORMAT as fmt`). Evidence: lint failure on
  the test that verified importability. Impact: renamed the alias to
  `IMPORTED_FMT` to satisfy the naming convention.

## Decision log

- Decision: Expose a public `RECOMMENDED_LOG_FORMAT` constant rather than
  documenting the format string only in prose. Rationale: the project already
  defines module-level constants for shared values
  (`_MISSING_CONTEXT_PLACEHOLDER`, `DEFAULT_HEADER_NAME`). A public constant
  lets users `from falcon_correlate import RECOMMENDED_LOG_FORMAT` and pass it
  directly to `logging.Formatter` or embed it in a `dictConfig` dictionary.
  This eliminates copy-paste transcription errors and is the strongest form of
  "documenting" a recommended format. Date/Author: 2026-02-25.

- Decision: Use the exact format string from design document §3.4.2 as the
  constant's value. Rationale: the design document is the source of truth for
  the recommended format. The value is:

  ```plaintext
  %(asctime)s - [%(levelname)s] - [%(correlation_id)s] - [%(user_id)s] - %(name)s - %(message)s
  ```

  The existing users-guide examples use slightly different formats (simpler,
  without `%(levelname)s`); these remain as-is to show customisation options,
  while the constant provides the "batteries-included" default. Date/Author:
  2026-02-25.

## Outcomes & retrospective

The `RECOMMENDED_LOG_FORMAT` constant is defined in `middleware.py` and
exported via `__init__.py` as part of the public API. Its value matches the
design document §3.4.2 format string. The `ContextualLogFilter` class docstring
now includes three examples: basic handler attachment, using the recommended
format constant, and a complete `dictConfig` configuration.

New tests: 5 unit tests in `TestRecommendedLogFormat` covering export,
importability, placeholder content, formatter integration, and `dictConfig`
integration; plus 2 BDD scenarios in `contextual_log_filter.feature` covering
recommended-format output and `dictConfig` integration. Total test suite: 261
passed, 11 skipped.

All quality gates passed: `make check-fmt`, `make typecheck`, `make lint`,
`make test`, `make markdownlint`.

Key lesson: ruff's `RUF022` rule enforces isort-style sorting of `__all__`,
which places all-uppercase names before title-case names. Use
`ruff check --fix` to auto-sort rather than guessing the order.

## Context and orientation

The project is `falcon-correlate`, a correlation ID middleware for the Falcon
web framework. The package source lives under `src/falcon_correlate/`.

`ContextualLogFilter` is defined in `src/falcon_correlate/middleware.py` (lines
35–97). It injects `correlation_id` and `user_id` attributes into `LogRecord`
objects, reading from `correlation_id_var` and `user_id_var` context variables.
When a context variable is not set, the placeholder `"-"` (stored in
`_MISSING_CONTEXT_PLACEHOLDER`) is used.

The class is exported from `src/falcon_correlate/__init__.py` and listed in
`__all__`. The `__all__` list is sorted case-sensitively: uppercase names first
(`ContextualLogFilter`, `CorrelationIDConfig`, `CorrelationIDMiddleware`, then
the future `RECOMMENDED_LOG_FORMAT`), followed by lowercase names
(`correlation_id_var`, `default_uuid7_generator`, `default_uuid_validator`,
`hello`, `user_id_var`).

Unit tests are co-located in `src/falcon_correlate/unittests/` and follow a
class-based pattern with descriptive docstrings. Shared unit-test fixtures
(`isolated_context`, `logger_with_capture`) live in
`src/falcon_correlate/unittests/conftest.py`. Behavioural tests live in
`tests/bdd/` as Gherkin `.feature` files with accompanying `test_*_steps.py`
step definition files using `pytest-bdd`.

The design specification[^1] describes the recommended format string in §3.4.2
(line 444) and provides a reference `dictConfig` example in §4.2 (line 819).

[^1]: `docs/falcon-correlation-id-middleware-design.md`

### Key files

- `src/falcon_correlate/middleware.py` — Edit — Add
  `RECOMMENDED_LOG_FORMAT` constant; expand `ContextualLogFilter` docstring.
- `src/falcon_correlate/__init__.py` — Edit — Add `RECOMMENDED_LOG_FORMAT`
  to imports and `__all__`.
- `src/falcon_correlate/unittests/test_contextual_log_filter.py` — Edit —
  Add `TestRecommendedLogFormat` test class.
- `tests/bdd/contextual_log_filter.feature` — Edit — Add two scenarios.
- `tests/bdd/test_contextual_log_filter_steps.py` — Edit — Add new step
  definitions.
- `docs/users-guide.md` — Edit — Add "Recommended format string"
  subsection.
- `docs/falcon-correlation-id-middleware-design.md` — Edit — Record
  implementation decision in §4.6.
- `docs/roadmap.md` — Edit — Mark 3.1.2 subtasks as `[x]`.

### Existing patterns to reuse

- Unit test structure: class-based tests with descriptive docstrings, as in
  `TestContextualLogFilterExports` and
  `TestContextualLogFilterLoggingIntegration`.
- `isolated_context` fixture from
  `src/falcon_correlate/unittests/conftest.py` for context variable isolation.
- `logger_with_capture` fixture for integration tests.
- BDD step definitions: `Context` TypedDict, `scenarios()` auto-loader,
  `@given`/`@when`/`@then` decorators, `_reset_context_variables` autouse
  fixture for cleanup, as in `tests/bdd/test_contextual_log_filter_steps.py`.

## Plan of work

### Stage A: Add unit tests (TDD red phase)

Add a new test class `TestRecommendedLogFormat` to
`src/falcon_correlate/unittests/test_contextual_log_filter.py`. The class
contains five tests covering the new `RECOMMENDED_LOG_FORMAT` constant:

1. `test_recommended_log_format_in_all` — Assert
   `"RECOMMENDED_LOG_FORMAT"` is in `falcon_correlate.__all__`.

2. `test_recommended_log_format_importable_from_root` — Assert
   `from falcon_correlate import RECOMMENDED_LOG_FORMAT` succeeds and the value
   is a `str`.

3. `test_recommended_log_format_contains_required_placeholders` — Assert
   the string contains both `%(correlation_id)s` and `%(user_id)s`.

4. `test_recommended_log_format_usable_with_formatter` — Create a
   `logging.Formatter(RECOMMENDED_LOG_FORMAT)`, attach a handler with
   `ContextualLogFilter` to a logger, set context variables in an isolated
   context, emit a log message, and assert the output contains the correlation
   ID, user ID, and message text.

5. `test_recommended_log_format_works_in_dictconfig` — Build a `dictConfig`
   dictionary that uses `RECOMMENDED_LOG_FORMAT` as the format string, apply
   with `logging.config.dictConfig`, emit a log record in an isolated context,
   and assert the captured output contains the expected values. Follow the
   existing `test_filter_works_with_dict_config` pattern for handler teardown.

All tests that interact with context variables must use the `isolated_context`
fixture. Tests that create loggers must clean up handlers in a `finally` block
or via the `logger_with_capture` fixture.

### Stage B: Add BDD scenarios (TDD red phase)

Add two new scenarios to `tests/bdd/contextual_log_filter.feature`:

```gherkin
  Scenario: Recommended format string produces expected output
    Given a logger configured with the recommended log format
    And the correlation ID is set to "fmt-cid-001"
    And the user ID is set to "fmt-uid-001"
    When a log message "format test" is emitted
    Then the formatted output should contain "fmt-cid-001"
    And the formatted output should contain "fmt-uid-001"
    And the formatted output should contain "format test"

  Scenario: Filter integrates with dictConfig using recommended format
    Given a logger configured via dictConfig with the recommended format
    And the correlation ID is set to "dict-cid-001"
    And the user ID is set to "dict-uid-001"
    When a log message "dictconfig format test" is emitted
    Then the formatted output should contain "dict-cid-001"
    And the formatted output should contain "dict-uid-001"
    And the formatted output should contain "dictconfig format test"
```

Add two new step definitions to `tests/bdd/test_contextual_log_filter_steps.py`:

1. `given_logger_with_recommended_format` — matching
   `"a logger configured with the recommended log format"`. Import
   `RECOMMENDED_LOG_FORMAT` from `falcon_correlate`. Create a `StreamHandler`
   writing to a `StringIO`, set its formatter to
   `logging.Formatter(RECOMMENDED_LOG_FORMAT)`, attach a `ContextualLogFilter`,
   wire up a named test logger, register teardown via `request.addfinalizer`,
   and return the `Context` dict with `logger`, `stream`, and `log_filter`
   keys. Follow the existing `given_logger_with_filter` pattern exactly.

2. `given_logger_via_dictconfig_with_recommended_format` — matching
   `"a logger configured via dictConfig with the recommended format"`. Import
   `RECOMMENDED_LOG_FORMAT`. Build a `dictConfig` dictionary with the constant
   as the format value and `"falcon_correlate.ContextualLogFilter"` as the
   filter class. Apply via `logging.config.dictConfig`. Create a `StringIO`,
   swap the handler's stream, register teardown, and return the `Context` dict.

The existing steps for setting context variables, emitting messages, and
checking output are already defined and will be reused without modification.

### Stage C: Implement production code

1. In `src/falcon_correlate/middleware.py`, after
   `_MISSING_CONTEXT_PLACEHOLDER` (line 32) and before the
   `ContextualLogFilter` class (line 35), add the public constant:

   ```python
   RECOMMENDED_LOG_FORMAT: str = (
       "%(asctime)s - [%(levelname)s] - [%(correlation_id)s] - "
       "[%(user_id)s] - %(name)s - %(message)s"
   )
   ```

2. Expand the `ContextualLogFilter` class docstring to include:

   - A paragraph introducing `RECOMMENDED_LOG_FORMAT` as an importable
     constant, with its value shown in a code block.
   - An example using the constant with `logging.Formatter`.
   - A complete `dictConfig` example that references the constant.

3. In `src/falcon_correlate/__init__.py`:

   - Add `RECOMMENDED_LOG_FORMAT` to the import from `.middleware`
     (after `CorrelationIDMiddleware`).
   - Add `"RECOMMENDED_LOG_FORMAT"` to `__all__` (after
     `"CorrelationIDMiddleware"`, before `"correlation_id_var"`).

### Stage D: Update documentation

1. **`docs/users-guide.md`**: Insert a new `### Recommended format string`
   subsection between the existing `### Basic usage` and `### Using dictConfig`
   subsections.

2. **`docs/falcon-correlation-id-middleware-design.md`**: Add a new
   subsection `#### 4.6.9. Recommended format string constant` after §4.6.8
   documenting the decision.

3. **`docs/roadmap.md`**: Change 3.1.2 items from `[ ]` to `[x]`.

### Stage E: Quality gates

Run all quality gates:

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

- Tests: `make test` passes. All new tests in `TestRecommendedLogFormat`
  fail before implementation and pass after. All new BDD scenarios in
  `contextual_log_filter.feature` fail before and pass after. All existing
  tests pass throughout.
- Lint: `make lint` passes with no new warnings.
- Formatting: `make check-fmt` passes.
- Type checking: `make typecheck` passes.
- Markdown: `make markdownlint` passes.

Behavioural acceptance:

- `from falcon_correlate import RECOMMENDED_LOG_FORMAT` succeeds.
- `isinstance(RECOMMENDED_LOG_FORMAT, str)` returns `True`.
- `"%(correlation_id)s" in RECOMMENDED_LOG_FORMAT` is `True`.
- `"%(user_id)s" in RECOMMENDED_LOG_FORMAT` is `True`.
- A logger configured with `ContextualLogFilter` and a formatter using
  `RECOMMENDED_LOG_FORMAT`, when emitting a record with `correlation_id_var`
  set to `"test-123"` and `user_id_var` set to `"user-abc"`, produces output
  containing `[test-123]` and `[user-abc]`.
- The `ContextualLogFilter` class docstring (visible via `help()` or IDE
  tooltips) includes a `dictConfig` example and a recommended-format example.

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

- `RECOMMENDED_LOG_FORMAT` — a `str` constant containing the recommended
  `logging.Formatter` format string.

Dependencies: standard library `logging` module only (already imported in
`middleware.py`). No new external dependencies.

## Revision note (required when editing an ExecPlan)

2026-02-25: Initial draft created to cover roadmap task 3.1.2 — provide example
logging configuration with a `RECOMMENDED_LOG_FORMAT` public constant, expanded
`ContextualLogFilter` docstring with `dictConfig` example, comprehensive unit
and BDD tests, and documentation updates.

2026-02-25: Marked plan complete. Updated progress, surprises, decisions, and
outcomes to reflect the implemented `RECOMMENDED_LOG_FORMAT` constant, quality
gate results, and the `RUF022`/`N811` lint lessons.
