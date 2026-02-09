# Integrate validation into request processing (2.3.2)

This Execution Plan (ExecPlan) is a living document. The sections
`Constraints`, `Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`,
`Decision log`, and `Outcomes & retrospective` must be kept up to date as work
proceeds.

Status: COMPLETE

## Purpose / big picture

The middleware currently accepts incoming correlation IDs from trusted sources
without checking their format. A trusted proxy could forward a malformed,
excessively long, or potentially malicious string, and the middleware would
propagate it unchanged. Task 2.3.2 closes this gap by calling the configured
`validator` (when present) on every incoming ID that has already passed the
trusted-source check. When validation fails, the middleware generates a fresh
ID and logs the rejection at DEBUG level.

Success is observable when:

- A request from a trusted source carrying an invalid correlation ID receives
  a newly generated ID instead of the invalid one.
- A request from a trusted source carrying a valid correlation ID still
  receives that same ID (no regression).
- A request with no validator configured behaves exactly as before (backwards
  compatible).
- A custom validator callable is invoked when provided.
- Validation failures produce a `DEBUG`-level log message containing the
  rejected value.
- All existing tests continue to pass unchanged.
- New unit and behaviour-driven development (BDD) tests cover every new code
  path.
- `docs/users-guide.md` documents the updated behaviour.
- `docs/roadmap.md` shows task 2.3.2 as complete.
- All quality gates pass (`make check-fmt`, `make typecheck`, `make lint`,
  `make test`).

## Constraints

- Preserve the existing public API surface. No new public functions or classes
  are added; only internal behaviour of `process_request` changes.
- The `validator` parameter remains optional (`None` by default). When `None`,
  no validation occurs and behaviour is identical to the current implementation.
- Only the standard library `logging` module is used for logging (no new
  dependencies).
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
- Ambiguity: if validation semantics conflict with the design document, stop
  and present options with trade-offs.

## Risks

- Risk: Existing BDD scenario "Correlation ID header is captured" sends
  `"cid-123"` from a trusted source and expects it back verbatim. If a default
  validator were enabled, this non-UUID string would be rejected. Severity:
  medium. Likelihood: low (validator defaults to `None`). Mitigation: validator
  remains `None` by default, so existing tests are unaffected. New
  validation-specific tests explicitly configure a validator.

- Risk: Logging in `process_request` could introduce import-time side effects
  or performance overhead. Severity: low. Likelihood: low. Mitigation: use
  module-level `logging.getLogger(__name__)` which is standard practice and
  negligible cost. The `DEBUG` level means the message is only formatted when
  DEBUG logging is active.

- Risk: Cognitive complexity of `process_request` increases beyond the
  threshold of 9. Severity: medium. Likelihood: low. Mitigation: extract a
  private helper method `_is_valid_id` to keep `process_request` flat and
  simple.

## Progress

- [x] (2026-02-09 00:00Z) Research and scope confirmation.
- [x] (2026-02-09 00:10Z) Add unit tests for validation integration (TDD red
  phase).
- [x] (2026-02-09 00:15Z) Add BDD scenarios for validation integration.
- [x] (2026-02-09 00:20Z) Implement validation in `process_request`.
- [x] (2026-02-09 00:25Z) Run tests to confirm they pass (TDD green phase).
- [x] (2026-02-09 00:30Z) Update `docs/users-guide.md`.
- [x] (2026-02-09 00:30Z) Record design decisions in design document.
- [x] (2026-02-09 00:35Z) Mark task 2.3.2 complete in `docs/roadmap.md`.
- [x] (2026-02-09 00:40Z) Run all quality gates.

## Surprises & discoveries

- Observation: The `make typecheck` gate (`ty check`) fails on the baseline
  commit with an `unresolved-import` error for `uuid_utils`. Evidence: stashing
  all changes and running `make typecheck` on the clean baseline produces the
  identical error. Impact: none for this task; the error is pre-existing and
  unrelated to the validation integration changes.

## Decision log

- Decision: Extract validator invocation into `_is_valid_id` helper method
  rather than inlining the check in `process_request`. Rationale: keeps
  `process_request` cognitive complexity low by delegating the
  validator-presence check; follows the existing pattern of private helpers
  (`_get_incoming_header_value`, `_is_trusted_source`). Date/Author: 2026-02-09.

- Decision: Log validation failures at DEBUG level (not WARNING or INFO).
  Rationale: the design document (section 3.6.1) mentions logging rejected IDs
  for security auditing, but the roadmap task explicitly specifies DEBUG level.
  DEBUG is appropriate because validation failure is a normal operational event
  (malformed IDs from proxies are expected), not an error condition.
  Date/Author: 2026-02-09.

## Outcomes & retrospective

The validation integration is now complete. The `process_request` method in
`CorrelationIDMiddleware` calls the configured validator (when present) on
incoming IDs that pass the trusted-source check. Invalid IDs trigger new
generation with a `DEBUG`-level log. A private `_is_valid_id` helper keeps
complexity low. When no validator is configured, behaviour is unchanged
(backwards compatible).

New tests: 15 unit tests in `test_validation_integration.py` covering five
categories (no-validator backwards compatibility, validator accepting,
validator rejecting, logging, and validator-not-called-when-unnecessary) plus 4
BDD scenarios in `middleware.feature`. Total test suite: 186 passed, 11 skipped
(continuous integration (CI)-only workflow tests).

All quality gates passed: `make check-fmt`, `make lint`, `make test`,
`make markdownlint`. The `make typecheck` failure is pre-existing and unrelated
(see Surprises & discoveries).

## Context and orientation

The project is `falcon-correlate`, a correlation ID middleware for the Falcon
web framework. The middleware intercepts every request, retrieves or generates
a correlation ID, stores it on `req.context.correlation_id`, and optionally
echoes it in the response.

### Current request processing flow

In `src/falcon_correlate/middleware.py` at lines 465-494, `process_request`
currently:

1. Calls `_get_incoming_header_value(req)` to read and normalise the header.
2. If a non-empty header exists and the source IP is trusted, accepts the
   incoming ID verbatim.
3. Otherwise, calls `self._config.generator()` to produce a new ID.

The `validator` field already exists on `CorrelationIDConfig` (line 152) as
`Callable[[str], bool] | None`, defaulting to `None`. It is validated at config
time (lines 253-257) to be callable if provided. The middleware exposes it via
a read-only property (lines 411-414). However, **the validator is never called
during request processing**. This is the gap task 2.3.2 fills.

### Key files

- `src/falcon_correlate/middleware.py` — Core middleware; `process_request` at
  line 465 is the primary edit target.
- `src/falcon_correlate/__init__.py` — Public exports (no changes needed).
- `src/falcon_correlate/unittests/test_generator_invocation.py` — Existing
  test patterns for `process_request` with mock generators and test clients.
- `tests/bdd/middleware.feature` — Existing BDD scenarios for middleware
  behaviour.
- `tests/bdd/test_middleware_steps.py` — Existing BDD step definitions.
- `tests/conftest.py` — Shared fixtures: `CorrelationEchoResource`,
  `TrackingMiddleware`.
- `docs/users-guide.md` — User documentation (lines 141-176 document the
  `validator` parameter; lines 51-69 document the request processing flow).
- `docs/roadmap.md` — Task tracking (lines 86-91 for task 2.3.2).
- `docs/falcon-correlation-id-middleware-design.md` — Design document
  (section 3.2.4 at line 316 covers validation; section 3.6.1 at line 660
  covers security considerations).

### Existing patterns to reuse

- The `create_test_client` fixture pattern from
  `test_generator_invocation.py` (lines 64-102) provides a factory for building
  test clients with configurable middleware. This pattern should be extended to
  accept a `validator` parameter.
- The BDD step definitions in `test_middleware_steps.py` already have steps
  for custom validators and generators that can be built upon.
- The `_MiddlewareKwargs` TypedDict in `test_generator_invocation.py`
  (lines 21-25) should be extended with a `validator` field.

### Logging conventions

No logging currently exists in the `src/` tree. The project's Python rules
(`.rules/python-exception-design-raising-handling-and-logging.md` lines
113-140) prescribe:

- `import logging` at module level.
- `logger = logging.getLogger(__name__)` at module level.
- Lazy interpolation: `logger.debug("message %s", value)`.
- No f-strings or %-formatting in log calls.

## Plan of work

### Stage A: Add unit tests (TDD red phase)

Create a new test file
`src/falcon_correlate/unittests/test_validation_integration.py` following the
patterns in `test_generator_invocation.py`. The tests cover five categories:

**1. No validator configured — backwards compatibility:**

- Test that when no validator is configured, a trusted source's incoming ID
  is accepted without validation.

**2. Validator returns `True` — valid ID accepted:**

- Test that when a validator returns `True`, the incoming ID from a trusted
  source is accepted.

**3. Validator returns `False` — invalid ID triggers generation:**

- Test that when a validator returns `False`, the incoming ID is rejected and
  the generator is called to produce a new ID.
- Test that a mock validator is called with the incoming header value.
- Test that a custom validator (not just `default_uuid_validator`) is called
  when provided.

**4. Logging of validation failures:**

- Test that when validation fails, a DEBUG-level log message is emitted
  containing the rejected value.
- Test that when validation succeeds, no log message is emitted.

**5. Validator not invoked when unnecessary:**

- Test that validation is not called when the source is untrusted (the
  validator is bypassed entirely because the ID is already rejected).
- Test that validation is not called when no incoming header is present.

The test file will use `unittest.mock.MagicMock` for validators, the existing
`create_test_client` factory pattern, and `caplog` from pytest for log
assertions.

### Stage B: Add BDD scenarios

Add new scenarios to `tests/bdd/middleware.feature` under a new comment section
`# Validation scenarios`:

1. **Invalid ID from trusted source triggers new generation**: A trusted
   source sends an invalid ID with a rejecting validator configured; the
   middleware generates a new one.
2. **Valid ID from trusted source is accepted after validation**: A trusted
   source sends a valid ID with an accepting validator; it passes through.
3. **Custom validator is called for incoming IDs**: A custom validator is
   configured and invoked for the incoming ID.
4. **No validator configured accepts any ID from trusted source**: Without a
   validator, any string from a trusted source is accepted.

Add corresponding step definitions in `tests/bdd/test_middleware_steps.py`.

### Stage C: Implement validation

Modify `src/falcon_correlate/middleware.py`:

1. Add `import logging` to the existing imports (after `import ipaddress`,
   not inside `TYPE_CHECKING`).

2. Add a module-level logger after `DEFAULT_HEADER_NAME` (around line 19):

       logger = logging.getLogger(__name__)

3. Add a private method `_is_valid_id` to `CorrelationIDMiddleware` after
   `_is_trusted_source` (after line 463):

       def _is_valid_id(self, value: str) -> bool:
           """Check incoming ID against the configured validator.

           Returns True if no validator is configured or if the validator
           accepts the value.
           """
           if self._config.validator is None:
               return True
           return self._config.validator(value)

4. Modify `process_request` (lines 488-494). The current logic:

       incoming = self._get_incoming_header_value(req)
       if incoming is not None and self._is_trusted_source(req.remote_addr):
           req.context.correlation_id = incoming
       else:
           req.context.correlation_id = self._config.generator()

   Becomes:

       incoming = self._get_incoming_header_value(req)
       if incoming is not None and self._is_trusted_source(req.remote_addr):
           if self._is_valid_id(incoming):
               req.context.correlation_id = incoming
           else:
               logger.debug(
                   "Correlation ID failed validation, "
                   "generating new ID: %s",
                   incoming,
               )
               req.context.correlation_id = self._config.generator()
       else:
           req.context.correlation_id = self._config.generator()

   This keeps `process_request` flat (one level of additional nesting within
   the existing trusted-source branch) and delegates the validator-presence
   check to `_is_valid_id`.

### Stage D: Update documentation

1. **`docs/users-guide.md`**: Update the "Header retrieval and trusted source
   behaviour" section (lines 51-69) to describe validation as a step between
   trust checking and acceptance. Update the `validator` section (lines
   141-176) to note that validation is now active during request processing and
   that failures trigger generation with a DEBUG log. Move task 2.3.2 from
   "will be added" to "implemented" in the Current Status section (lines
   215-233).

2. **`docs/falcon-correlation-id-middleware-design.md`**: Record any design
   decisions in the appropriate section if implementation details warrant it.

3. **`docs/roadmap.md`**: Check off all subtasks under 2.3.2 (lines 86-91).

### Stage E: Quality gates

Run all quality checks:

    set -o pipefail
    make check-fmt 2>&1 | tee /tmp/falcon-correlate-check-fmt.log
    make typecheck 2>&1 | tee /tmp/falcon-correlate-typecheck.log
    make lint 2>&1 | tee /tmp/falcon-correlate-lint.log
    make test 2>&1 | tee /tmp/falcon-correlate-test.log

## Concrete steps

1. **Write the ExecPlan file** to
   `docs/execplans/2-3-2-integrate-validation-into-request-processing.md`.

2. **Create unit test file**
   `src/falcon_correlate/unittests/test_validation_integration.py`:
   - Follow the `create_test_client` factory pattern from
     `test_generator_invocation.py`.
   - Extend the `_MiddlewareKwargs` TypedDict to include `validator`.
   - Add test classes: `TestValidationWhenNoValidatorConfigured`,
     `TestValidationWithValidatorAccepting`,
     `TestValidationWithValidatorRejecting`,
     `TestValidationLogging`,
     `TestValidationNotCalledWhenUnnecessary`.

3. **Add BDD scenarios** to `tests/bdd/middleware.feature`:
   - Add `# Validation scenarios` section with 4 scenarios.

4. **Add BDD step definitions** to `tests/bdd/test_middleware_steps.py`:
   - Add Given steps for creating apps with validators and trusted sources.
   - Add Then steps for verifying validation behaviour.
   - Reuse existing step definitions where possible.

5. **Run tests to confirm new tests fail** (TDD red phase):

       set -o pipefail
       make test 2>&1 | tee /tmp/falcon-correlate-test-red.log

6. **Add `import logging`** to `src/falcon_correlate/middleware.py`
   (after `import ipaddress`, line 5).

7. **Add module-level logger** to `src/falcon_correlate/middleware.py`
   (after `DEFAULT_HEADER_NAME`, around line 19):

       logger = logging.getLogger(__name__)

8. **Add `_is_valid_id` method** to `CorrelationIDMiddleware`
   (after `_is_trusted_source`, after line 463).

9. **Modify `process_request`** (lines 488-494):
   - Add validation check within the trusted-source branch.
   - Add DEBUG log on validation failure.

10. **Run tests to confirm they pass** (TDD green phase):

        set -o pipefail
        make test 2>&1 | tee /tmp/falcon-correlate-test-green.log

11. **Update `docs/users-guide.md`**:
    - Update request processing flow description.
    - Clarify validator integration in the validator section.
    - Update Current Status section.

12. **Update `docs/roadmap.md`**:
    - Mark all 2.3.2 subtasks as `[x]`.

13. **Run full quality gate suite**:

        set -o pipefail
        make check-fmt 2>&1 | tee /tmp/falcon-correlate-check-fmt.log
        make typecheck 2>&1 | tee /tmp/falcon-correlate-typecheck.log
        make lint 2>&1 | tee /tmp/falcon-correlate-lint.log
        make test 2>&1 | tee /tmp/falcon-correlate-test.log

14. **Commit changes** with a descriptive message referencing the task.

## Validation and acceptance

Quality criteria:

- Tests: `make test` passes. All new tests in
  `test_validation_integration.py` fail before implementation and pass after.
  All new BDD scenarios in `middleware.feature` fail before and pass after. All
  existing tests pass throughout.
- Lint: `make lint` passes with no warnings.
- Formatting: `make check-fmt` passes.
- Type checking: `make typecheck` passes.
- Markdown: `make markdownlint` passes.

Behavioural acceptance:

- A Falcon app configured with
  `CorrelationIDMiddleware(validator=default_uuid_validator, trusted_sources=["127.0.0.1"])`
   that receives a request with header `X-Correlation-ID: not-a-uuid` from
  `127.0.0.1` will generate a new correlation ID (a UUIDv7 hex string) instead
  of accepting `not-a-uuid`.
- The same app receiving a valid UUID from a trusted source will accept and
  propagate it.
- An app with no validator configured will accept any string from a trusted
  source (backwards compatible).

## Idempotence and recovery

All steps are safe to re-run. If a test fails after implementation, adjust the
implementation or tests and re-run `make test`. If formatting fails, run
`make fmt` and rerun `make check-fmt`. The logger addition is idempotent
(adding `logging.getLogger(__name__)` twice would be a code issue caught by
linting, but the edit is a single insertion).

## Artifacts and notes

Keep the log files created via `tee` for evidence of passing checks:

- `/tmp/falcon-correlate-check-fmt.log`
- `/tmp/falcon-correlate-typecheck.log`
- `/tmp/falcon-correlate-lint.log`
- `/tmp/falcon-correlate-test.log`

## Interfaces and dependencies

No new public interfaces. The following private method is added to
`CorrelationIDMiddleware`:

    def _is_valid_id(self, value: str) -> bool:
        """Check incoming ID against the configured validator.

        Returns True if no validator is configured or if the validator
        accepts the value.
        """

Dependencies: Standard library `logging` module only (no new external
dependencies).

## Files to modify

- `src/falcon_correlate/middleware.py` — Edit — Add logger, `_is_valid_id`
  method, modify `process_request`.
- `src/falcon_correlate/unittests/test_validation_integration.py` — Create —
  Unit tests for validation integration.
- `tests/bdd/middleware.feature` — Edit — Add validation scenarios.
- `tests/bdd/test_middleware_steps.py` — Edit — Add validation step
  definitions.
- `docs/users-guide.md` — Edit — Document validation behaviour.
- `docs/roadmap.md` — Edit — Mark 2.3.2 complete.
- `docs/execplans/2-3-2-integrate-validation-into-request-processing.md` —
  Create — This ExecPlan file.

## Revision note (required when editing an ExecPlan)

2026-02-09: Initial draft created to cover roadmap task 2.3.2 — integrate
validation into request processing with DEBUG logging, unit tests, BDD tests,
and documentation updates.

2026-02-09: Marked the plan complete, recorded execution details, and updated
progress, decisions, surprises, and outcomes to reflect the implemented
validation integration and quality gate results.
