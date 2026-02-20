# Implement context variable lifecycle (2.4.2)

This Execution Plan (ExecPlan) is a living document. The sections
`Constraints`, `Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`,
`Decision log`, and `Outcomes & retrospective` must be kept up to date as work
proceeds.

Status: DRAFT

## Purpose / big picture

Task 2.4.1 created and exported `correlation_id_var` and `user_id_var`, but the
middleware does not yet manage `correlation_id_var` during the request
lifecycle. Task 2.4.2 adds lifecycle management so request-scoped code can
reliably read `correlation_id_var.get()` during request handling and trust that
it is cleared after response processing.

Success is observable when:

- `process_request` sets `correlation_id_var` to the request's active
  correlation ID.
- The `contextvars.Token` returned by `.set()` is stored for deterministic
  cleanup.
- `process_response` resets `correlation_id_var` using the stored token.
- Cleanup occurs when request handling fails (`req_succeeded=False`) and no
  context leaks into subsequent requests.
- New unit tests (pytest) verify set/reset behaviour and isolation.
- New behavioural tests (`pytest-bdd`) verify request-time visibility,
  post-response cleanup, and concurrent request isolation.
- `docs/users-guide.md` documents the new lifecycle behaviour and removes the
  "future release" caveat for task 2.4.2.
- `docs/falcon-correlation-id-middleware-design.md` records implementation
  decisions for lifecycle token storage and cleanup semantics.
- `docs/roadmap.md` marks 2.4.2 complete only after all tests and quality gates
  pass.
- `make check-fmt`, `make typecheck`, `make lint`, and `make test` all pass.

## Constraints

- Follow TDD for this task: write or update tests first, verify failures, then
  implement, then verify pass.
- Do not change public constructor signatures or existing public exports.
- Do not add external dependencies.
- Keep `user_id_var` unchanged in this task; lifecycle management here is for
  `correlation_id_var` only.
- Preserve existing correlation ID selection semantics (trusted source +
  optional validator + generator fallback).
- Markdown changes must follow project documentation style (80-column wrapping,
  dash bullets).

## Tolerances (exception triggers)

- Scope: if implementation requires more than 10 files or 300 net lines
  changed, stop and escalate.
- Interface: if a public API signature must change, stop and escalate.
- Dependencies: if a new dependency is needed, stop and escalate.
- Behaviour: if lifecycle requirements conflict with existing accepted tests,
  stop and document options before proceeding.
- Iteration: if quality gates still fail after two fix iterations for the same
  root cause, stop and escalate with findings.

## Risks

- Risk: token storage location introduces concurrency bugs if shared across
  requests (e.g., middleware instance attribute).
  Severity: high. Likelihood: medium.
  Mitigation: store reset token on request-scoped state (`req.context`) instead
  of middleware instance state.

- Risk: `process_response` may run when request setup failed before token
  creation.
  Severity: medium. Likelihood: medium.
  Mitigation: treat token as optional and make cleanup idempotent/no-op when no
  token is present.

- Risk: tests can falsely pass if they only assert final response payload and
  not in-flight context state.
  Severity: medium. Likelihood: medium.
  Mitigation: add a dedicated Falcon test resource that reads
  `correlation_id_var.get()` inside `on_get` during request handling.

## Progress

- [x] (2026-02-20 09:23Z) Review roadmap, design doc §3.3.4, and current
  middleware/test state.
- [x] (2026-02-20 09:23Z) Draft ExecPlan for task 2.4.2.
- [ ] Add/modify unit tests for lifecycle behaviour (red phase).
- [ ] Add/modify behavioural tests for lifecycle behaviour (red phase).
- [ ] Implement lifecycle token set/reset in middleware (green phase).
- [ ] Update user-facing and design documentation.
- [ ] Mark roadmap task 2.4.2 complete.
- [ ] Run all quality gates and capture logs.

## Surprises & discoveries

- The current `process_response` method in
  `src/falcon_correlate/middleware.py` is a stub containing only a docstring,
  so this task supplies the first concrete response-phase behaviour.

- Existing context variable tests validate variable definition and basic
  `ContextVar` operations, but they do not yet exercise middleware lifecycle
  integration.

## Decision log

- Decision: store the token returned by `correlation_id_var.set(...)` on
  request-scoped context (for example,
  `req.context._correlation_id_reset_token`) instead of middleware instance
  state.
  Rationale: middleware instances are reused across requests and may execute
  concurrently; request-scoped token storage avoids cross-request races.
  Date/Author: 2026-02-20.

- Decision: make `process_response` cleanup unconditional with respect to
  `req_succeeded`; cleanup should run for both success and failure paths.
  Rationale: design-doc §3.3.4 requires end-of-request clearing to prevent
  leaks, and Falcon invokes `process_response` for middleware cleanup paths.
  Date/Author: 2026-02-20.

- Decision: verify concurrency isolation with behavioural tests that issue
  overlapping requests and assert per-request context values.
  Rationale: this is the closest user-visible proof that context lifecycle
  state is isolated and cleaned correctly.
  Date/Author: 2026-02-20.

## Outcomes & retrospective

Pending implementation.

## Context and orientation

`falcon-correlate` is a Falcon middleware library. `process_request` currently
selects a correlation ID and stores it on `req.context.correlation_id`.
`correlation_id_var` exists but is not currently set/reset by middleware.

### Key files

- `src/falcon_correlate/middleware.py` - lifecycle implementation point.
- `src/falcon_correlate/unittests/test_context_variables.py` - existing
  contextvar unit tests; candidate for extension.
- `src/falcon_correlate/unittests/test_middleware_falcon_integration.py` -
  middleware hook integration patterns.
- `tests/bdd/context_variables.feature` - existing contextvar BDD coverage.
- `tests/bdd/test_context_variables_steps.py` - existing contextvar step
  patterns.
- `tests/conftest.py` - shared Falcon test resources/middleware helpers.
- `docs/users-guide.md` - user-facing behaviour and API guidance.
- `docs/falcon-correlation-id-middleware-design.md` - decision record target.
- `docs/roadmap.md` - completion checklist target.

### Current implementation gap

- `process_request` chooses/stores `req.context.correlation_id` but does not
  call `correlation_id_var.set(...)`.
- No token is stored for context reset.
- `process_response` does not reset `correlation_id_var`.

## Plan of work

### Stage A: unit tests first (TDD red phase)

Add lifecycle-focused unit tests in a dedicated file
`src/falcon_correlate/unittests/test_contextvar_lifecycle.py`.

Planned assertions:

- After `process_request`, `correlation_id_var.get()` returns the same value as
  `req.context.correlation_id`.
- `process_request` stores a reset token in request-scoped context.
- After `process_response`, `correlation_id_var.get()` is `None`.
- `process_response` cleanup is safe when no token is present.
- Cleanup runs when `req_succeeded=False`.

Use `contextvars.copy_context().run(...)` where direct middleware invocation is
used to avoid cross-test leakage.

### Stage B: behavioural tests (pytest-bdd red phase)

Add `tests/bdd/contextvar_lifecycle.feature` and
`tests/bdd/test_contextvar_lifecycle_steps.py`.

Scenarios:

- `Context variable is set during request handling`:
  resource reads `correlation_id_var.get()` in `on_get`; value matches active
  request correlation ID.
- `Context variable is cleared after response`:
  after client request completes, out-of-request `correlation_id_var.get()` is
  `None`.
- `Context isolation across concurrent requests`:
  two overlapping requests with distinct incoming IDs each observe their own
  ID inside request handling and do not cross-contaminate.

### Stage C: implement middleware lifecycle (green phase)

In `src/falcon_correlate/middleware.py`:

- After establishing `req.context.correlation_id` in `process_request`, set
  `correlation_id_var` and store the returned token in request-scoped context.
- Implement `process_response` to:
  - optionally echo header behaviour only if currently implemented/required by
    existing tests (avoid scope expansion);
  - reset `correlation_id_var` via the stored token;
  - tolerate absent token without raising.
- Keep complexity low by extracting tiny helpers only if needed to avoid a
  bumpy-road method.

### Stage D: documentation updates

Update `docs/users-guide.md`:

- Replace "future release" language for task 2.4.2.
- Document that `correlation_id_var` is set for the duration of a request and
  automatically reset in `process_response`, including failure paths.
- Clarify that `user_id_var` lifecycle is still managed by authentication or
  application code.

Update `docs/falcon-correlation-id-middleware-design.md` appendix:

- Add an implementation decision entry for task 2.4.2 describing token storage
  location, cleanup semantics, and concurrency rationale.

Update `docs/roadmap.md`:

- Mark all 2.4.2 checkboxes complete after implementation and validation pass.

### Stage E: quality gates and evidence

Run (with `tee` and `set -o pipefail`) and keep logs in `/tmp`:

- `make check-fmt`
- `make typecheck`
- `make lint`
- `make test`

If any gate fails, fix and rerun until all pass.

## Concrete steps

1. Create/modify unit tests for lifecycle behaviour and run focused pytest to
   confirm red phase.
2. Create/modify BDD scenarios and steps for lifecycle behaviour and run
   focused `pytest -k contextvar_lifecycle` to confirm red phase.
3. Implement lifecycle code in middleware and rerun focused tests to green.
4. Run full quality gates.
5. Update docs (`users-guide`, design appendix, roadmap) and rerun markdown
   quality checks if needed.
6. Run full quality gates again to verify final state.

## Validation and acceptance

Functional acceptance:

- Unit tests prove set/token/reset behaviour, including failure cleanup.
- BDD tests prove in-request visibility, post-response clearing, and concurrent
  isolation.
- Existing middleware and context variable tests remain green.

Quality acceptance:

- `make check-fmt` exits 0.
- `make typecheck` exits 0.
- `make lint` exits 0.
- `make test` exits 0.

Documentation acceptance:

- `docs/users-guide.md` reflects new lifecycle behaviour and current caveats.
- `docs/falcon-correlation-id-middleware-design.md` records 2.4.2 decisions.
- `docs/roadmap.md` shows task 2.4.2 complete.

## Idempotence and recovery

- Re-running tests is safe and deterministic.
- If partial implementation leaves stale context, rerun from Stage A and use
  focused lifecycle tests to localise failures before full suite execution.
- If concurrency tests are flaky, tighten synchronisation primitives in test
  code (barriers/events) before changing production code.

## Artifacts and notes

Expected new files:

- `docs/execplans/2-4-2-contextvar-lifecycle.md`
- `src/falcon_correlate/unittests/test_contextvar_lifecycle.py`
- `tests/bdd/contextvar_lifecycle.feature`
- `tests/bdd/test_contextvar_lifecycle_steps.py`

Expected modified files:

- `src/falcon_correlate/middleware.py`
- `docs/users-guide.md`
- `docs/falcon-correlation-id-middleware-design.md`
- `docs/roadmap.md`

## Interfaces and dependencies

No new public interfaces are planned.

Internal additions (private/request-scoped):

- request-context storage for correlation contextvar reset token.

Dependencies remain unchanged.

## Revision note (required when editing an ExecPlan)

- 2026-02-20: Initial DRAFT created for roadmap item 2.4.2.
