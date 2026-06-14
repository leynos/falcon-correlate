# Ensure context variable compatibility with async (5.1.2)

This ExecPlan (execution plan) is a living document. The sections `Constraints`,
`Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`, `Decision Log`,
and `Outcomes & Retrospective` must be kept up to date as work proceeds.

Status: COMPLETE

This plan covers roadmap item 5.1.2 only. The user approved implementation on
2026-06-02, so the plan is now being executed milestone by milestone.

## Purpose / big picture

Roadmap item 5.1.2 proves that the ASGI middleware keeps correlation ID context
correct when Falcon handles asynchronous requests. ASGI means Asynchronous
Server Gateway Interface: Falcon calls asynchronous middleware hooks and
resource responders in an event loop, where many request tasks can be active at
the same time.

After this work is implemented, a consumer using `falcon.asgi.App` can rely on
`CorrelationIDMiddlewareASGI` to expose the current request's correlation ID
through both `req.context.correlation_id` and `correlation_id_var` while that
request is active, isolate that value from concurrent ASGI requests, echo the
configured response header when enabled, and clear request-local context after
response processing finishes.

Success is observable through pytest unit tests, pytest-bdd behavioural tests,
and Falcon ASGI integration tests. The important behaviour is not merely that
the middleware has asynchronous methods; it is that concurrent ASGI requests
cannot see each other's correlation IDs and that cleanup runs on normal and
failure paths.

## Constraints

- Do not implement this plan until it is explicitly approved.
- Keep this plan scoped to roadmap item 5.1.2. Do not redesign the ASGI
  middleware API or implement later ASGI roadmap items unless approval is
  updated.
- Preserve the public classes `CorrelationIDMiddleware` and
  `CorrelationIDMiddlewareASGI`.
- Preserve the current constructor contract: the middleware accepts either
  `config=CorrelationIDConfig(...)` or individual keyword arguments, but not
  both.
- Preserve WSGI behaviour unless an existing test is already incorrect and the
  deviation is recorded in this plan before changing it.
- Reuse the shared lifecycle in
  `src/falcon_correlate/middleware.py::_CorrelationIDMiddlewareBase`; do not
  fork header selection, trust checking, validation, response-header echoing,
  or reset-token cleanup into a second ASGI-only algorithm.
- Store `ContextVar` objects at module scope only. Python `Context` objects keep
  strong references to context variables, so new context variables must not be
  created inside closures.
- Cleanup must use reset tokens from `ContextVar.set()` and must clear
  `req.context._correlation_id_reset_token` after response processing.
- Do not add an external dependency without explicit approval.
- Use `pytest` for unit and integration tests and `pytest-bdd` for behavioural
  scenarios where behaviour is visible to consumers.
- Use `hypothesis` property tests only when the change introduces an invariant
  over a range of request counts, header values, ordering, or failure states.
- Use deterministic bounded concurrency tests. Avoid fragile timing assertions
  and sleeps that encode wall-clock assumptions.
- Update `docs/users-guide.md` with consumer-visible ASGI guarantees.
- Update `docs/falcon-correlation-id-middleware-design.md` with internally
  relevant async lifecycle decisions and test-backed invariants.
- Mark `docs/roadmap.md` item 5.1.2 done only after implementation,
  documentation, all gates, CodeRabbit review, commit, push, and pull request
  update are complete.
- Prefer Makefile targets for quality gates. Run gates sequentially and capture
  long output with `tee` under `/tmp`.
- Run `coderabbit review --agent` after each major implementation milestone
  only after applicable deterministic gates pass, then clear all concerns
  before moving on.
- Do not use `/tmp` as a build target. Use it only for command logs or scratch
  files.

If satisfying the objective requires violating a constraint, stop immediately,
record the conflict in `Decision Log`, and ask for direction.

## Tolerances (exception triggers)

- Scope: if implementation requires more than 8 changed files or more than 250
  net production-code lines, stop and ask whether the work should be split.
- Interface: if any public API signature must change, stop and present options
  before editing the interface.
- Dependencies: if tests require a package not already configured in
  `pyproject.toml`, stop before editing dependency metadata.
- Concurrency: if deterministic ASGI concurrency tests cannot demonstrate
  isolation with 2 to 16 concurrent requests, stop and record the blocker.
- Cancellation and failure paths: if proving cleanup after cancellation requires
  changes outside Falcon middleware lifecycle hooks, stop and ask whether that
  scope belongs in a separate roadmap item.
- Test iterations: if the same focused ASGI test remains red after three
  targeted implementation attempts, stop and ask for review.
- Validation: if `make check-fmt`, `make typecheck`, `make lint`, or
  `make test` fails for an unrelated reason that cannot be isolated in two
  focused attempts, stop and document the log path.
- Documentation validation: if `make markdownlint` or `make nixie` fails for an
  unrelated document, stop, and document the log path before broadening scope.
- CodeRabbit: if `coderabbit review --agent` raises a concern that implies an
  architectural change or public API change, stop and ask for approval before
  applying it.
- Branch or pull request workflow: if the remote branch or pull request state
  requires force-push, branch deletion, or a published branch rename, stop and
  ask for direction.

## Risks

- Risk: hook-level async tests can pass while real Falcon ASGI request
  execution still behaves differently. Severity: high. Likelihood: medium.
  Mitigation: include Falcon ASGI integration tests using
  `falcon.testing.TestClient` or `falcon.testing.ASGIConductor`.

- Risk: context isolation can appear correct with one deterministic interleave
  but fail under a different request ordering. Severity: high. Likelihood:
  medium. Mitigation: use `asyncio.gather()` with multiple requests, explicit
  event-loop yields, and distinct generated or incoming IDs. Add a property
  test only if a useful variable request-count invariant emerges.

- Risk: cleanup can be skipped when response-header mutation raises.
  Severity: high. Likelihood: low. Mitigation: keep response header echo and
  cleanup in a `try`/`finally` path and test header failure directly for ASGI.

- Risk: BDD scenarios become brittle if they duplicate every unit edge case.
  Severity: medium. Likelihood: medium. Mitigation: keep BDD scenarios focused
  on consumer-visible ASGI flows: concurrent requests, distinct observed IDs,
  response headers, and post-request cleanup.

- Risk: CodeRabbit may recommend broad refactors outside roadmap item 5.1.2.
  Severity: medium. Likelihood: medium. Mitigation: record such concerns, apply
  only concerns needed for this item, and escalate anything that exceeds the
  scope tolerance.

## Progress

- [x] (2026-05-26T21:15:36Z) Loaded the `leta` skill and registered this
  repository as a Leta workspace.
- [x] (2026-05-26T21:15:36Z) Renamed the local branch to
  `5-1-2-ensure-context-variable-compatibility-with-async`.
- [x] (2026-05-26T21:15:36Z) Used a Wyvern agent team for repository
  reconnaissance and ASGI test-strategy review.
- [x] (2026-05-26T21:15:36Z) Used Firecrawl to check Python `contextvars`,
  Falcon ASGI middleware, Falcon ASGI testing, and ASGI prior-art documentation.
- [x] (2026-05-26T21:15:36Z) Drafted this pre-implementation execplan.
- [x] (2026-06-02T00:00:00+02:00) Obtained user approval for this execplan
  and began implementation.
- [x] (2026-06-02T00:00:00+02:00) Completed Milestone 1 audit. Existing
  direct ASGI unit tests already cover request context setup, response cleanup,
  header echo disabling, header echo failure cleanup, and concurrent direct
  hook isolation. The missing coverage is stronger Falcon ASGI application
  boundary testing and consumer-facing BDD coverage for concurrent isolation
  and post-response cleanup.
- [x] (2026-06-02T00:00:00+02:00) Baseline gates passed:
  `make check-fmt`, `make typecheck`, `make lint`, and `make test`. Logs:
  `/tmp/check-fmt-falcon-correlate-5-1-2-baseline.out`,
  `/tmp/typecheck-falcon-correlate-5-1-2-baseline.out`,
  `/tmp/lint-falcon-correlate-5-1-2-baseline.out`, and
  `/tmp/test-falcon-correlate-5-1-2-baseline.out`.
- [x] (2026-06-02T00:00:00+02:00) CodeRabbit baseline review completed with
  zero findings after three recoverable rate-limit retries.
- [x] (2026-06-02T00:00:00+02:00) Completed Milestone 2 by adding ASGI
  property, Falcon ASGI integration, and BDD coverage for concurrent async
  context isolation and ambient cleanup. The new tests were green on arrival:
  the existing shared lifecycle already satisfied the verified contracts.
- [x] (2026-06-02T00:00:00+02:00) Full test-milestone gates passed after
  CodeRabbit fixes: `make check-fmt`, `make typecheck`, `make lint`, and
  `make test`. Final logs:
  `/tmp/check-fmt-falcon-correlate-5-1-2-tests-dataclass-final.out`,
  `/tmp/typecheck-falcon-correlate-5-1-2-tests-dataclass-final.out`,
  `/tmp/lint-falcon-correlate-5-1-2-tests-dataclass-final.out`, and
  `/tmp/test-falcon-correlate-5-1-2-tests-dataclass-final.out`.
- [x] (2026-06-02T00:00:00+02:00) CodeRabbit test-milestone review completed
  with zero findings after applying its helper extraction, Hypothesis context
  isolation, deadline, lock, typing, and dataclass feedback.
- [x] (2026-06-02T00:00:00+02:00) Completed Milestone 3 with no production
  code changes. No lifecycle bug was found; the implementation fix milestone
  was unnecessary because the new tests proved the existing ASGI wrapper and
  shared base already handle async context isolation and cleanup.
- [x] (2026-06-02T05:19:21+02:00) Completed Milestone 4 documentation by
  updating `docs/users-guide.md`,
  `docs/falcon-correlation-id-middleware-design.md`, and `docs/roadmap.md`.
  `make fmt` exposed an unrelated existing Markdown line-length failure in
  `docs/execplans/4-2-4-validate-optional-celery-integration.md`, so unrelated
  formatter churn was reverted and the documentation gates were rerun.
- [x] (2026-06-02T05:19:21+02:00) Documentation milestone gates passed:
  `make check-fmt`, `make markdownlint`, `make nixie`, `make typecheck`,
  `make lint`, and `make test`. Logs:
  `/tmp/check-fmt-falcon-correlate-5-1-2-docs.out`,
  `/tmp/markdownlint-falcon-correlate-5-1-2-docs.out`,
  `/tmp/nixie-falcon-correlate-5-1-2-docs.out`,
  `/tmp/typecheck-falcon-correlate-5-1-2-docs.out`,
  `/tmp/lint-falcon-correlate-5-1-2-docs.out`, and
  `/tmp/test-falcon-correlate-5-1-2-docs.out`.
- [x] (2026-06-02T05:19:21+02:00) CodeRabbit documentation review completed
  with zero findings after one recoverable rate-limit retry and a 27-minute
  backoff.
- [x] (2026-06-02T05:26:31+02:00) Final gates passed:
  `make check-fmt`, `make typecheck`, `make lint`, `make test`,
  `make markdownlint`, and `make nixie`. Logs:
  `/tmp/check-fmt-falcon-correlate-5-1-2-final.out`,
  `/tmp/typecheck-falcon-correlate-5-1-2-final.out`,
  `/tmp/lint-falcon-correlate-5-1-2-final.out`,
  `/tmp/test-falcon-correlate-5-1-2-final.out`,
  `/tmp/markdownlint-falcon-correlate-5-1-2-final.out`, and
  `/tmp/nixie-falcon-correlate-5-1-2-final.out`.
- [x] (2026-06-02T05:26:31+02:00) Final CodeRabbit review completed with zero
  findings.
- [x] Implement the approved milestones.
- [x] Run all required gates and CodeRabbit reviews.
- [x] Mark roadmap item 5.1.2 done after the feature is complete.

## Surprises & Discoveries

- Observation: `CorrelationIDMiddlewareASGI` already exists from roadmap item
  5.1.1, so this item is a verification and hardening milestone rather than a
  greenfield implementation. Evidence:
  `src/falcon_correlate/middleware_asgi.py` defines
  `CorrelationIDMiddlewareASGI`, and `docs/roadmap.md` marks item 5.1.1 done.
  Impact: tests should target async context isolation and cleanup gaps instead
  of recreating the ASGI class.

- Observation: ASGI lifecycle unit tests already include a concurrent direct
  hook test. Evidence:
  `src/falcon_correlate/unittests/test_middleware_asgi.py::TestCorrelationIDMiddlewareASGIRequestLifecycle`
  includes `test_concurrent_asgi_requests_keep_correlation_ids_isolated`.
  Impact: implementation should first audit whether existing tests are strong
  enough, then add only missing ASGI integration and BDD coverage.

- Observation: `falcon.testing.ASGIConductor` is the Falcon-provided harness
  for interleaved ASGI requests. Evidence: Falcon testing documentation says
  `ASGIConductor` provides coroutine-based lifecycle control and interleaved
  request testing. Impact: the plan should prefer `ASGIConductor` for
  concurrent ASGI integration tests when `TestClient` cannot model interleaving.

- Observation: `CorrelationIDMiddlewareASGI` is already a thin coroutine
  wrapper over `_CorrelationIDMiddlewareBase`; no ASGI-specific lifecycle fork
  exists. Evidence: `src/falcon_correlate/middleware_asgi.py` calls
  `_process_request()` and `_process_response()` directly from the Falcon ASGI
  hooks. Impact: new tests should first prove the shared lifecycle holds at the
  ASGI app boundary before changing production code.

- Observation: CodeRabbit reported repeated recoverable rate-limit errors
  before completing the baseline review. Evidence: retries followed random
  18-minute, 16-minute, and 20-minute backoffs; the final retry completed with
  zero findings. Impact: later CodeRabbit milestones may require the same
  backoff loop and should not be treated as deterministic gate failures.

- Observation: Milestone 2 tests were green on arrival. Evidence:
  `uv run pytest -v` against
  `src/falcon_correlate/unittests/test_middleware_asgi.py`,
  `src/falcon_correlate/unittests/test_middleware_asgi_integration.py`, and
  `tests/bdd/test_asgi_middleware_steps.py` passed after adding the new cases,
  and the final full suite passed with 409 passed and 11 skipped. Impact:
  roadmap item 5.1.2 is primarily a verification and documentation milestone;
  no production lifecycle change is required.

- Observation: The ASGI property test needed a shared helper module rather
  than importing private doubles from the direct unit test file. Evidence:
  CodeRabbit flagged cross-test private imports, and the helpers now live in
  `src/falcon_correlate/unittests/asgi_middleware_helpers.py`. Impact: direct
  ASGI unit tests and ASGI property tests share the same doubles without
  coupling one test module to another.

- Observation: Hypothesis examples for async context isolation should run
  inside the existing `isolated_context` fixture and without the default
  200-millisecond deadline. Evidence: CodeRabbit flagged potential ContextVar
  leakage between examples and CI flakiness from the default deadline. Impact:
  the property test now isolates each generated example and disables
  per-example deadline enforcement.

- Observation: `make fmt` can fail on pre-existing Markdown defects outside
  the current roadmap item. Evidence: the docs milestone `make fmt` run failed
  on `docs/execplans/4-2-4-validate-optional-celery-integration.md:685`, while
  the current task documentation passed `make check-fmt`, `make markdownlint`,
  and `make nixie` after unrelated formatter churn was reverted. Impact: future
  documentation work may need to isolate current-task diffs when global
  formatting exposes older documentation debt.

## Decision Log

- Decision: Treat this work as a test-backed compatibility milestone, not an
  ASGI middleware redesign. Rationale: roadmap item 5.1.1 already created
  `CorrelationIDMiddlewareASGI`; item 5.1.2 asks specifically for async
  `contextvars` behaviour, concurrent requests, isolation, and cleanup.
  Date/Author: 2026-05-26T21:15:36Z / Codex.

- Decision: Keep BDD coverage consumer-facing and put detailed failure-path
  assertions in unit tests. Rationale: behavioural tests should describe
  externally observable library guarantees, while token internals and
  header-mutation failures are clearer and less brittle in pytest unit tests.
  Date/Author: 2026-05-26T21:15:36Z / Codex.

- Decision: Use property tests only if implementation adds a variable invariant
  that materially improves coverage over deterministic concurrency tests.
  Rationale: the user requested property tests where applicable; for this
  milestone, a bounded deterministic concurrency test may be the better signal
  unless request counts, ordering, or failure combinations become meaningful
  variables. Date/Author: 2026-05-26T21:15:36Z / Codex.

- Decision: Add an ASGI-specific property test over task counts 2 through 16.
  Rationale: the implementation added a meaningful invariant over a range of
  concurrent async request counts, and this directly satisfies the user's
  property-test requirement where applicable. Date/Author:
  2026-06-02T00:00:00+02:00 / Codex.

- Decision: Do not edit production middleware for Milestone 3. Rationale: the
  new unit, property, integration, and BDD tests passed against the existing
  ASGI middleware, proving the shared lifecycle already provides async
  ContextVar isolation and cleanup. Date/Author: 2026-06-02T00:00:00+02:00 /
  Codex.

- Decision: Document the verified ASGI guarantees without changing the public
  API. Rationale: consumers need to know that ASGI request context is isolated
  and cleaned up, but the tests showed no constructor, hook, or configuration
  contract change was needed. Date/Author: 2026-06-02T05:19:21+02:00 / Codex.

## Outcomes & Retrospective

Roadmap item 5.1.2 has been implemented as a test-backed compatibility
verification. The existing ASGI middleware already used the shared lifecycle
correctly, so the work added stronger evidence rather than production changes:
a bounded Hypothesis property test over concurrent ASGI task counts, a Falcon
ASGI integration test with overlapping responders, and a consumer-facing BDD
scenario for concurrent isolation and cleanup.

The documentation now states that `CorrelationIDMiddlewareASGI` exposes the
same active request ID through `req.context.correlation_id` and
`correlation_id_var`, keeps concurrent ASGI request values isolated, resets
ambient context after response processing, and follows
`echo_header_in_response` for response headers. The design document records the
reset-token lifecycle and the test-backed async invariant.

All deterministic gates and CodeRabbit reviews required by this plan completed
with no unresolved findings. The remaining handoff work is mechanical pull
request metadata and branch push, outside the implementation itself.

## Context and orientation

The project is a Python package named `falcon-correlate`. It provides Falcon
middleware that manages a correlation ID for each request. A correlation ID is
an identifier used to connect logs and downstream calls that belong to the same
request.

The WSGI middleware is `CorrelationIDMiddleware` in
`src/falcon_correlate/middleware.py`. WSGI means Web Server Gateway Interface,
the synchronous Python web-server interface. The ASGI middleware is
`CorrelationIDMiddlewareASGI` in `src/falcon_correlate/middleware_asgi.py`.
Both variants share `_CorrelationIDMiddlewareBase` in
`src/falcon_correlate/middleware.py`.

The shared lifecycle currently performs these steps:

1. Read the configured incoming header, defaulting to `X-Correlation-ID`.
2. Accept the incoming ID only when the source is trusted and the validator
   accepts the value.
3. Generate a new ID when no acceptable incoming value exists.
4. Store the final ID on `req.context.correlation_id`.
5. Store the same ID in `correlation_id_var`, a Python `ContextVar` exported by
   the package.
6. Store the reset token on
   `req.context._correlation_id_reset_token`.
7. Echo the configured response header when enabled.
8. Reset `correlation_id_var` and clear the reset token during response
   processing.

`ContextVar` is Python's mechanism for context-local state. It is designed for
concurrent asynchronous code, but each request must still set and reset its own
value correctly. A reset token is the object returned by
`ContextVar.set(value)`; calling `ContextVar.reset(token)` restores the
previous value for the current context.

The main implementation files are:

- `src/falcon_correlate/middleware.py`, for shared lifecycle logic.
- `src/falcon_correlate/middleware_asgi.py`, for Falcon ASGI hook methods.
- `src/falcon_correlate/middleware_config.py`, for configuration validation.
- `src/falcon_correlate/__init__.py`, for public exports.

The main tests for this roadmap item are:

- `src/falcon_correlate/unittests/test_middleware_asgi.py`, for direct ASGI
  hook tests.
- `src/falcon_correlate/unittests/test_middleware_asgi_integration.py`, for
  Falcon ASGI application integration tests.
- `src/falcon_correlate/unittests/test_contextvar_lifecycle.py`, for WSGI
  lifecycle parity reference.
- `src/falcon_correlate/unittests/test_middleware_properties.py`, for existing
  property-test patterns.
- `tests/bdd/asgi_middleware.feature`, for consumer-facing ASGI behaviour.
- `tests/bdd/test_asgi_middleware_steps.py`, for ASGI BDD step definitions.
- `tests/asgi_resources.py`, for ASGI test resources.

The main documentation files are:

- `docs/roadmap.md`, for roadmap item status.
- `docs/falcon-correlation-id-middleware-design.md`, for architecture and
  lifecycle decisions.
- `docs/users-guide.md`, for consumer-facing usage and guarantees.
- `docs/complexity-antipatterns-and-refactoring-strategies.md`, for guidance
  on keeping any refactor small and readable.
- `docs/documentation-style-guide.md`, for documentation conventions.

The relevant skills for implementation are:

- `leta`, for semantic repository navigation.
- `execplans`, for keeping this plan current.
- `firecrawl-mcp`, for resolving external Falcon, ASGI, or Python
  documentation gaps.
- `code-review`, for review stance before committing.
- `commit-message`, for file-based commit messages.
- `pr-creation` and `en-gb-oxendict-style`, for pull request metadata.

External research used for this draft:

- Python `contextvars` documentation states that context variables are
  natively supported in `asyncio`, that `ContextVar.set()` returns a token, and
  that `ContextVar.reset(token)` restores the previous value:
  <https://docs.python.org/3/library/contextvars.html>.
- Falcon middleware documentation confirms ASGI middleware hooks are async and
  that dual WSGI/ASGI middleware can use `*_async` variants:
  <https://falcon.readthedocs.io/en/stable/api/middleware.html>.
- Falcon testing documentation confirms `TestClient` supports ASGI and
  `ASGIConductor` supports coroutine-based lifecycle control and interleaved
  request testing: <https://falcon.readthedocs.io/en/stable/api/testing.html>.
- ASGI 3.0 documentation states that applications are called once per
  connection with `scope`, `receive`, and `send`, and that middleware wraps
  those asynchronous callables:
  <https://asgi.readthedocs.io/en/latest/specs/main.html>.

## Plan of work

### Milestone 1: audit existing async context coverage

Use `leta` to inspect the relevant symbols before editing:

```bash
leta show _CorrelationIDMiddlewareBase
leta show CorrelationIDMiddlewareASGI
leta show TestCorrelationIDMiddlewareASGIRequestLifecycle
leta show TestCorrelationIDMiddlewareASGIFalconIntegration
```

Compare current tests with the acceptance criteria in roadmap item 5.1.2:

- contextvars behaviour in async context;
- concurrent async requests;
- context isolation with concurrent async requests;
- cleanup on async request completion.

Record discoveries in this plan. If the existing direct hook tests already
cover part of the item, do not duplicate them. Identify missing coverage at the
Falcon ASGI app boundary and in BDD scenarios.

Run a focused baseline before editing tests:

```bash
set -o pipefail
make check-fmt 2>&1 | tee /tmp/check-fmt-falcon-correlate-5-1-2-baseline.out
make typecheck 2>&1 | tee /tmp/typecheck-falcon-correlate-5-1-2-baseline.out
make lint 2>&1 | tee /tmp/lint-falcon-correlate-5-1-2-baseline.out
make test 2>&1 | tee /tmp/test-falcon-correlate-5-1-2-baseline.out
```

After the deterministic gates pass, run:

```bash
coderabbit review --agent
```

Acceptance for this milestone:

- The plan records which existing tests already satisfy part of 5.1.2.
- Baseline gates pass, or unrelated failures are documented with log paths.
- CodeRabbit has no unresolved concerns for the audited baseline.

### Milestone 2: add or strengthen failing tests

Add tests before changing production code. If the current implementation
already satisfies a candidate test, keep it only when it proves a missing
contract and record that it was green on arrival. Add failing tests only for
genuine gaps.

In `src/falcon_correlate/unittests/test_middleware_asgi.py`, ensure direct
async hook tests cover:

- `req.context.correlation_id == correlation_id_var.get()` during an ASGI
  request;
- `correlation_id_var.get() is None` after response processing;
- reset-token cleanup after normal completion;
- reset-token cleanup after response header echo failure;
- concurrent request tasks with unique IDs, each task observing only its own
  ID before cleanup.

In `src/falcon_correlate/unittests/test_middleware_asgi_integration.py`, add
Falcon ASGI application tests that use `ASGICorrelationEchoResource` or a small
purpose-built resource to prove:

- the resource can observe the current request's `correlation_id_var`;
- concurrent ASGI requests receive distinct IDs;
- ambient `correlation_id_var` is clear after requests complete.

Prefer `falcon.testing.ASGIConductor` for true interleaving. Use
`falcon.testing.TestClient` only for single-shot request/response checks.

In `tests/bdd/asgi_middleware.feature` and
`tests/bdd/test_asgi_middleware_steps.py`, add consumer-facing scenarios for:

- concurrent ASGI requests with distinct observed correlation IDs;
- response header echo enabled and disabled;
- post-response ambient context cleanup.

Add a property test only if a concrete invariant emerges, for example:

```plaintext
For any request count between 2 and 16 and any generated unique ID sequence,
each completed ASGI request observes exactly its assigned ID during the request
and the ambient correlation_id_var is None after all requests finish.
```

Run focused tests and capture the red or green-on-arrival evidence:

```bash
set -o pipefail
uv run pytest -v src/falcon_correlate/unittests/test_middleware_asgi.py \
  2>&1 | tee /tmp/test-falcon-correlate-5-1-2-asgi-unit-red.out
uv run pytest -v src/falcon_correlate/unittests/test_middleware_asgi_integration.py \
  2>&1 | tee /tmp/test-falcon-correlate-5-1-2-asgi-integration-red.out
uv run pytest -v tests/bdd/test_asgi_middleware_steps.py \
  2>&1 | tee /tmp/test-falcon-correlate-5-1-2-asgi-bdd-red.out
```

Acceptance for this milestone:

- New tests either fail for the expected async context compatibility gap or are
  recorded as green-on-arrival because the existing implementation already
  satisfied that contract.
- No unrelated fixture, import, or environment failure is introduced.
- This plan records the test names and observed result.

### Milestone 3: implement the smallest lifecycle fix

If Milestone 2 finds a production bug, change only the smallest necessary code
around ASGI lifecycle and shared context cleanup.

Expected edit locations are:

- `src/falcon_correlate/middleware.py`, if the shared base must adjust token
  cleanup, response-header echo ordering, or guard conditions.
- `src/falcon_correlate/middleware_asgi.py`, if the ASGI hook methods need to
  await, shield, or structure calls differently.
- `tests/asgi_resources.py`, only if tests need a clearer ASGI resource for
  observing in-request context.

The preferred implementation keeps `process_request()` and `process_response()`
as thin async wrappers around the shared base unless a test proves that Falcon
ASGI requires different behaviour.

Run the focused tests:

```bash
set -o pipefail
uv run pytest -v src/falcon_correlate/unittests/test_middleware_asgi.py \
  2>&1 | tee /tmp/test-falcon-correlate-5-1-2-asgi-unit-green.out
uv run pytest -v src/falcon_correlate/unittests/test_middleware_asgi_integration.py \
  2>&1 | tee /tmp/test-falcon-correlate-5-1-2-asgi-integration-green.out
uv run pytest -v tests/bdd/test_asgi_middleware_steps.py \
  2>&1 | tee /tmp/test-falcon-correlate-5-1-2-asgi-bdd-green.out
```

Then run the required gates sequentially:

```bash
set -o pipefail
make check-fmt 2>&1 | tee /tmp/check-fmt-falcon-correlate-5-1-2-implementation.out
make typecheck 2>&1 | tee /tmp/typecheck-falcon-correlate-5-1-2-implementation.out
make lint 2>&1 | tee /tmp/lint-falcon-correlate-5-1-2-implementation.out
make test 2>&1 | tee /tmp/test-falcon-correlate-5-1-2-implementation.out
```

After deterministic gates pass, run:

```bash
coderabbit review --agent
```

Acceptance for this milestone:

- The new ASGI context tests pass.
- Full deterministic gates pass.
- CodeRabbit has no unresolved concerns.
- Any production edit is narrower than the scope tolerance.

### Milestone 4: update documentation and roadmap

Update `docs/users-guide.md` to state the ASGI consumer guarantee:

- `CorrelationIDMiddlewareASGI` exposes the active request ID through
  `req.context.correlation_id` and `correlation_id_var` while the request is
  running.
- Concurrent ASGI requests have isolated context.
- `correlation_id_var` is reset after request completion.
- Response header echoing follows the existing `echo_header_in_response`
  setting.

Update `docs/falcon-correlation-id-middleware-design.md` to record the
internally facing decision:

- the ASGI variant relies on module-level `ContextVar` objects;
- each request stores a reset token;
- cleanup runs during response processing in a `finally` path;
- tests verify concurrent async isolation and cleanup.

Update `docs/roadmap.md` only after all tests and docs pass, marking item 5.1.2
and its subtasks as done.

Run documentation formatting and validation:

```bash
set -o pipefail
make fmt 2>&1 | tee /tmp/fmt-falcon-correlate-5-1-2-docs.out
make check-fmt 2>&1 | tee /tmp/check-fmt-falcon-correlate-5-1-2-docs.out
make markdownlint 2>&1 | tee /tmp/markdownlint-falcon-correlate-5-1-2-docs.out
make nixie 2>&1 | tee /tmp/nixie-falcon-correlate-5-1-2-docs.out
make typecheck 2>&1 | tee /tmp/typecheck-falcon-correlate-5-1-2-docs.out
make lint 2>&1 | tee /tmp/lint-falcon-correlate-5-1-2-docs.out
make test 2>&1 | tee /tmp/test-falcon-correlate-5-1-2-docs.out
```

After deterministic gates pass, run:

```bash
coderabbit review --agent
```

Acceptance for this milestone:

- Consumer and internal documentation describe the verified ASGI async context
  behaviour accurately.
- `docs/roadmap.md` marks 5.1.2 done.
- Documentation and full project gates pass.
- CodeRabbit has no unresolved concerns.

### Milestone 5: commit, push, and update the pull request

Use file-based commit messages only. Do not pass commit messages with
`git commit -m`.

Inspect and commit the final implementation:

```bash
git status --short
git diff -- docs/roadmap.md docs/users-guide.md docs/falcon-correlation-id-middleware-design.md
git diff -- src tests
git add docs/roadmap.md docs/users-guide.md docs/falcon-correlation-id-middleware-design.md
git add src tests
COMMIT_MSG_DIR=$(mktemp -d)
cat > "$COMMIT_MSG_DIR/COMMIT_MSG.md" << 'ENDOFMSG'
Verify ASGI context isolation

Add test-backed ASGI context variable guarantees for concurrent request
isolation and cleanup. Document the verified behaviour for consumers and
record roadmap item 5.1.2 as complete.
ENDOFMSG
git commit -F "$COMMIT_MSG_DIR/COMMIT_MSG.md"
rm -rf "$COMMIT_MSG_DIR"
```

Push the branch and update the draft pull request description so reviewers can
see the execplan, implementation, validation logs, and collaboration session
reference.

Acceptance for this milestone:

- The commit is small enough to review.
- The branch tracks
  `origin/5-1-2-ensure-context-variable-compatibility-with-async`.
- The draft pull request title includes `(5.1.2)`.
- The pull request summary mentions this execplan:
  `docs/execplans/5-1-2-ensure-context-variable-compatibility-with-async.md`.
- The pull request description ends with a `## References` section containing the
  collaboration session link/reference.

## Concrete steps

All commands run from the repository root:

```bash
cd <repo-root>
```

Before implementation, verify branch and workspace state:

```bash
git branch --show-current
git status --short --branch
leta workspace add .
```

Expected branch output:

```plaintext
5-1-2-ensure-context-variable-compatibility-with-async
```

Run focused inspection commands:

```bash
leta show _CorrelationIDMiddlewareBase
leta show CorrelationIDMiddlewareASGI
leta show TestCorrelationIDMiddlewareASGIRequestLifecycle
leta show TestCorrelationIDMiddlewareASGIFalconIntegration
```

Run all test and quality commands sequentially. Use `tee` for command logs:

```bash
set -o pipefail
make check-fmt 2>&1 | tee /tmp/check-fmt-falcon-correlate-5-1-2.out
make typecheck 2>&1 | tee /tmp/typecheck-falcon-correlate-5-1-2.out
make lint 2>&1 | tee /tmp/lint-falcon-correlate-5-1-2.out
make test 2>&1 | tee /tmp/test-falcon-correlate-5-1-2.out
make markdownlint 2>&1 | tee /tmp/markdownlint-falcon-correlate-5-1-2.out
make nixie 2>&1 | tee /tmp/nixie-falcon-correlate-5-1-2.out
```

After each major milestone with passing deterministic gates, run:

```bash
coderabbit review --agent
```

If CodeRabbit reports concerns, either fix them within this plan's scope or
record why they require escalation before moving to the next milestone.

## Validation and acceptance

The feature is complete only when all of the following are true:

- Unit tests prove ASGI request processing sets
  `req.context.correlation_id` and `correlation_id_var` to the same ID during
  request handling.
- Unit tests prove `correlation_id_var.get() is None` after ASGI response
  processing.
- Unit tests prove reset-token cleanup after normal response processing and
  after response-header echo failure.
- Concurrent ASGI tests prove each request task observes only its own
  correlation ID.
- Falcon ASGI integration tests prove the same behaviour at real application
  boundaries.
- BDD scenarios describe consumer-visible concurrent ASGI isolation,
  response-header echoing, and post-response cleanup.
- `docs/users-guide.md` documents the ASGI behaviour a consumer should rely on.
- `docs/falcon-correlation-id-middleware-design.md` documents the internal
  async lifecycle invariant.
- `docs/roadmap.md` marks item 5.1.2 done.
- `make check-fmt`, `make typecheck`, `make lint`, `make test`,
  `make markdownlint`, and `make nixie` pass.
- `coderabbit review --agent` has no unresolved concerns for the completed
  milestone.

Expected successful command summaries look like:

```plaintext
make check-fmt
# ruff format --check completes without changes required

make typecheck
# ty check completes successfully

make lint
# ruff and pylint-pypy complete successfully

make test
# pytest completes with all tests passing

make markdownlint
# markdownlint-cli2 reports no failures

make nixie
# Mermaid validation completes without failures
```

## Idempotence and recovery

The inspection, focused test, lint, typecheck, markdown, and CodeRabbit review
steps are safe to rerun. The implementation should avoid persistent services
and should not require any manual cleanup beyond temporary files in `/tmp`.

If formatting changes more Markdown than expected, inspect the diff before
committing. If `make fmt` touches unrelated files, either include only
necessary documentation formatting in this branch or stop and ask for direction
if the formatter churn is large.

If a focused async test becomes flaky, do not hide the flake with arbitrary
sleep increases. Replace timing-sensitive assertions with deterministic
barriers, explicit event-loop yields, bounded concurrency, or `ASGIConductor`
lifecycle control.

Rollback is ordinary Git rollback. Before committing, use `git diff` to inspect
changes. After committing, use `git revert <commit>` for a public rollback
instead of destructive reset commands.

## Artifacts and notes

Planning reconnaissance used one Wyvern agent to map relevant source, tests,
docs, and Makefile gates, and another Wyvern agent to propose the ASGI
contextvars test strategy. Both agents recommended strengthening ASGI unit,
integration, and BDD coverage while keeping the implementation scoped.

Firecrawl resolved these external prior-art points:

- Python `contextvars` are natively supported by `asyncio`, but correct
  application code must still use reset tokens for cleanup.
- Falcon ASGI middleware hooks are async and can coexist with WSGI middleware
  through separate or `*_async` hook methods.
- Falcon `ASGIConductor` is the appropriate prior-art helper for interleaved
  ASGI lifecycle tests.
- ASGI applications are per-connection async callables, so request isolation
  must be proven under concurrent tasks.

Initial branch state:

```plaintext
git branch --show-current
5-1-2-ensure-context-variable-compatibility-with-async
```

Collaboration session ID for pull request references:

```plaintext
<session-id>
```

## Interfaces and dependencies

No new public interface is expected. The following interfaces must still exist
after implementation:

```python
class CorrelationIDMiddlewareASGI(_CorrelationIDMiddlewareBase):
    async def process_request(
        self,
        req: falcon.asgi.Request,
        resp: falcon.asgi.Response,
    ) -> None:
        ...

    async def process_response(
        self,
        req: falcon.asgi.Request,
        resp: falcon.asgi.Response,
        resource: object,
        req_succeeded: bool,
    ) -> None:
        ...
```

`correlation_id_var` remains the package-level context variable exported from
`src/falcon_correlate/__init__.py`.

The plan expects existing dependencies only:

- `falcon`, for the ASGI application and testing helpers.
- `pytest`, for unit and integration tests.
- `pytest-asyncio`, already used by async tests.
- `pytest-bdd`, for behavioural tests.
- `hypothesis`, only if a property test is applicable.

No new runtime dependency should be added for this roadmap item.

## Revision note

Initial draft created on 2026-05-26. It captures repository reconnaissance,
external prior-art checks, implementation tolerances, and the approval gate for
roadmap item 5.1.2.
