# Integrate with Falcon's req.context (2.4.3)

This ExecPlan is a living document. The sections `Constraints`, `Tolerances`,
`Risks`, `Progress`, `Surprises & Discoveries`, `Decision Log`, and
`Outcomes & Retrospective` must be kept up to date as work proceeds.

Status: COMPLETE

## Purpose / big picture

Task 2.4.2 added lifecycle management so that `correlation_id_var` is set
during `process_request` and reset during `process_response`. The middleware
also copies the correlation ID to `req.context.correlation_id` (line 529 of
`src/falcon_correlate/middleware.py`), providing a convenient Falcon-native
access method. Task 2.4.3 makes this dual-access pattern an explicit,
documented, and independently tested feature of the library.

Success is observable when:

- Dedicated unit tests prove that `req.context.correlation_id` and
  `correlation_id_var.get()` always return the same value across all
  correlation ID selection paths (generated, trusted incoming, untrusted
  rejection, validator rejection) and under concurrent request handling.
- Dedicated behavioural tests (`pytest-bdd`) verify the same parity guarantee
  from a user-facing perspective.
- `docs/users-guide.md` documents both access methods with usage guidance and
  code examples, and removes the "future release" caveat for task 2.4.3.
- `docs/falcon-correlation-id-middleware-design.md` records the implementation
  decision as appendix entry A.4.
- `docs/roadmap.md` marks 2.4.3 complete only after all tests and quality
  gates pass.
- `make check-fmt`, `make typecheck`, `make lint`, and `make test` all pass.

## Constraints

- Do not modify `src/falcon_correlate/middleware.py`. The production code
  already implements the feature; this task adds tests and documentation only.
- Do not change public constructor signatures or existing public exports.
- Do not add external dependencies.
- Markdown changes must follow the project documentation style guide
  (80-column wrapping, dash bullets, British English with Oxford spelling).
- Follow the testing guidelines in `AGENTS.md`: write tests before considering
  the functionality complete; ensure both unit and behavioural tests pass.

## Tolerances (exception triggers)

- Scope: if implementation requires more than 8 files or 250 net lines
  changed, stop and escalate.
- Interface: if a public API signature must change, stop and escalate.
- Dependencies: if a new dependency is needed, stop and escalate.
- Behaviour: if new tests conflict with existing accepted tests, stop and
  document options before proceeding.
- Iteration: if quality gates still fail after two fix iterations for the same
  root cause, stop and escalate with findings.

## Risks

- Risk: BDD concurrent-request tests may be flaky due to thread scheduling.
  Severity: low. Likelihood: low. Mitigation: use the established pattern from
  `test_contextvar_lifecycle_steps.py` with a short sleep delay in the test
  resource to encourage request overlap, and `ThreadPoolExecutor` for
  deterministic concurrency.

- Risk: documentation updates may fail `make markdownlint` due to line length
  or formatting. Severity: low. Likelihood: medium. Mitigation: run `make fmt`
  after documentation changes and verify with `make markdownlint`.

## Progress

- [x] (2026-02-21) Write ExecPlan (this document).
- [x] (2026-02-21) Create unit tests in
  `src/falcon_correlate/unittests/test_req_context_integration.py`.
- [x] (2026-02-21) Verify unit tests pass with `make test` (228 passed).
- [x] (2026-02-21) Create BDD feature file
  `tests/bdd/req_context_integration.feature`.
- [x] (2026-02-21) Create BDD step definitions
  `tests/bdd/test_req_context_integration_steps.py`.
- [x] (2026-02-21) Verify BDD tests pass with `make test` (228 passed).
- [x] (2026-02-21) Update `docs/users-guide.md` with dual-access
  documentation.
- [x] (2026-02-21) Update `docs/falcon-correlation-id-middleware-design.md`
  with appendix A.4.
- [x] (2026-02-21) Update `docs/roadmap.md` to mark 2.4.3 complete.
- [x] (2026-02-21) Run all quality gates and capture logs.
- [x] (2026-02-21) Update ExecPlan status to COMPLETE.

## Surprises & discoveries

- The production code for `req.context.correlation_id` assignment (line 529 of
  `middleware.py`) was already in place from task 2.4.2 or earlier. The
  existing lifecycle tests in `test_contextvar_lifecycle.py` verified this as a
  side-effect via the `_assert_contextvar_state` helper. This task therefore
  required no production code changes — only dedicated tests and documentation.

## Decision log

- Decision: create dedicated test files (`test_req_context_integration.py`,
  `req_context_integration.feature`) rather than extending the existing
  lifecycle test files. Rationale: follows established project convention (task
  2.4.1 has `test_context_variables.py` and `context_variables.feature`; task
  2.4.2 has `test_contextvar_lifecycle.py` and `contextvar_lifecycle.feature`).
  Dedicated files make the dual-access parity the explicit subject under test.
  Date/Author: 2026-02-21.

- Decision: no production code changes. Rationale: `process_request` at line
  529 of `middleware.py` already sets `req.context.correlation_id` from the
  same `correlation_id` variable used to set `correlation_id_var` at line 530.
  Both are set in the same code path, guaranteeing parity. This task documents
  and tests that guarantee. Date/Author: 2026-02-21.

## Outcomes & retrospective

Task 2.4.3 is implemented end to end.

The dual-access pattern (`req.context.correlation_id` and
`correlation_id_var.get()`) is now explicitly tested and documented. No
production code changes were needed because the middleware already set both
values in `process_request`.

New tests were added in both unit and behavioural suites:

- `src/falcon_correlate/unittests/test_req_context_integration.py` — five
  unit tests covering parametrised parity across four selection paths plus
  concurrent isolation.
- `tests/bdd/req_context_integration.feature` — three BDD scenarios covering
  generated ID parity, trusted incoming ID parity, and concurrent parity.
- `tests/bdd/test_req_context_integration_steps.py` — BDD step definitions.

Documentation and tracking were updated:

- `docs/users-guide.md` now documents both access methods with a comparison
  table and code examples, and lists the feature as implemented.
- `docs/falcon-correlation-id-middleware-design.md` now records the task 2.4.3
  implementation decision as appendix A.4.
- `docs/roadmap.md` now marks 2.4.3 complete.

All quality gates pass: `make check-fmt`, `make typecheck`, `make lint`,
`make test` (228 passed, 11 skipped), and `make markdownlint`.

## Context and orientation

`falcon-correlate` is a Falcon web framework middleware library for managing
correlation IDs throughout the HTTP request lifecycle. The middleware lives in
a single module at `src/falcon_correlate/middleware.py`.

The `CorrelationIDMiddleware.process_request` method (lines 492-531) selects a
correlation ID (from a trusted incoming header or by generation) and stores it
in two places:

- `req.context.correlation_id` (line 529) — Falcon's per-request context
  object, accessible within responders and hooks that have access to `req`.
- `correlation_id_var` (line 530) — a `contextvars.ContextVar` instance,
  accessible anywhere in the call stack without needing `req`.

The design specification at section 3.3.3 of
`docs/falcon-correlation-id-middleware-design.md` recommends this pattern:
`contextvars` as the primary authoritative store, with `req.context` as a
convenience copy.

### Key files

- `src/falcon_correlate/middleware.py` — middleware implementation (no changes
  planned).
- `src/falcon_correlate/__init__.py` — public API exports (no changes
  planned).
- `src/falcon_correlate/unittests/test_contextvar_lifecycle.py` — existing
  lifecycle unit tests; the `_assert_contextvar_state` helper at line 59
  already verifies both access methods as a side-effect.
- `tests/bdd/contextvar_lifecycle.feature` — existing lifecycle BDD scenarios.
- `tests/bdd/test_contextvar_lifecycle_steps.py` — existing lifecycle step
  definitions; `_LifecycleResource` reads both `req.context.correlation_id` and
  `correlation_id_var.get()`.
- `tests/conftest.py` — shared test fixtures (`CorrelationEchoResource`,
  `TrackingMiddleware`).
- `docs/users-guide.md` — user-facing documentation (needs dual-access
  section and status update).
- `docs/falcon-correlation-id-middleware-design.md` — design document (needs
  appendix A.4).
- `docs/roadmap.md` — completion checklist (lines 107-109 need marking).

## Plan of work

### Stage A: unit tests

Create `src/falcon_correlate/unittests/test_req_context_integration.py` with a
`TestReqContextIntegration` class containing:

1. A parametrised test covering four scenarios that verify
   `req.context.correlation_id == correlation_id_var.get()`:
   - Generated ID (no incoming header): both return the same generated value.
   - Trusted incoming ID: both return the incoming header value.
   - Untrusted source: both return the same generated value (incoming
     rejected).
   - Validator rejects: both return the same generated value (incoming
     rejected).

2. A concurrent isolation test using `ThreadPoolExecutor` and `Barrier` that
   verifies two overlapping requests each observe matching
   `req.context.correlation_id` and `correlation_id_var.get()` for their own
   request.

Reuse the fixture patterns from `test_contextvar_lifecycle.py`:
`request_response_factory` (lines 22-43) and `isolated_context` (lines 46-53).

Validate: `make test` passes and new tests appear in output.

### Stage B: BDD tests

Create `tests/bdd/req_context_integration.feature` with three scenarios:

1. `req.context and contextvar return the same generated ID` — request without
   header, verify both values match and are non-empty.
2. `req.context and contextvar return the same trusted incoming ID` — request
   with trusted header, verify both return the incoming value.
3. `Dual access parity with concurrent requests` — two concurrent requests
   with distinct IDs, verify each response confirms parity.

Create `tests/bdd/test_req_context_integration_steps.py` with:

- A `_ReqContextParityResource` that returns `req.context.correlation_id`,
  `correlation_id_var.get()`, and a `parity` boolean in `resp.media`.
- Step definitions for the three scenarios.

Validate: `make test` passes and new BDD scenarios appear in output.

### Stage C: documentation

Update `docs/users-guide.md`:

- Add an "Accessing the correlation ID" section between "Context Variables"
  and "echo_header_in_response" documenting both methods, when to use each, and
  the parity guarantee, with code examples.
- Update the "Current Status" section to move task 2.4.3 from future to
  implemented.

Update `docs/falcon-correlation-id-middleware-design.md`:

- Append section A.4 recording the implementation decision for task 2.4.3.

Update `docs/roadmap.md`:

- Mark all 2.4.3 checkboxes `[x]`.

Validate: `make markdownlint` passes.

### Stage D: quality gates

Run all quality gates:

    set -o pipefail
    make check-fmt 2>&1 | tee /tmp/check-fmt.log
    make typecheck 2>&1 | tee /tmp/typecheck.log
    make lint 2>&1 | tee /tmp/lint.log
    make test 2>&1 | tee /tmp/test.log

Fix any failures and rerun until all pass.

## Concrete steps

1. Write this ExecPlan to
   `docs/execplans/2-4-3-integrate-with-req-context.md`.
2. Create unit test file and run `make test`.
3. Create BDD feature and step files, then run `make test`.
4. Update `docs/users-guide.md`, `docs/roadmap.md`, and design document.
5. Run `make fmt` to format all files.
6. Run all quality gates.
7. Update ExecPlan status to COMPLETE.

## Validation and acceptance

Functional acceptance:

- Unit tests prove dual-access parity across all correlation ID selection
  paths and concurrent requests.
- BDD tests prove parity from a user-facing perspective.
- Existing middleware, lifecycle, and context variable tests remain green.

Quality acceptance:

- `make check-fmt` exits 0.
- `make typecheck` exits 0.
- `make lint` exits 0.
- `make test` exits 0.

Documentation acceptance:

- `docs/users-guide.md` documents both access methods with guidance and
  examples.
- `docs/falcon-correlation-id-middleware-design.md` records appendix A.4.
- `docs/roadmap.md` shows task 2.4.3 complete.

## Idempotence and recovery

- Re-running tests is safe and deterministic.
- Documentation updates are idempotent: running `make fmt` multiple times
  produces the same output.
- If a quality gate fails, fix the issue and rerun from Stage D.

## Artifacts and notes

Expected new files:

- `docs/execplans/2-4-3-integrate-with-req-context.md`
- `src/falcon_correlate/unittests/test_req_context_integration.py`
- `tests/bdd/req_context_integration.feature`
- `tests/bdd/test_req_context_integration_steps.py`

Expected modified files:

- `docs/users-guide.md`
- `docs/falcon-correlation-id-middleware-design.md`
- `docs/roadmap.md`

No production code files are modified.

## Interfaces and dependencies

No new public interfaces are planned. No new dependencies are required.

The tests use existing fixtures and patterns from the project's test suite. The
documentation references existing public API exports (`correlation_id_var`,
`CorrelationIDMiddleware`, `req.context`).

## Revision note (required when editing an ExecPlan)

- 2026-02-21: Initial DRAFT created for roadmap item 2.4.3.
- 2026-02-21: Updated to COMPLETE after implementation, tests, and docs.
