# Document structlog integration pattern (3.2.1 + 3.2.2)

This ExecPlan (execution plan) is a living document. The sections
`Constraints`, `Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`,
`Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work
proceeds.

Status: COMPLETE

## Purpose / big picture

The `falcon-correlate` middleware stores correlation IDs and user IDs in
`contextvars.ContextVar` instances (`correlation_id_var` and `user_id_var`).
Users of the standard library `logging` module already have
`ContextualLogFilter` to inject these values into log records. However, users
of `structlog` — a popular structured logging library — have no guidance on how
to include these values in structured log output.

Task 3.2.1 fills this documentation gap by explaining how `structlog`'s
`merge_contextvars` processor relates to the library's context variables,
providing a copy-pasteable configuration example, and noting what bridging is
needed. Task 3.2.2 validates the documented pattern with unit and behavioural
tests.

After this change:

- A developer can read the "Structlog integration" section in
  `docs/users-guide.md` and find a complete, working configuration example that
  makes `correlation_id` and `user_id` appear in structlog's structured log
  output.
- A developer understands why `structlog.contextvars.merge_contextvars()` alone
  does not automatically pick up the library's context variables, and what
  bridging step is needed.
- Running `make test` exercises validation tests that prove the documented
  pattern works when `structlog` is installed and are cleanly skipped when it
  is not.

## Constraints

- Do not change existing public function signatures or existing tests.
- Do not add `structlog` as a runtime dependency. It is a dev/test dependency
  only.
- Do not add new public Python code to the library for this task. The
  integration is documentation-only, with example code shown in docs and
  validated by tests. The `__all__` list in `__init__.py` must not change.
- Follow the project's British English (Oxford English Dictionary) spelling
  conventions in documentation.
- Markdown paragraphs and bullets must wrap at 80 columns; code blocks at 120
  columns. Use `-` for list bullets.
- Python line length limit is 88 characters.
- Follow test-driven development (TDD): write tests first, then documentation.

## Tolerances (exception triggers)

- Scope: if implementation requires more than 12 files or 300 net lines
  changed, stop and escalate.
- Interface: if any existing public API signature must change, stop and
  escalate.
- Dependencies: if a new runtime dependency is required, stop and escalate.
  Adding `structlog` to the dev dependency group is expected and permitted.
- Iterations: if tests still fail after two fix attempts for the same root
  cause, stop and escalate with findings.
- Ambiguity: if the structlog API behaviour differs from what is documented
  here (e.g., `merge_contextvars` semantics have changed), stop and present
  options.

## Risks

- Risk: structlog's `merge_contextvars` implementation may change in future
  versions, invalidating the documented pattern. Severity: low. Likelihood:
  low. Mitigation: document the structlog version tested against; the custom
  processor approach reads from the library's own `ContextVar` instances and
  does not depend on structlog internals.

- Risk: `pytest.importorskip("structlog")` may interact unexpectedly with
  pytest-xdist parallel execution. Severity: low. Likelihood: low. Mitigation:
  use module-level `pytest.importorskip` which is the standard pattern and
  works correctly with xdist.

- Risk: BDD step definitions that import structlog at module level will cause
  import errors when structlog is not installed, even for unrelated tests.
  Severity: medium. Likelihood: medium. Mitigation: use
  `pytest.importorskip("structlog")` at module level in the step definition
  file, causing the entire module and its scenarios to be skipped.

## Progress

- [x] (2026-02-27 00:00Z) Write ExecPlan.
- [x] (2026-02-27 00:05Z) Add `structlog` to dev dependency group in
  `pyproject.toml`.
- [x] (2026-02-27 00:10Z) Write unit tests for structlog integration
  (6 unit tests across 3 test classes).
- [x] (2026-02-27 00:10Z) Write BDD feature file (2 scenarios) and step
  definitions.
- [x] (2026-02-27 00:12Z) Run tests — all 8 new tests pass.
- [x] (2026-02-27 00:15Z) Add "Structlog integration" section to
  `docs/users-guide.md`.
- [x] (2026-02-27 00:15Z) Record design decisions in design document
  appendix A.5.
- [x] (2026-02-27 00:18Z) Update "Current Status" section of
  `docs/users-guide.md`.
- [x] (2026-02-27 00:18Z) Mark tasks 3.2.1 and 3.2.2 complete in
  `docs/roadmap.md`.
- [x] (2026-02-27 00:20Z) Run all quality gates — all pass (269 passed,
  11 skipped).

## Surprises & discoveries

- Observation: `structlog.contextvars.merge_contextvars()` does NOT
  automatically pick up arbitrary `ContextVar` instances. It only reads
  `ContextVar` instances whose `.name` starts with the prefix `"structlog_"`,
  which are created by `structlog.contextvars.bind_contextvars()`. The
  library's `correlation_id_var` (name `"correlation_id"`) and `user_id_var`
  (name `"user_id"`) are invisible to it. Evidence: structlog source code; the
  processor iterates over the current context and filters by name prefix.
  Impact: The design document section 3.4.3 states that context variables set
  by the middleware "would be automatically picked up if `merge_contextvars` is
  in the processor chain." This is inaccurate. A bridging step is required. The
  documentation must explain this and provide bridging approaches.

## Decision log

- Decision: Document two structlog integration approaches rather than one.
  Rationale: Approach A (custom processor) is a "configure once, works
  everywhere" solution. Approach B (`bind_contextvars` in user middleware) is
  the approach suggested by structlog's own documentation. Documenting both
  gives users flexibility. The custom processor approach is recommended as
  primary because it requires no per-request bridging code. Date/Author:
  2026-02-27.

- Decision: Do NOT add library code (no new processor class in the package).
  Rationale: The design doc says "no additional code is required if contextvars
  are used." While this is technically inaccurate (bridging IS needed), the
  bridging code is trivial (~6 lines) and belongs in user configuration, not
  the library. Adding a processor to the library would create a runtime import
  path that touches structlog, which is not a dependency. The
  documentation-only approach keeps the dependency surface clean. Date/Author:
  2026-02-27.

- Decision: Add `structlog` only as a dev dependency, not an optional runtime
  dependency. Rationale: The library provides no structlog-specific code, so
  there is nothing to gate behind an optional extra. The dev dependency is
  needed only to run the validation tests. Date/Author: 2026-02-27.

- Decision: Correct the design document's claim about `merge_contextvars`.
  Rationale: Section 3.4.3 is factually incorrect about automatic pickup. The
  design document appendix should record this finding so future work does not
  repeat the misunderstanding. Date/Author: 2026-02-27.

- Decision: Use `event_dict.setdefault()` in the custom processor to avoid
  overwriting explicitly bound values. Rationale: This matches the "fill, don't
  overwrite" pattern used by `ContextualLogFilter`, providing consistent
  behaviour across standard logging and structlog integration paths.
  Date/Author: 2026-02-27.

## Outcomes & retrospective

The structlog integration documentation and validation are complete. The
users' guide now contains a "Structlog integration" section with two bridging
approaches: a custom processor (recommended) and a `bind_contextvars`
middleware (alternative). The design document appendix A.5 records the finding
that `merge_contextvars` does not pick up arbitrary `ContextVar` instances.

New tests: 6 unit tests in `test_structlog_integration.py` covering three
categories (merge_contextvars limitation, custom processor approach, and
bind_contextvars approach) plus 2 BDD scenarios in
`structlog_integration.feature`. Total test suite: 269 passed, 11 skipped
(CI-only workflow tests).

All quality gates passed: `make check-fmt`, `make lint`, `make typecheck`,
`make test`, `make markdownlint`.

Key lesson: `pytest.importorskip()` at module level causes imports after it to
trigger E402 (module-level import not at top of file). These require `# noqa:
E402` suppression since the import order is intentional — the `importorskip`
call must precede imports that depend on the skipped package.

## Context and orientation

The project is `falcon-correlate`, a correlation ID middleware for the Falcon
web framework. The package source lives under `src/falcon_correlate/`.

The middleware class (`CorrelationIDMiddleware`) and the two context variables
(`correlation_id_var`, `user_id_var`) are defined in
`src/falcon_correlate/middleware.py`. The public API is exported from
`src/falcon_correlate/__init__.py` via an `__all__` list sorted in isort-style
(SCREAMING_CASE first, then CamelCase, then lowercase).

Unit tests are co-located in `src/falcon_correlate/unittests/` and follow a
class-based pattern with descriptive docstrings (one test file per concern).
Shared unit-test fixtures (`request_response_factory`, `isolated_context`,
`logger_with_capture`) live in `src/falcon_correlate/unittests/conftest.py`.

Behavioural tests live in `tests/bdd/` as Gherkin `.feature` files with
accompanying `test_*_steps.py` step definition files using `pytest-bdd`. Step
definition files use a `Context` TypedDict for passing state between steps, and
an `autouse` fixture `_reset_context_variables` for cleanup.

The design specification is in
`docs/falcon-correlation-id-middleware-design.md`. Section 3.4.3 describes the
structlog integration considerations. Appendix A records implementation
decisions; the last entry is A.4 (req.context integration).

The users' guide is in `docs/users-guide.md`. It has a "Logging integration"
section (line 298) with subsections for basic usage, recommended format string,
`dictConfig`, placeholder behaviour, and preserving explicit metadata. The new
structlog section will be added after "Preserving explicit metadata" (line 437)
and before "Full Configuration Example" (line 439).

The roadmap is in `docs/roadmap.md`. Tasks 3.2.1 and 3.2.2 (lines 131–137) are
currently unchecked.

### Key files

- `pyproject.toml` — Edit — Add `structlog` to dev dependency group.
- `src/falcon_correlate/unittests/test_structlog_integration.py` — Create —
  Unit tests validating the documented patterns.
- `tests/bdd/structlog_integration.feature` — Create — BDD feature file.
- `tests/bdd/test_structlog_integration_steps.py` — Create — BDD step
  definitions.
- `docs/users-guide.md` — Edit — Add "Structlog integration" section; update
  "Current Status".
- `docs/falcon-correlation-id-middleware-design.md` — Edit — Add appendix
  section A.5 recording the `merge_contextvars` finding.
- `docs/roadmap.md` — Edit — Mark 3.2.1 and 3.2.2 subtasks as `[x]`.
- `docs/execplans/3-2-1-document-structlog-integration-pattern.md` — Create —
  This ExecPlan file.

### Existing patterns to reuse

- Unit test structure: class-based tests with descriptive docstrings, as in
  `test_contextual_log_filter.py`.
- `isolated_context` fixture from
  `src/falcon_correlate/unittests/conftest.py` for context variable isolation.
- BDD step definitions: `Context` TypedDict, `scenarios()` auto-loader,
  `@given`/`@when`/`@then` decorators, `_reset_context_variables` autouse
  fixture, `pytest.importorskip("structlog")` for conditional skipping.

## Plan of work

### Stage A: Add structlog dev dependency

Edit `pyproject.toml` to add `"structlog"` to the `[dependency-groups] dev`
list, placed alphabetically. Run `uv sync` to install. Verify with
`python -c "import structlog; print(structlog.__version__)"`.

### Stage B: Write unit tests (TDD)

Create `src/falcon_correlate/unittests/test_structlog_integration.py` with
`pytest.importorskip("structlog")` at module top.

The custom processor function tested is:

```python
def inject_correlation_context(
    logger: object,
    method_name: str,
    event_dict: dict[str, object],
) -> dict[str, object]:
    """Inject correlation ID and user ID into structlog event dict."""
    event_dict.setdefault(
        "correlation_id", correlation_id_var.get() or "-"
    )
    event_dict.setdefault(
        "user_id", user_id_var.get() or "-"
    )
    return event_dict
```

Test classes:

1. `TestMergeContextvarsLimitation` — Proves `merge_contextvars` does NOT pick
   up `correlation_id_var` or `user_id_var` (negative test documenting the
   limitation).

2. `TestCustomProcessorApproach` — Validates the custom processor:
   - IDs injected when context variables are set.
   - Placeholder `"-"` when context variables are unset.
   - Existing keys preserved via `setdefault` (explicit structlog bindings
     take precedence).

3. `TestBindContextvarsApproach` — Validates the alternative approach of
   calling `structlog.contextvars.bind_contextvars()` to bridge values.

Each test must use the `isolated_context` fixture. Each test must reset
structlog configuration via `structlog.reset_defaults()` in teardown (using an
autouse fixture). Events are captured using a custom processor that appends to
a list and raises `structlog.DropEvent`.

### Stage C: Write BDD scenarios (TDD)

Create `tests/bdd/structlog_integration.feature` with scenarios:

1. Custom processor injects IDs into structured output.
2. Custom processor uses placeholder when context is empty.

Create `tests/bdd/test_structlog_integration_steps.py` following existing
patterns. Module-level `pytest.importorskip("structlog")` to skip when not
installed. `_reset_context_variables` autouse fixture for cleanup. A structlog
teardown fixture that calls `structlog.reset_defaults()`.

### Stage D: Verify tests pass

Run `make test` and confirm new tests pass when structlog is installed.

### Stage E: Add documentation to users' guide

Insert `## Structlog integration` section in `docs/users-guide.md` between
"Preserving explicit metadata" and "Full Configuration Example". The section
covers:

- How it works — explain that `merge_contextvars` only reads
  structlog-managed variables, not arbitrary `ContextVar` instances.
- Custom processor (recommended) — provide `inject_correlation_context`
  function and full `structlog.configure()` example.
- Alternative: `bind_contextvars` in middleware — show a bridging middleware
  as an alternative approach.
- Note on `merge_contextvars` — explicit caveat about the limitation.

Update "Current Status" to list structlog documentation. Remove task 3.2 from
the "future releases" line.

### Stage F: Update design document

Add appendix section A.5 in `docs/falcon-correlation-id-middleware-design.md`
recording the `merge_contextvars` limitation finding, the decision to document
bridging approaches as user-side code, and the `setdefault` pattern for "fill,
don't overwrite" consistency.

### Stage G: Update roadmap

Mark all subtasks under 3.2.1 and 3.2.2 as `[x]` in `docs/roadmap.md`.

### Stage H: Quality gates

Run all gates with `set -o pipefail` and `tee`:

```bash
set -o pipefail
make check-fmt 2>&1 | tee /tmp/fc-check-fmt.log
make typecheck 2>&1 | tee /tmp/fc-typecheck.log
make lint 2>&1 | tee /tmp/fc-lint.log
make test 2>&1 | tee /tmp/fc-test.log
make markdownlint 2>&1 | tee /tmp/fc-markdownlint.log
```

If formatting fails, run `make fmt` and re-run `make check-fmt`.

## Validation and acceptance

Quality criteria:

- Tests: `make test` passes. All new tests in
  `test_structlog_integration.py` pass when structlog is installed and are
  skipped when it is not. All new BDD scenarios in
  `structlog_integration.feature` pass when structlog is installed and are
  skipped when it is not. All existing tests pass unchanged.
- Lint: `make lint` passes with no new warnings.
- Formatting: `make check-fmt` passes.
- Type checking: `make typecheck` passes.
- Markdown: `make markdownlint` passes.

Behavioural acceptance:

- The custom processor function, when configured in structlog's processor
  chain, causes `correlation_id` and `user_id` to appear in the event dict with
  values matching `correlation_id_var.get()` and `user_id_var.get()`.
- When context variables are not set, the processor substitutes `"-"`.
- When a value is explicitly bound via structlog's own binding, the processor
  does not overwrite it (tested via `setdefault`).
- The users' guide "Structlog integration" section is readable and contains
  complete, copy-pasteable examples.
- Tests are skipped (not errored) when structlog is not installed.

## Idempotence and recovery

All steps are safe to re-run. If a test fails after implementation, adjust the
test or the documented pattern and re-run `make test`. If formatting fails, run
`make fmt` and re-run `make check-fmt`. The quality gate commands can be
repeated without side effects.

Structlog configuration in tests must be reset via `structlog.reset_defaults()`
in teardown to prevent cross-test contamination.

## Artifacts and notes

Keep the log files created via `tee` for evidence of passing checks:

- `/tmp/fc-check-fmt.log`
- `/tmp/fc-typecheck.log`
- `/tmp/fc-lint.log`
- `/tmp/fc-test.log`
- `/tmp/fc-markdownlint.log`

## Interfaces and dependencies

No new public names are added to `falcon_correlate.__all__`.

New dev dependency: `structlog` added to the `[dependency-groups] dev` list in
`pyproject.toml`.

The custom processor function documented in the users' guide has this signature:

```python
def inject_correlation_context(
    logger: object,
    method_name: str,
    event_dict: dict[str, object],
) -> dict[str, object]:
    ...
```

This follows structlog's processor protocol. It is user-side code, not library
code.

## Revision note (required when editing an ExecPlan)

2026-02-27: Initial draft created to cover roadmap tasks 3.2.1 (document
structlog integration pattern) and 3.2.2 (validate structlog integration). Key
finding: `structlog.contextvars.merge_contextvars()` does NOT pick up arbitrary
`ContextVar` instances — it only reads those with a `"structlog_"` name prefix.
This contradicts the design document section 3.4.3. The plan documents two
bridging approaches and adds validation tests.

2026-02-27: Marked plan complete. Updated progress, surprises, decisions, and
outcomes to reflect the implemented structlog integration documentation,
quality gate results, and the `pytest.importorskip` E402 suppression lesson.
