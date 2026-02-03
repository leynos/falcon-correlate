# Support custom generator injection (2.2.2)

This Execution Plan (ExecPlan) is a living document. The sections
`Constraints`, `Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`,
`Decision log`, and `Outcomes & retrospective` must be kept up to date as work
proceeds.

Status: COMPLETE

No `PLANS.md` file exists in the repository root at the time of writing.

## Purpose / big picture

This change wires the configured generator into `process_request()` so that
correlation IDs are generated when no header is present or when the request
source is untrusted. The generator parameter and default UUIDv7 generator
already exist from tasks 1.2.2 and 2.2.1 respectively. Success is observable
when:

- Custom generators are called and their output used as the correlation ID
- The default generator is used as a fallback when no custom generator is
  provided
- Unit and BDD tests verify generator invocation behaviour
- Documentation reflects the new behaviour
- `docs/roadmap.md` shows task 2.2.2 as complete

## Constraints

- Preserve the existing generator interface: `Callable[[], str]` with no
  parameters.
- Generator must be called when:
  - No correlation ID header is present
  - The request source is not trusted (incoming ID rejected)
- Generated IDs must be stored on `req.context.correlation_id`.
- Follow test-driven development (TDD): write tests before implementation.
- Follow documentation style rules (80-column wrapping, Markdown linting).

## Tolerances (exception triggers)

- Scope: more than 10 files or more than 350 lines (net) changed requires
  escalation.
- Interface: any change to public function signatures requires escalation.
- Dependencies: any new dependencies require escalation.
- Tests: if tests fail after two fix attempts, stop and escalate.

## Risks

- Risk: Existing tests assume no correlation ID is set for untrusted sources.
  Severity: medium Likelihood: high Mitigation: update affected tests to expect
  generated IDs instead of empty context.
- Risk: BDD step definitions may need refactoring to handle generated IDs.
  Severity: low Likelihood: medium Mitigation: add new steps for verifying
  generated IDs and update existing steps as needed.

## Progress

- [x] (2026-02-01 00:00Z) Create ExecPlan document (this file).
- [x] (2026-02-01 00:05Z) Write unit tests for generator invocation.
- [x] (2026-02-01 00:10Z) Write behaviour-driven development (BDD) scenarios for
  generator behaviour.
- [x] (2026-02-01 00:15Z) Implement generator integration in `process_request()`.
- [x] (2026-02-01 00:20Z) Update documentation (users-guide, design doc).
- [x] (2026-02-01 00:25Z) Update roadmap to mark task complete.
- [x] (2026-02-01 00:30Z) Run quality gates.

## Surprises & Discoveries

- Observation: Several existing tests expected no correlation ID to be set for
  untrusted sources and missing headers. Evidence: Tests in
  `test_middleware_header_handling.py` and `test_trusted_sources.py` failed
  after implementation. Impact: Updated these tests to expect generated IDs,
  which reflects the new desired behaviour where every request gets a
  correlation ID.

## Decision log

- Decision: Generator is called for both missing headers and untrusted sources.
  Rationale: Ensures every request gets a correlation ID, maintaining
  traceability even for untrusted clients. This aligns with the design document
  §3.2.3[^1] which states, "If no correlation ID is found in the header, if the
  source is not trusted, or if an incoming ID fails validation, the middleware
  must generate a new UUIDv7." Date/Author: 2026-02-01 DevBoxer.
- Decision: Generated IDs are not validated. Rationale: The generator is
  trusted to produce valid IDs. Validation (task 2.3) applies only to incoming
  IDs from external sources. Date/Author: 2026-02-01 DevBoxer.

## Outcomes & retrospective

The custom generator injection feature is now complete. The configured generator
is called in `process_request()` whenever an incoming correlation ID is not
accepted (missing header, empty header, or untrusted source). The default
`default_uuid7_generator` is used as a fallback when no custom generator is
provided.

Key files modified:

- `src/falcon_correlate/middleware.py` - Added generator call in else branch
- `src/falcon_correlate/unittests/test_generator_invocation.py` - New test file
- `src/falcon_correlate/unittests/test_middleware_header_handling.py` - Updated
- `src/falcon_correlate/unittests/test_trusted_sources.py` - Updated
- `tests/bdd/middleware.feature` - Added generator scenarios
- `tests/bdd/test_middleware_steps.py` - Added generator step definitions
- `docs/users-guide.md` - Updated behaviour documentation
- `docs/falcon-correlation-id-middleware-design.md` - Added §4.6.7
- `docs/roadmap.md` - Marked task 2.2.2 complete

All quality gates passed: `make check-fmt`, `make typecheck`, `make lint`,
`make test`, and `make markdownlint`.

## Context and orientation

The `CorrelationIDMiddleware` in `src/falcon_correlate/middleware.py` already
accepts a `generator` parameter (task 1.2.2) and has a working
`default_uuid7_generator` (task 2.2.1). The generator is stored in
`self._config.generator` but is not yet called in `process_request()`. The
current behaviour sets `req.context.correlation_id` only when a trusted source
provides a valid header; otherwise the context remains unset.

Key files:

- `src/falcon_correlate/middleware.py` - Core middleware implementation
- `src/falcon_correlate/unittests/test_middleware_configuration.py` - Unit
  tests for middleware configuration
- `tests/bdd/middleware.feature` - BDD feature file
- `tests/bdd/test_middleware_steps.py` - BDD step definitions
- `docs/users-guide.md` - User-facing documentation
- `docs/roadmap.md` - Implementation roadmap

## Plan of work

Stage A writes tests first following TDD. Add unit tests that verify the
generator is called when the header is missing or the source is untrusted, and
that custom generator output is used as the correlation ID. Add BDD scenarios
that exercise generator behaviour end-to-end.

Stage B implements the generator integration. Modify `process_request()` to
call `self._config.generator()` in the else branch when the incoming ID is not
accepted. This is a minimal change to the existing conditional logic.

Stage C updates documentation. Revise `docs/users-guide.md` to reflect that
generator invocation is now active, add an implementation note to
`docs/falcon-correlation-id-middleware-design.md` section 4.6, and mark task
2.2.2 complete in `docs/roadmap.md`.

Stage D runs quality gates to ensure all checks pass.

## Concrete steps

1. Write unit tests for generator invocation.

   Add a new test class to
   `src/falcon_correlate/unittests/test_middleware_configuration.py` or create
   `src/falcon_correlate/unittests/test_generator_invocation.py`:

   - Test generator called when header missing
   - Test generator called when source untrusted
   - Test custom generator output used as correlation ID
   - Test default generator used when custom not provided

2. Write BDD scenarios for generator behaviour.

   Add scenarios to `tests/bdd/middleware.feature`:

   - Scenario: Generator called when header is missing
   - Scenario: Generator called for untrusted source
   - Scenario: Custom generator output is used

3. Run tests to confirm they fail before implementation.

   ```bash
   set -o pipefail
   pytest -k "generator" -v 2>&1 | tee /tmp/falcon-correlate-generator-tests.log
   ```

4. Implement generator integration.

   Edit `src/falcon_correlate/middleware.py` to modify `process_request()`:

   ```python
   incoming = self._get_incoming_header_value(req)

   if incoming is not None and self._is_trusted_source(req.remote_addr):
       req.context.correlation_id = incoming
   else:
       req.context.correlation_id = self._config.generator()
   ```

5. Update existing tests that expect no correlation ID for untrusted sources.

   Some existing BDD scenarios and unit tests may need updating to expect
   generated IDs instead of empty context.

6. Update documentation.

   - `docs/users-guide.md`: Update header retrieval section and current status
   - `docs/falcon-correlation-id-middleware-design.md`: Add note in §4.6
   - `docs/roadmap.md`: Mark task 2.2.2 as complete

7. Run quality gates.

   ```bash
   set -o pipefail
   make fmt 2>&1 | tee /tmp/falcon-correlate-fmt.log
   make check-fmt 2>&1 | tee /tmp/falcon-correlate-check-fmt.log
   make typecheck 2>&1 | tee /tmp/falcon-correlate-typecheck.log
   make lint 2>&1 | tee /tmp/falcon-correlate-lint.log
   make test 2>&1 | tee /tmp/falcon-correlate-test.log
   make markdownlint 2>&1 | tee /tmp/falcon-correlate-markdownlint.log
   ```

## Validation and acceptance

- Unit tests: generator invocation tests pass and verify correct behaviour.
- Behavioural tests: BDD scenarios for generator behaviour pass.
- Documentation: `docs/users-guide.md` reflects active generator invocation,
  `docs/roadmap.md` shows 2.2.2 complete.
- Quality gates: `make check-fmt`, `make typecheck`, `make lint`, `make test`,
  and `make markdownlint` all pass.

## Idempotence and recovery

All steps are safe to re-run. If tests fail after implementation, adjust the
implementation or tests and re-run. If documentation linting fails, run
`make fmt` and rerun `make markdownlint`.

## Artifacts and notes

Keep log files created via `tee` for evidence of passing checks.

## Interfaces and dependencies

The following interface remains unchanged:

```python
class CorrelationIDMiddleware:
    def __init__(
        self,
        *,
        config: CorrelationIDConfig | None = None,
        **kwargs: object,
    ) -> None: ...

    def process_request(self, req: falcon.Request, resp: falcon.Response) -> None:
        # Now calls self._config.generator() when needed
        ...
```

Dependencies:

- Task 1.2.2 (complete): Generator parameter acceptance
- Task 2.2.1 (complete): Default UUIDv7 generator implementation

## Revision note (required when editing an ExecPlan)

2026-02-01: Initial draft created to cover roadmap task 2.2.2.

2026-02-01: Marked the plan complete, recorded execution details, and updated
progress, surprises, and outcomes to reflect the implemented generator
integration and quality gate results.

[^1]: Design document reference:
    [docs/falcon-correlation-id-middleware-design.md](../falcon-correlation-id-middleware-design.md),
    section 3.2.3 "ID Generation".
