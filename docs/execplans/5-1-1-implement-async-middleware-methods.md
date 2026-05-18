# Implement async middleware methods (5.1.1)

This Execution Plan (ExecPlan) is a living document. The sections
`Constraints`, `Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`,
`Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work
proceeds.

Status: DRAFT

This draft covers the remaining ASGI middleware implementation. The branch
already contains prerequisite WSGI response-header parity commits discovered
during earlier planning and review. Those historical commits are recorded
below, but no ASGI middleware implementation may begin until this draft is
approved.

## Purpose / big picture

Roadmap item 5.1.1 adds Falcon Asynchronous Server Gateway Interface (ASGI)
support to `falcon-correlate`. After the change is implemented, a consumer
using `falcon.asgi.App` can install `CorrelationIDMiddlewareASGI` and receive
the same request correlation behaviour that Web Server Gateway Interface
(WSGI) consumers receive from `CorrelationIDMiddleware`.

Success is observable when an ASGI Falcon application can accept a request,
create or accept a correlation ID according to the configured trust and
validation rules, expose that ID through `req.context.correlation_id` and
`correlation_id_var`, echo the response header when configured, and clear
request-local state after response processing. The WSGI middleware must keep
its existing public behaviour while sharing the same configuration and
lifecycle rules.

## Context and orientation

The existing WSGI implementation lives in `src/falcon_correlate/middleware.py`.
`CorrelationIDMiddleware` owns the public constructor, the configuration
properties, header retrieval, trust checks, validator calls, request context
storage, response-header echoing, and `contextvars` cleanup. The immutable
`CorrelationIDConfig` dataclass in
`src/falcon_correlate/middleware_config.py` already validates
`header_name`, `trusted_sources`, `generator`, `validator`, and
`echo_header_in_response`.

The ASGI class must be a separate public class named
`CorrelationIDMiddlewareASGI`. It should not copy a second correlation
algorithm. The implementation should extract a shared private lifecycle layer
that both WSGI and ASGI middleware call from thin framework hook methods. The
shared layer should cover incoming header trimming, trust and validation
selection, request context storage, response-header echoing, and reset-token
cleanup.

The package root, `src/falcon_correlate/__init__.py`, is the public export
surface. ASGI support must add the class there and update
`src/falcon_correlate/unittests/test_public_exports.py`.

The main WSGI test references are:

- `src/falcon_correlate/unittests/test_middleware_configuration.py`
- `src/falcon_correlate/unittests/test_middleware_falcon_integration.py`
- `src/falcon_correlate/unittests/test_middleware_header_handling.py`
- `src/falcon_correlate/unittests/test_middleware_response_header.py`
- `src/falcon_correlate/unittests/test_contextvar_lifecycle.py`
- `src/falcon_correlate/unittests/test_req_context_integration.py`
- `src/falcon_correlate/unittests/test_validation_integration.py`
- `src/falcon_correlate/unittests/test_trusted_sources.py`

The existing Behaviour-Driven Development (BDD) scenarios for WSGI middleware
live under `tests/bdd/`, especially `tests/bdd/middleware.feature`,
`tests/bdd/contextvar_lifecycle.feature`, and their step files. ASGI behaviour
should use a focused ASGI feature file and step file instead of overloading the
current WSGI steps.

The relevant project documentation is:

- `docs/roadmap.md`, item 5.1.1.
- `docs/falcon-correlation-id-middleware-design.md`, especially section 3.1.1.
- `docs/complexity-antipatterns-and-refactoring-strategies.md`.
- `docs/users-guide.md`.
- `docs/documentation-style-guide.md`.

The relevant skills and tools for implementation are:

- `leta`, for semantic code navigation.
- `execplans`, for keeping this living plan current.
- `firecrawl-mcp`, for resolving external Falcon and ASGI prior-art questions.
- `code-review`, for review stance before commits.
- `commit-message`, for file-based commit messages.
- `pr-creation` and `en-gb-oxendict-style`, for pull request metadata.

External research performed for this draft:

- Falcon 4.2 middleware documentation confirms ASGI middleware hooks are
  `async def process_request(self, req, resp)` and
  `async def process_response(self, req, resp, resource, req_succeeded)`.
  It also documents the alternative `*_async` dual-mode hook convention:
  <https://falcon.readthedocs.io/en/stable/api/middleware.html>
- Falcon 4.2 testing documentation confirms `falcon.testing.TestClient`
  supports WSGI and ASGI applications, and `falcon.testing.ASGIConductor`
  provides coroutine-based ASGI lifecycle control:
  <https://falcon.readthedocs.io/en/stable/api/testing.html>
- `asgi-correlation-id` prior art confirms common ASGI correlation middleware
  options: configurable header name, generator, validator, and logging context
  integration:
  <https://github.com/snok/asgi-correlation-id>

## Constraints

- Do not implement `CorrelationIDMiddlewareASGI` until this draft is approved.
- Preserve existing public WSGI behaviour unless a failing test proves it
  contradicts the documented contract and the deviation is recorded here.
- Implement ASGI support as a separate public class named
  `CorrelationIDMiddlewareASGI`.
- Reuse `CorrelationIDConfig`; do not fork defaults, validation, trusted source
  parsing, generator handling, or validator handling.
- Preserve the constructor contract used by `CorrelationIDMiddleware`: accept
  either `config=CorrelationIDConfig(...)` or individual keyword arguments, but
  not both.
- Do not add ASGI lifespan hooks for this roadmap item unless Falcon requires
  them for request and response tests to pass.
- Do not add a new external dependency without explicit approval.
- Add tests before implementation changes. The first ASGI test run must show
  the expected red state.
- Use property tests only for real invariants over a range of inputs or
  interleavings.
- Update `docs/users-guide.md` for the consumer-facing ASGI API.
- Update `docs/falcon-correlation-id-middleware-design.md` for shared
  lifecycle decisions and ASGI cleanup guarantees.
- Mark `docs/roadmap.md` item 5.1.1 done only after implementation,
  documentation, validation, commit, push, and pull request update are
  complete.
- Prefer Makefile targets for gates. Run gates sequentially and capture long
  output with `tee` under `/tmp`.
- Use `coderabbit review --agent` after each major milestone and clear all
  concerns before moving to the next milestone.
- Do not use `/tmp` as a build target. Use it only for command logs or scratch
  files.

If satisfying the objective requires violating a constraint, stop immediately,
record the conflict in `Decision Log`, and ask for direction.

## Tolerances

- Scope: if the ASGI implementation needs more than 10 files changed or more
  than 350 net lines outside tests and documentation, stop and ask whether the
  work should be split.
- Public API: if the ASGI class cannot reuse the WSGI constructor contract
  cleanly, stop and present alternatives before changing the API.
- Typing: if concrete `falcon.asgi.Request` or `falcon.asgi.Response`
  annotations fail type checking, try a narrow internal protocol. Do not weaken
  public annotations to `object` without recording the evidence.
- Dependencies: if ASGI testing requires a package not already in
  `pyproject.toml`, stop before editing dependencies.
- Test iterations: if the same targeted ASGI test still fails after three
  focused implementation attempts, stop and ask for review.
- Validation: if `make check-fmt`, `make typecheck`, `make lint`,
  `make test`, `make markdownlint`, or `make nixie` fails for an unrelated
  reason that cannot be fixed within two focused attempts, stop and document
  the log path.
- Branch or pull request workflow: if the remote branch or pull request state
  requires force-push, branch deletion, or a published branch rename, stop and
  ask for direction.

## Risks

- Risk: Falcon ASGI request and response types may differ enough from WSGI
  types that helper annotations become awkward. Severity: medium. Likelihood:
  medium. Mitigation: keep shared helpers typed around the small surface used
  by both modes: `get_header`, `remote_addr`, `context`, and response header
  mutation.

- Risk: Falcon ASGI test clients may not set `remote_addr` the same way WSGI
  helpers do. Severity: high. Likelihood: medium. Mitigation: first verify the
  ASGI scope `client` behaviour in a focused test, then use that verified path
  for trusted-source scenarios.

- Risk: subclassing the WSGI middleware directly could leave synchronous hook
  methods visible on the ASGI class. Severity: medium. Likelihood: medium.
  Mitigation: extract a private shared base or mixin and define explicit async
  hooks on `CorrelationIDMiddlewareASGI`.

- Risk: response-header echo failures must not skip cleanup. Severity: high.
  Likelihood: low after the WSGI fix. Mitigation: keep response processing in
  a `finally`-based helper and test ASGI cleanup after response mutation
  failures.

- Risk: BDD coverage may become brittle if it mirrors every unit edge case.
  Severity: low. Likelihood: medium. Mitigation: keep BDD scenarios focused on
  externally observable ASGI request flows and put detailed edge cases in unit
  tests.

## Proposed implementation

### Milestone 1: verify the current contract

Use `leta` for code navigation and inspect the current WSGI behaviour before
editing tests:

```bash
leta show CorrelationIDConfig
leta show CorrelationIDMiddleware
leta refs CorrelationIDMiddleware
leta refs CorrelationIDConfig
```

Confirm that the existing WSGI response-header parity commits are still
present and that no `CorrelationIDMiddlewareASGI` symbol exists.

Acceptance for this milestone:

- The implementation notes in this ExecPlan remain accurate.
- Any discrepancy between documented behaviour and current WSGI behaviour is
  recorded in `Surprises & Discoveries`.
- `coderabbit review --agent` has no unresolved concerns for the milestone.

### Milestone 2: add failing ASGI tests

Add unit tests under `src/falcon_correlate/unittests/`, preferably in
`test_middleware_asgi.py`. Cover:

- construction with default keyword configuration;
- construction with a pre-built `CorrelationIDConfig`;
- config-plus-kwargs rejection parity with WSGI;
- `inspect.iscoroutinefunction` for `process_request` and
  `process_response`;
- `falcon.asgi.App` request flow exposing `req.context.correlation_id`;
- trusted incoming header acceptance;
- missing, empty, untrusted, invalid, or validator-exception incoming headers
  causing generation;
- response echo enabled, disabled, and missing-ID paths;
- cleanup after successful response processing and after header echo failure;
- concurrent ASGI requests with isolated correlation IDs.

Add a dedicated ASGI BDD feature, such as `tests/bdd/asgi_middleware.feature`,
with steps in `tests/bdd/test_asgi_middleware_steps.py`. The BDD suite should
prove at least one externally visible ASGI workflow: a Falcon ASGI app receives
a request, the resource observes the request correlation ID, and the response
header contains the same ID when echoing is enabled.

Use `hypothesis` only if the implementation introduces a true invariant worth
fuzzing. A useful optional property is that every generated or accepted ASGI
request exposes the same ID in request context and `correlation_id_var` during
the request and clears it afterwards.

Run focused red-state checks:

```bash
set -o pipefail
uv run pytest -v src/falcon_correlate/unittests/test_middleware_asgi.py \
  2>&1 | tee /tmp/test-falcon-correlate-5-1-1-asgi-unit-red.out
uv run pytest -v tests/bdd/test_asgi_middleware_steps.py \
  2>&1 | tee /tmp/test-falcon-correlate-5-1-1-asgi-bdd-red.out
```

Acceptance for this milestone:

- At least one focused test fails because `CorrelationIDMiddlewareASGI` is not
  implemented.
- The failure is expected red state, not an unrelated fixture or environment
  failure.
- `coderabbit review --agent` has no unresolved concerns for the milestone.

### Milestone 3: extract shared lifecycle logic

Refactor only as much as needed to share lifecycle behaviour between WSGI and
ASGI. The preferred shape is:

- keep `CorrelationIDConfig` unchanged;
- extract a private base or helper layer for constructor configuration,
  incoming ID choice, request context setup, response-header echoing, and
  reset-token cleanup;
- keep WSGI and ASGI hook methods as thin wrappers;
- keep response cleanup in a `finally` path so cleanup runs even when response
  header mutation fails.

Run WSGI regression tests after the refactor:

```bash
set -o pipefail
uv run pytest -v \
  src/falcon_correlate/unittests/test_middleware_configuration.py \
  src/falcon_correlate/unittests/test_contextvar_lifecycle.py \
  src/falcon_correlate/unittests/test_req_context_integration.py \
  src/falcon_correlate/unittests/test_validation_integration.py \
  src/falcon_correlate/unittests/test_trusted_sources.py \
  src/falcon_correlate/unittests/test_middleware_response_header.py \
  2>&1 | tee /tmp/test-falcon-correlate-5-1-1-wsgi-regression.out
```

Acceptance for this milestone:

- Existing WSGI tests still pass.
- Shared logic reduces duplication rather than creating parallel algorithms.
- `coderabbit review --agent` has no unresolved concerns for the milestone.

### Milestone 4: implement and export `CorrelationIDMiddlewareASGI`

Add `CorrelationIDMiddlewareASGI` to `src/falcon_correlate/middleware.py`.
Its public constructor should mirror `CorrelationIDMiddleware`. Its Falcon
hooks should be explicit coroutine methods:

```python
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

If Falcon's exported type names or the project type checker reject those
annotations, use the narrowest accurate type-safe alternative and record the
choice in `Decision Log`.

Export the class from `src/falcon_correlate/__init__.py` and add public export
tests.

Run focused ASGI checks:

```bash
set -o pipefail
uv run pytest -v src/falcon_correlate/unittests/test_middleware_asgi.py \
  2>&1 | tee /tmp/test-falcon-correlate-5-1-1-asgi-unit-green.out
uv run pytest -v tests/bdd/test_asgi_middleware_steps.py \
  2>&1 | tee /tmp/test-falcon-correlate-5-1-1-asgi-bdd-green.out
```

Acceptance for this milestone:

- Focused ASGI unit and behavioural tests pass.
- Public export tests pass.
- `coderabbit review --agent` has no unresolved concerns for the milestone.

### Milestone 5: update documentation and roadmap

Update `docs/users-guide.md` with an ASGI usage section:

```python
import falcon.asgi
from falcon_correlate import CorrelationIDMiddlewareASGI

middleware = CorrelationIDMiddlewareASGI()
app = falcon.asgi.App(middleware=[middleware])
```

State that ASGI configuration options match the WSGI middleware options, and
that ASGI application code can read `req.context.correlation_id` or
`correlation_id_var.get()` during the request.

Update `docs/falcon-correlation-id-middleware-design.md` with the final design
decision for sharing configuration and lifecycle logic between WSGI and ASGI.
Document the response-header echo and cleanup ordering.

Update `docs/roadmap.md` to check off all 5.1.1 sub-items and the parent item
only after implementation and validation have passed. Do not check off 5.1.2
unless that separate roadmap item is explicitly completed.

Acceptance for this milestone:

- Users can discover and wire the ASGI class from the guide.
- The design document records implementation-relevant decisions.
- Roadmap item 5.1.1 is checked off only when complete.
- `coderabbit review --agent` has no unresolved concerns for the milestone.

### Milestone 6: full validation, commit, push, and pull request update

Run validation sequentially:

```bash
set -o pipefail
make check-fmt 2>&1 | tee /tmp/check-fmt-falcon-correlate-5-1-1.out
make typecheck 2>&1 | tee /tmp/typecheck-falcon-correlate-5-1-1.out
make lint 2>&1 | tee /tmp/lint-falcon-correlate-5-1-1.out
make test 2>&1 | tee /tmp/test-falcon-correlate-5-1-1.out
make markdownlint 2>&1 | tee /tmp/markdownlint-falcon-correlate-5-1-1.out
make nixie 2>&1 | tee /tmp/nixie-falcon-correlate-5-1-1.out
```

If documentation was edited, run `make fmt` before the final `make check-fmt`
unless it would modify unrelated files. Inspect `git diff` before staging.

Commit only after applicable gates pass. Use the commit-message skill and
commit with a temporary message file through `git commit -F`.

Push the branch `5-1-1-implement-async-middleware-methods` to
`origin/5-1-1-implement-async-middleware-methods`. The pull request title must
include `(5.1.1)`, and the summary must link this ExecPlan:
`docs/execplans/5-1-1-implement-async-middleware-methods.md`.

Acceptance for this milestone:

- Working tree is clean after commit.
- Remote branch tracks `origin/5-1-1-implement-async-middleware-methods`.
- Pull request exists as a draft until implementation is approved or complete,
  depending on the review phase.

## Progress

- [x] 2026-05-08: Read `AGENTS.md` and loaded the `leta` and `execplans`
  skills for the original planning task.
- [x] 2026-05-08: Created the original pre-implementation ExecPlan for roadmap
  item 5.1.1.
- [x] 2026-05-09: Earlier approval allowed prerequisite investigation and WSGI
  response-header parity work to proceed.
- [x] 2026-05-10: Confirmed and fixed the WSGI response-header echo contract
  so ASGI parity has a correct shared target.
- [x] 2026-05-17: Updated WSGI response cleanup so `correlation_id_var` resets
  in a `finally` path when response-header echoing fails.
- [x] 2026-05-19: Loaded the `leta`, `execplans`, `firecrawl-mcp`,
  `pr-creation`, `commit-message`, and `en-gb-oxendict-style` skills for the
  current planning refresh.
- [x] 2026-05-19: Confirmed that the requested branch already exists, is
  checked out in this worktree, and tracks
  `origin/5-1-1-implement-async-middleware-methods`.
- [x] 2026-05-19: Created a `leta` workspace for this worktree.
- [x] 2026-05-19: Created context pack `pk_2ugy6etd` for the agent team with
  roadmap, design, middleware, and configuration references.
- [x] 2026-05-19: Used Firecrawl to verify Falcon ASGI middleware hooks,
  Falcon ASGI testing helpers, and ASGI correlation middleware prior art.
- [x] 2026-05-19: Used a Wyvern agent team for planning. One agent reviewed
  implementation shape and risks; another reviewed test and documentation
  coverage.
- [x] 2026-05-19: Refreshed this ExecPlan as a current draft awaiting approval
  for the remaining ASGI work.
- [x] 2026-05-19: Ran `make markdownlint` and `make nixie` for the refreshed
  plan. Logs are in
  `/tmp/markdownlint-falcon-correlate-5-1-1-plan-refresh.out` and
  `/tmp/nixie-falcon-correlate-5-1-1-plan-refresh.out`.
- [x] 2026-05-19: Ran `coderabbit review --agent` for the refreshed plan.
  CodeRabbit reported zero findings in
  `/tmp/coderabbit-falcon-correlate-5-1-1-plan-refresh.out`.
- [ ] Receive explicit approval before implementing ASGI middleware.
- [ ] Add failing ASGI unit and behavioural tests.
- [ ] Implement shared lifecycle helpers and `CorrelationIDMiddlewareASGI`.
- [ ] Update public exports, users' guide, design documentation, and roadmap.
- [ ] Run full validation, commit, push, and update the pull request.

## Surprises & Discoveries

- 2026-05-08: The current WSGI implementation already centralizes
  configuration in `CorrelationIDConfig`, so ASGI configuration sharing does
  not require a new configuration abstraction.
- 2026-05-08: The codebase had no `falcon.asgi.App` middleware tests and no
  `CorrelationIDMiddlewareASGI` public symbol.
- 2026-05-09: WSGI response-header tests confirmed the documented
  `echo_header_in_response` contract was incomplete. That gap was fixed before
  ASGI parity work.
- 2026-05-17: Review feedback identified that response-header echo failure
  could skip request-local cleanup. WSGI response processing now resets in a
  `finally` path, and ASGI must share that ordering.
- 2026-05-19: The target branch name was already checked out in another local
  worktree, so the current planning work continued in that target worktree
  instead of overwriting an active branch.
- 2026-05-19: PR #32 already exists for this branch and is currently open.
  It should be converted back to draft for this approval phase.
- 2026-05-19: Firecrawl confirmed Falcon's ASGI middleware methods are async
  request and response hooks and that Falcon provides ASGI-aware testing
  helpers.
- 2026-05-19: Wyvern review highlighted that ASGI trusted-source tests should
  first verify how Falcon exposes `remote_addr` from the ASGI scope.

## Decision Log

- 2026-05-08: Plan `CorrelationIDMiddlewareASGI` as a separate public class
  rather than converting `CorrelationIDMiddleware` into a dual-mode class. The
  roadmap requires the named ASGI class.
- 2026-05-08: Reuse `CorrelationIDConfig` and extract shared lifecycle helpers
  instead of duplicating request and response logic.
- 2026-05-09: Blocked ASGI implementation at the response-header parity
  tolerance when WSGI did not honour the documented response echo contract.
- 2026-05-10: Resolved the response-header tolerance by fixing WSGI
  `process_response` to honour the documented public contract.
- 2026-05-12: Kept `resp.set_header` failures propagating instead of catching
  them, while ensuring cleanup still runs.
- 2026-05-19: Treat this refreshed ExecPlan as a new approval gate for the
  remaining ASGI implementation. Historical WSGI parity commits stay in the
  branch, but no ASGI implementation work begins until approval is explicit.
- 2026-05-19: Use a dedicated ASGI unit test module and dedicated ASGI BDD
  feature file. This keeps WSGI and ASGI scenarios readable while still
  proving parity.

## Outcomes & Retrospective

Current outcome: the refreshed ExecPlan is ready for review. The remaining
ASGI implementation is not approved yet and has not begun.

Historical prerequisite outcome: this branch already fixed the WSGI
response-header echo contract and cleanup ordering so ASGI parity has a
correct shared target. The latest recorded full validation from that earlier
milestone reported the local gates passing with 362 tests passed and 11
skipped.

Planning refresh validation: `make markdownlint`, `make nixie`, and
`coderabbit review --agent` passed on 2026-05-19. CodeRabbit reported zero
findings for the refreshed plan.

Lessons so far: Falcon response-header echo and `ContextVar` cleanup must be
ordered so request-local state is cleared even when response mutation fails.
ASGI middleware should share those lifecycle decisions rather than copy a
parallel correlation algorithm.
