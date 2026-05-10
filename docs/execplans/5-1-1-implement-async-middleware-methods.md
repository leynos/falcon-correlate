# Implement async middleware methods (5.1.1)

This Execution Plan (ExecPlan) is a living document. The sections
`Constraints`, `Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`,
`Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work
proceeds.

Status: IN PROGRESS

## Purpose / big picture

Roadmap item 5.1.1 adds Falcon ASGI support to `falcon-correlate` by
introducing a middleware class whose Falcon hook methods are asynchronous.
After implementation, a consumer using `falcon.asgi.App` can install
`CorrelationIDMiddlewareASGI` and receive the same correlation ID behaviour
that WSGI users receive from `CorrelationIDMiddleware`: incoming IDs are read
from the configured header only when the source is trusted, invalid or
untrusted IDs are replaced by generated IDs, the request context and
`contextvars` state expose the active correlation ID, and response processing
cleans up request-local state.

Success is observable when all of the following are true:

- `CorrelationIDMiddlewareASGI` exists in `src/falcon_correlate/middleware.py`
  and is exported from `src/falcon_correlate/__init__.py`.
- `CorrelationIDMiddlewareASGI.process_request(self, req, resp)` and
  `CorrelationIDMiddlewareASGI.process_response(self, req, resp, resource,
  req_succeeded)` are `async def` methods with Falcon ASGI-compatible
  signatures.
- The ASGI class shares `CorrelationIDConfig` and the existing configuration
  validation path with the WSGI class.
- ASGI tests prove generation, trusted incoming ID acceptance, invalid incoming
  ID rejection, request-context exposure, response-header behaviour, and
  cleanup after response processing.
- Behavioural tests written with `pytest-bdd` prove that a Falcon ASGI
  application can use the middleware in an externally observable request flow.
- Documentation explains when to use `CorrelationIDMiddlewareASGI`, how its
  configuration matches the WSGI class, and what behaviour users can rely on.
- `docs/roadmap.md` marks item 5.1.1 complete only after code, tests,
  documentation, validation, commit, push and draft pull request creation are
  complete.
- The repository passes `make check-fmt`, `make typecheck`, `make lint`,
  `make test`, `make markdownlint`, and `make nixie`.

This plan must be approved before implementation begins. Do not implement the
middleware, update the roadmap checkbox, or create implementation commits until
that approval is explicit.

## Context and orientation

The existing middleware implementation lives in
`src/falcon_correlate/middleware.py`. The immutable `CorrelationIDConfig`
dataclass stores validated configuration for `header_name`, `trusted_sources`,
`generator`, `validator`, and `echo_header_in_response`. The existing WSGI
`CorrelationIDMiddleware` constructor accepts either a pre-built
`CorrelationIDConfig` or keyword arguments that are converted with
`CorrelationIDConfig.from_kwargs`. This is the configuration logic that the
ASGI class must reuse.

`CorrelationIDMiddleware.process_request` currently retrieves the incoming
header through `_get_incoming_header_value`, checks trust with
`_is_trusted_source`, validates trusted incoming IDs through `_is_valid_id`,
sets `req.context.correlation_id`, and stores a reset token for
`correlation_id_var`. `CorrelationIDMiddleware.process_response` retrieves the
stored reset token, ignores missing or mismatched tokens, resets
`correlation_id_var`, and clears the reset-token attribute to prevent double
reset. The ASGI class should preserve this lifecycle and should not introduce
a separate correlation algorithm.

The package root, `src/falcon_correlate/__init__.py`, re-exports public API
symbols. Any public ASGI middleware class must be added there and covered by
`src/falcon_correlate/unittests/test_public_exports.py`.

Current WSGI-oriented middleware tests live under
`src/falcon_correlate/unittests/`, especially:

- `test_middleware_configuration.py`
- `test_middleware_falcon_integration.py`
- `test_contextvar_lifecycle.py`
- `test_req_context_integration.py`
- `test_validation_integration.py`
- `test_trusted_sources.py`

Current behavioural tests live under `tests/bdd/`. The existing WSGI
middleware scenarios are in `tests/bdd/middleware.feature` and
`tests/bdd/test_middleware_steps.py`. ASGI coverage may be added beside these
tests or in a focused `asgi_middleware.feature` file if that keeps the step
definitions clearer.

The relevant project documentation is:

- `docs/roadmap.md` item 5.1.1 for the concrete checklist.
- `docs/falcon-correlation-id-middleware-design.md` section 3.1.1 for Falcon
  middleware shape and the ASGI note that hook methods are asynchronous.
- `docs/falcon-correlation-id-middleware-design.md` sections 3.2 and 3.3 for
  ID retrieval, trusted source handling, validation and context storage.
- `docs/falcon-correlation-id-middleware-design.md` section 4.1 and
  implementation notes for configuration defaults and WSGI examples that need
  ASGI parity notes.
- `docs/complexity-antipatterns-and-refactoring-strategies.md` for the
  refactoring constraint: avoid growing request lifecycle code into a bumpy,
  deeply nested path when extracting shared helpers is clearer.
- `docs/users-guide.md` for consumer-facing setup and API examples.

The relevant skills are:

- `/home/leynos/.codex/skills/execplans/SKILL.md` to keep this living
  ExecPlan current.
- `/home/leynos/.codex/skills/leta/SKILL.md` for semantic navigation of the
  middleware, tests and public exports.
- `/home/leynos/.codex/skills/code-review/SKILL.md` for the post-change review
  stance before commit.
- `/home/leynos/.codex/skills/commit-message/SKILL.md` when committing the
  approved implementation.
- `/home/leynos/.codex/skills/pr-creation/SKILL.md` when creating or updating
  the draft pull request.

## Constraints

- Do not begin implementation until this draft ExecPlan is approved.
- Preserve all public behaviour of `CorrelationIDMiddleware` unless a failing
  test proves that existing behaviour contradicts the documented contract and
  the deviation is recorded in the decision log.
- Implement ASGI support as a separate public class named
  `CorrelationIDMiddlewareASGI`.
- Keep `CorrelationIDConfig` as the shared configuration object. Do not fork
  defaults, validation rules, trusted source parsing, generator handling, or
  validator handling between WSGI and ASGI classes.
- Keep the constructor contract aligned with the WSGI middleware: accept either
  `config=CorrelationIDConfig(...)` or individual keyword configuration, but
  not both.
- Do not add ASGI lifespan hooks for this roadmap item unless Falcon requires
  them for the request/response tests to pass. Section 3.1.1 says lifespan
  hooks are not directly involved in per-request correlation ID handling.
- Do not add a new external dependency. The development environment already
  includes `pytest`, `pytest-bdd`, `pytest-asyncio`, `hypothesis` and Falcon 4.
- Add tests before implementation changes. For missing ASGI behaviour, first
  demonstrate at least one failing unit or behavioural test.
- Use `hypothesis` only where a genuine invariant over a range of inputs or
  interleavings is introduced. Basic parity scenarios do not require property
  tests.
- Update `docs/users-guide.md` for the consumer-facing ASGI API and update
  `docs/falcon-correlation-id-middleware-design.md` for any internal design
  decisions made during implementation.
- Check off `docs/roadmap.md` item 5.1.1 only after implementation,
  documentation and validation are complete.
- Keep Markdown wrapped at 80 columns and code blocks within 120 columns.
- Follow the repository command guidance: prefer Makefile targets, run quality
  gates sequentially, and capture long outputs with `tee` logs under `/tmp`.
- Do not use `/tmp` as a build target. Use it only for command logs or scratch
  files.

If satisfying the objective requires violating a constraint, stop immediately,
record the conflict in `Decision Log`, and ask for direction.

## Tolerances

- Scope: if the approved implementation needs more than 10 files changed or
  more than 350 net lines outside tests and documentation, stop and ask whether
  the work should be split.
- Public API: if `CorrelationIDMiddlewareASGI` cannot reuse the WSGI
  constructor contract cleanly, stop and present the alternatives before
  changing the API.
- Behavioural parity: if tests reveal the documented response-header contract
  differs from the current WSGI implementation, stop after writing the failing
  test and ask whether to fix WSGI and ASGI together or document narrower ASGI
  parity for this item.
- Dependencies: if Falcon ASGI testing requires an additional package beyond
  the existing development dependencies, stop and request approval before
  editing `pyproject.toml`.
- Test iterations: if the same targeted ASGI test still fails after three
  focused implementation attempts, stop, update `Surprises & Discoveries`, and
  ask for review.
- Validation: if `make check-fmt`, `make typecheck`, `make lint`,
  `make test`, `make markdownlint`, or `make nixie` fails for an unrelated
  reason that cannot be fixed within two focused attempts, stop and document
  the failure with the log path.
- Branch or pull request workflow: if the remote branch or draft pull request
  already exists with incompatible history, stop before force-pushing or
  renaming a published pull request branch.

## Risks

- Risk: Falcon ASGI request and response types may differ enough from WSGI
  types that private helper annotations become awkward.
  Severity: medium.
  Likelihood: medium.
  Mitigation: keep helper logic duck-typed around the small Falcon surface
  actually used by both modes: `get_header`, `remote_addr`, `context`, and
  response header mutation.

- Risk: implementing ASGI by subclassing the WSGI class directly could make an
  async class inherit synchronous hook methods unintentionally.
  Severity: medium.
  Likelihood: medium.
  Mitigation: prefer extracting shared non-hook helper methods or a small
  internal base class, then define explicit async hook methods on
  `CorrelationIDMiddlewareASGI`.

- Risk: response-header echo behaviour is documented and configured, but the
  currently inspected WSGI `process_response` path appears focused on cleanup.
  Severity: high.
  Likelihood: medium.
  Mitigation: write targeted tests around both WSGI and ASGI response-header
  behaviour before implementation. If the tests expose a WSGI gap, use the
  tolerance above to escalate the intended scope.

- Risk: async context isolation failures may be hidden by sequential tests.
  Severity: high.
  Likelihood: medium.
  Mitigation: include an ASGI concurrency test that sends overlapping requests
  with distinct generated IDs or accepted trusted IDs and verifies no leakage.

- Risk: BDD scenarios can become brittle if they duplicate too much Falcon
  test-client setup.
  Severity: low.
  Likelihood: medium.
  Mitigation: keep behavioural scenarios focused on user-visible ASGI outcomes
  and put detailed edge-case coverage in unit tests.

## Proposed implementation

### Milestone 1: verify the current contract

Use `leta` for code navigation and inspect the current WSGI behaviour before
editing tests. Confirm the exact symbols and references:

```bash
leta show CorrelationIDConfig
leta show CorrelationIDMiddleware
leta refs CorrelationIDMiddleware
leta refs CorrelationIDConfig
```

Review the WSGI tests listed in the context section and identify the smallest
test helpers worth sharing with ASGI tests. Avoid broad refactors at this
stage.

Acceptance for this milestone:

- The implementation notes in this ExecPlan remain accurate.
- Any discrepancy between documented response-header behaviour and current
  WSGI behaviour is recorded in `Surprises & Discoveries`.

### Milestone 2: add failing ASGI tests

Add unit tests under `src/falcon_correlate/unittests/`, preferably in a new
`test_middleware_asgi.py` file unless the existing Falcon integration test can
be extended without obscuring the WSGI cases. The tests should cover:

- the ASGI class is constructible with default keyword configuration;
- the ASGI class accepts a pre-built `CorrelationIDConfig`;
- `process_request` and `process_response` are coroutine functions;
- a `falcon.asgi.App` using the middleware completes a request and exposes
  `req.context.correlation_id`;
- a trusted incoming header is accepted;
- an untrusted, missing, empty, or invalid incoming header causes generation;
- response processing echoes the configured header when enabled and omits it
  when disabled, subject to the response-header tolerance above;
- `correlation_id_var` is reset after response processing; and
- concurrent ASGI requests keep their correlation IDs isolated.

Add or extend BDD coverage under `tests/bdd/` for at least one externally
observable ASGI request flow. A good initial scenario is: given a
`falcon.asgi.App` with `CorrelationIDMiddlewareASGI`, when a client requests a
resource, then the response body contains the request correlation ID and the
response header contains the same ID when echoing is enabled.

Run only the focused new tests first and capture logs:

```bash
set -o pipefail
uv run pytest -v src/falcon_correlate/unittests/test_middleware_asgi.py \
  2>&1 | tee /tmp/test-falcon-correlate-5-1-1-asgi-unit-red.out
uv run pytest -v tests/bdd/test_asgi_middleware_steps.py \
  2>&1 | tee /tmp/test-falcon-correlate-5-1-1-asgi-bdd-red.out
```

Acceptance for this milestone:

- At least one focused test fails because `CorrelationIDMiddlewareASGI` does
  not exist or because async middleware behaviour is not implemented.
- The failure is the expected red state, not an unrelated fixture or
  environment failure.

### Milestone 3: extract shared lifecycle logic without changing behaviour

Refactor only as much as needed to share the lifecycle between WSGI and ASGI.
The preferred shape is:

- keep `CorrelationIDConfig` unchanged unless tests expose a real gap;
- keep the existing constructor validation path in one reusable class or
  helper;
- extract synchronous helper methods that compute and store the correlation ID
  without depending on whether the Falcon hook is sync or async; and
- call those helpers from both `CorrelationIDMiddleware.process_request` and
  `CorrelationIDMiddlewareASGI.process_request`.

Do the same for response processing: one shared helper should apply any
response-header echo logic and reset the `contextvars` token, while the WSGI
and ASGI hook methods remain thin mode-specific wrappers.

Run the existing WSGI-focused tests after the refactor and before adding ASGI
implementation details:

```bash
set -o pipefail
uv run pytest -v \
  src/falcon_correlate/unittests/test_middleware_configuration.py \
  src/falcon_correlate/unittests/test_contextvar_lifecycle.py \
  src/falcon_correlate/unittests/test_req_context_integration.py \
  src/falcon_correlate/unittests/test_validation_integration.py \
  src/falcon_correlate/unittests/test_trusted_sources.py \
  2>&1 | tee /tmp/test-falcon-correlate-5-1-1-wsgi-regression.out
```

Acceptance for this milestone:

- Existing WSGI tests still pass.
- Shared logic reduces duplication rather than creating parallel WSGI and ASGI
  algorithms.
- Any needed response-header fix is covered by tests and recorded as a design
  decision.

### Milestone 4: implement `CorrelationIDMiddlewareASGI`

Add `CorrelationIDMiddlewareASGI` to `src/falcon_correlate/middleware.py`.
Its constructor should mirror `CorrelationIDMiddleware`. Its Falcon hooks
should be explicit coroutine methods:

```python
async def process_request(self, req: falcon.asgi.Request, resp: falcon.asgi.Response) -> None:
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

If Falcon's exported type names differ or `ty` rejects these annotations, use
the narrowest accurate annotations that pass type checking and document the
choice in the decision log. Do not weaken public annotations to `object`
without evidence from `ty`.

Export the class from `src/falcon_correlate/__init__.py` and add a public
export test.

Run the focused ASGI tests again:

```bash
set -o pipefail
uv run pytest -v src/falcon_correlate/unittests/test_middleware_asgi.py \
  2>&1 | tee /tmp/test-falcon-correlate-5-1-1-asgi-unit-green.out
uv run pytest -v tests/bdd/test_asgi_middleware_steps.py \
  2>&1 | tee /tmp/test-falcon-correlate-5-1-1-asgi-bdd-green.out
```

Acceptance for this milestone:

- Focused ASGI unit and behavioural tests pass.
- The public export test passes.
- WSGI tests touched by shared logic still pass.

### Milestone 5: update documentation and roadmap

Update `docs/users-guide.md` with an ASGI usage section that shows:

```python
import falcon.asgi
from falcon_correlate import CorrelationIDMiddlewareASGI

middleware = CorrelationIDMiddlewareASGI()
app = falcon.asgi.App(middleware=[middleware])
```

State that ASGI configuration options are the same as the WSGI middleware
options, and that application code can read `req.context.correlation_id` or
`correlation_id_var.get()` during the request.

Update `docs/falcon-correlation-id-middleware-design.md` with the final design
decision for sharing configuration and lifecycle logic between WSGI and ASGI.
If response-header behaviour required a WSGI correction, record that as part
of the same decision.

Update `docs/roadmap.md` to check off all 5.1.1 sub-items and the parent item
only after the implementation and validation gates have passed. Do not check
off 5.1.2 unless this branch explicitly completes every item under 5.1.2 as
well.

Acceptance for this milestone:

- Users can discover the ASGI class and wire it into a `falcon.asgi.App` from
  the guide.
- The design document records implementation-relevant decisions instead of
  only repeating the roadmap.
- Roadmap item 5.1.1 is checked off only when the branch genuinely implements
  it.

### Milestone 6: run full validation, commit, push and draft the PR

Run validation sequentially and capture logs:

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

Commit only after all applicable gates pass. Use the commit-message skill and
commit with a temporary message file through `git commit -F`, not `git commit
-m`.

Push the branch `5-1-1-implement-async-middleware-methods` to
`origin/5-1-1-implement-async-middleware-methods` and create a draft pull
request. The PR title must include `(5.1.1)`, and the summary must link this
ExecPlan:
`docs/execplans/5-1-1-implement-async-middleware-methods.md`.

Acceptance for this milestone:

- Working tree is clean after commit.
- Remote branch tracks `origin/5-1-1-implement-async-middleware-methods`.
- Draft PR exists and clearly states that it implements the approved ExecPlan.

## Progress

- [x] 2026-05-08: Read `AGENTS.md` and loaded the `leta` and `execplans`
  skills for the planning task.
- [x] 2026-05-08: Checked the starting branch and renamed it from
  `feat/plan-asgi-middleware` to
  `5-1-1-implement-async-middleware-methods`.
- [x] 2026-05-08: Used a Wyvern agent team for planning reconnaissance. One
  helper reviewed the roadmap and design documentation; another reviewed the
  middleware implementation and test layout.
- [x] 2026-05-08: Confirmed that `CorrelationIDConfig` is the existing shared
  configuration point and that no `CorrelationIDMiddlewareASGI` symbol exists
  yet.
- [x] 2026-05-08: Drafted this pre-implementation ExecPlan.
- [x] 2026-05-09: Received explicit approval to implement the approved
  ExecPlan and changed plan status from `DRAFT` to `IN PROGRESS`.
- [x] 2026-05-09: Re-read `CorrelationIDMiddleware`,
  `CorrelationIDConfig`, public export tests, WSGI Falcon integration tests,
  and BDD middleware steps before editing.
- [x] 2026-05-09: Added
  `src/falcon_correlate/unittests/test_middleware_response_header.py` to
  verify the documented WSGI response-header echo contract before ASGI parity
  work.
- [x] 2026-05-09: Ran
  `uv run pytest -v src/falcon_correlate/unittests/test_middleware_response_header.py`
  and captured the red-state log at
  `/tmp/test-falcon-correlate-5-1-1-wsgi-response-header-red.out`.
- [x] 2026-05-10: Resolved the confirmed WSGI response-header contract gap by
  echoing `req.context.correlation_id` through `resp.set_header` before
  reset-token cleanup when `echo_header_in_response` is enabled.
- [x] 2026-05-10: Ran the two focused response-header tests requested for the
  unblock and captured the passing log at
  `/tmp/test-falcon-correlate-5-1-1-response-header-fix.out`.
- [x] 2026-05-10: Ran response-header validation gates after the WSGI fix:
  `make check-fmt`, `make typecheck`, `make lint`, `make test`,
  `make markdownlint`, and `make nixie` all passed.
- [ ] Add failing unit and behavioural tests for ASGI middleware behaviour.
- [ ] Implement `CorrelationIDMiddlewareASGI` and shared lifecycle helpers.
- [ ] Update public exports, user documentation, design documentation and the
  roadmap.
- [ ] Run full validation, commit, push and create a draft PR.

## Surprises & Discoveries

- 2026-05-08: The current WSGI implementation already centralizes
  configuration in `CorrelationIDConfig`, so ASGI configuration sharing should
  not require a new configuration abstraction.
- 2026-05-08: The current codebase has no `falcon.asgi.App` middleware tests
  and no `CorrelationIDMiddlewareASGI` public symbol, so ASGI support is a new
  public surface.
- 2026-05-08: The inspected WSGI `process_response` implementation resets the
  context variable but does not visibly apply the documented
  `echo_header_in_response` behaviour. The implementation phase must test this
  contract before assuming parity.
- 2026-05-09: Re-inspection confirmed the WSGI `process_response` method
  currently contains only reset-token handling and does not call
  `resp.set_header`. The next red test will verify whether the documented
  response-header echo contract is currently unmet.
- 2026-05-09: The new WSGI response-header test confirmed the documented
  contract gap. With `echo_header_in_response=True`, `resp.get_header(
  "X-Correlation-ID")` was `None` after `process_response`, while the disabled
  echo test passed. This reaches the plan tolerance for response-header parity
  and pauses implementation pending user direction.
- 2026-05-10: The user directed the implementation to add response-header
  echoing to `CorrelationIDMiddleware.process_response` using
  `req.context.correlation_id` and the configured header name. The focused
  red-state test now passes.
- 2026-05-10: Full validation after the WSGI response-header fix passed with
  `make test` reporting 353 passed and 11 skipped. This confirms the narrower
  contract fix did not regress the existing unit or behavioural suite.

## Decision Log

- 2026-05-08: Keep this as a draft plan only. The user explicitly stated that
  the plan must be approved before implementation, so this branch must not
  implement ASGI middleware until approval is received.
- 2026-05-08: Plan `CorrelationIDMiddlewareASGI` as a separate public class
  rather than converting `CorrelationIDMiddleware` into a dual-mode class. The
  roadmap requires a named ASGI class, and Falcon expects async middleware
  hooks for ASGI mode.
- 2026-05-08: Reuse `CorrelationIDConfig` and extract shared lifecycle helpers
  instead of duplicating request and response logic. This satisfies roadmap
  item 5.1.1 while limiting the complexity risk described in
  `docs/complexity-antipatterns-and-refactoring-strategies.md`.
- 2026-05-08: Treat response-header echo as a verified contract, not an
  assumption. The docs and configuration promise this behaviour, but the
  current WSGI code inspection suggests the implementation may be incomplete.
- 2026-05-09: Treat the user's implementation request as explicit approval of
  this ExecPlan. The work may now proceed milestone by milestone, but the
  tolerance requiring escalation on a confirmed WSGI response-header contract
  gap still applies.
- 2026-05-09: Block implementation at the response-header tolerance. Options:
  fix WSGI response-header echo and make ASGI share that corrected lifecycle,
  or narrow this roadmap item so ASGI matches the current implementation and
  update documentation to remove the response-header promise. The first option
  preserves the documented public contract; the second avoids expanding
  runtime behaviour in this branch but leaves or codifies a surprising
  configuration no-op.
- 2026-05-10: Resolve the response-header tolerance by fixing WSGI
  `process_response` to honour the existing documented contract. The block
  reads `req.context.correlation_id`, skips missing values, uses
  `self._config.header_name`, and runs before any `ContextVar` reset logic.

## Outcomes & Retrospective

No implementation outcome exists yet. This plan is awaiting approval. After
implementation, update this section with the commits produced, validation
results, pull request link, and any lessons about Falcon ASGI middleware or
context variable behaviour.
