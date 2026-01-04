# Implement correlation ID header retrieval

This ExecPlan is a living document. The sections `Progress`,
`Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must
be kept up to date as work proceeds.

No `PLANS.md` file exists in the repository root at the time of writing.

## Purpose / Big Picture

After this change, the middleware will read the configured correlation ID
header from incoming requests, treat missing or empty values as absent, and
persist a candidate value for later lifecycle steps. Success is observable in
unit and behavioural tests that verify header retrieval and the handling of
missing or empty headers. Documentation will describe the new behaviour, and
`docs/roadmap.md` will show task 2.1.1 as complete.

## Progress

    - [x] (2026-01-04 00:00Z) Capture requirements from the roadmap and design
      document.
    - [x] (2026-01-04 00:15Z) Add unit and behavioural tests for header
      retrieval and missing/empty handling.
    - [x] (2026-01-04 00:25Z) Implement header retrieval in
      `src/falcon_correlate/middleware.py`.
    - [x] (2026-01-04 00:35Z) Update documentation and the roadmap to reflect
      the new behaviour.
    - [x] (2026-01-04 00:45Z) Run formatting, linting, type checking, and tests
      with passing results.

## Surprises & Discoveries

    - Observation: `make fmt` initially failed due to table column count errors
      in `docs/falcon-correlation-id-middleware-design.md`.
      Evidence: markdownlint reported MD056/MD060 on the configuration options
      table until the type cells were rewritten without `|` characters.

## Decision Log

    - Decision: Treat missing, empty, or whitespace-only header values as
      absent by trimming and checking for content.
      Rationale: Prevents empty identifiers from entering the lifecycle and
      matches design doc §3.2.1 intent.
      Date/Author: 2026-01-04 Codex.
    - Decision: Store the retrieved value on `req.context.correlation_id` only
      when a non-empty header is present, leaving it unset otherwise.
      Rationale: Provides an observable effect for tests without prematurely
      generating IDs or storing placeholders.
      Date/Author: 2026-01-04 Codex.

## Outcomes & Retrospective

Header retrieval now reads the configured header, ignores missing or empty
values, and stores non-empty values on `req.context.correlation_id`. Unit and
behavioural tests cover the present, missing, and whitespace-only cases. The
roadmap and user documentation were updated, and all quality gates passed
(`make fmt`, `make check-fmt`, `make lint`, `make typecheck`, `make test`,
`make markdownlint`, and `make nixie`).

## Context and Orientation

The middleware lives in `src/falcon_correlate/middleware.py`. The
`CorrelationIDMiddleware.process_request` method now reads the header and sets
request context values when present. Unit coverage for middleware behaviour is
in `src/falcon_correlate/unittests/test_middleware.py`. Behavioural tests are
in `tests/bdd/middleware.feature` with step definitions in
`tests/bdd/test_middleware_steps.py` and shared helpers in `tests/conftest.py`.
The design guidance for this change is in
`docs/falcon-correlation-id-middleware-design.md` §3.2.1. The roadmap item to
complete is `docs/roadmap.md` task 2.1.1. The user-facing behaviour is
documented in `docs/users-guide.md`.

## Plan of Work

First, add tests that define the desired behaviour before touching the
implementation. Add unit tests that exercise `process_request` for three cases:
header present with a value, header missing, and header present but empty or
whitespace. For behavioural coverage, add a BDD scenario that makes a request
with and without the header and asserts the middleware surface (for example, a
resource that returns whether `req.context.correlation_id` is set). The tests
should initially fail because `process_request` does not set any value.

Next, implement header retrieval in `CorrelationIDMiddleware.process_request`.
Use a small helper method or local function to keep the control flow flat and
avoid introducing a Bumpy Road pattern as described in
`docs/complexity-antipatterns-and-refactoring-strategies.md`. The logic should
read the configured header (via `req.get_header`), normalise it by trimming
whitespace, and only store it when non-empty. Do not call the generator or
validator yet, because those are part of later roadmap tasks.

Then, update documentation. In `docs/users-guide.md`, describe the new header
retrieval behaviour and remove the “Correlation ID retrieval from request
headers” item from the “Current Status” list. In
`docs/falcon-correlation-id-middleware-design.md`, record the decision about
empty header handling in the implementation notes section. Finally, mark task
2.1.1 complete in `docs/roadmap.md`.

Finish by running formatting, linting, type checking, and tests. Ensure the
full suite passes and record results in the plan.

## Concrete Steps

1. Create tests before changing code.

   - Add unit tests in `src/falcon_correlate/unittests/test_middleware.py` for:
     - header present: value stored on `req.context.correlation_id`.
     - header missing: `req.context` does not expose `correlation_id`.
     - header empty or whitespace: treated as missing.
   - Add a BDD scenario in `tests/bdd/middleware.feature` and implement steps in
     `tests/bdd/test_middleware_steps.py` to assert behaviour via a Falcon
     resource that reads `req.context.correlation_id`.

2. Run targeted tests to confirm they fail before the implementation change.

   Example command (run from `/root/repo`):

       set -o pipefail
       pytest -k "header" -v 2>&1 | tee /tmp/falcon-correlate-header-tests.log

   Expected result: the new tests fail because `process_request` does not set
   the context value.

3. Implement header retrieval in `src/falcon_correlate/middleware.py`.

   - Add a private helper (for example, `_get_incoming_header_value`) that
     returns `str | None` after trimming and validating emptiness.
   - In `process_request`, call the helper and set
     `req.context.correlation_id` only when a value is returned.
   - Keep the method small and avoid nested conditionals.

4. Update documentation and roadmap.

   - `docs/users-guide.md`: document the new behaviour and update the “Current
     Status” list.
   - `docs/falcon-correlation-id-middleware-design.md`: add an implementation
     note describing empty/whitespace handling and the choice to store the
     value on `req.context.correlation_id`.
   - `docs/roadmap.md`: check off task 2.1.1 items.

5. Run formatting, linting, type checking, and the full test suite.

   Use tee and pipefail per project guidance:

       set -o pipefail
       make fmt 2>&1 | tee /tmp/falcon-correlate-fmt.log
       set -o pipefail
       make check-fmt 2>&1 | tee /tmp/falcon-correlate-check-fmt.log
       set -o pipefail
       make lint 2>&1 | tee /tmp/falcon-correlate-lint.log
       set -o pipefail
       make typecheck 2>&1 | tee /tmp/falcon-correlate-typecheck.log
       set -o pipefail
       make test 2>&1 | tee /tmp/falcon-correlate-test.log
       set -o pipefail
       make markdownlint 2>&1 | tee /tmp/falcon-correlate-markdownlint.log
       set -o pipefail
       make nixie 2>&1 | tee /tmp/falcon-correlate-nixie.log

   Expected result: all commands exit 0. If a formatter changes files, re-run
   `make check-fmt` and `make markdownlint`.

## Validation and Acceptance

- Unit tests: the new tests in
  `src/falcon_correlate/unittests/test_middleware.py` fail before the change
  and pass after it, verifying header retrieval and missing/empty handling.
- Behavioural tests: the new BDD scenario passes, demonstrating end-to-end
  behaviour when the header is present or absent.
- Documentation: `docs/users-guide.md`,
  `docs/falcon-correlation-id-middleware-design.md`, and `docs/roadmap.md` are
  updated to reflect the change.
- Quality gates: `make check-fmt`, `make lint`, `make typecheck`, and
  `make test` pass, alongside `make markdownlint` and `make nixie` for
  documentation updates.

## Idempotence and Recovery

All steps are safe to re-run. If a test fails after implementation, adjust the
code or tests and re-run the specific test file before re-running the full
suite. If documentation formatting changes introduce lint failures, run
`make fmt` and re-check.

## Artifacts and Notes

Capture short evidence of success in the log files created by `tee`. For
example, after `make test`, the tail of `/tmp/falcon-correlate-test.log` should
show all tests passing.

## Interfaces and Dependencies

Implement or update these interfaces in `src/falcon_correlate/middleware.py`:

    class CorrelationIDMiddleware:
        def _get_incoming_header_value(
            self,
            req: falcon.Request,
        ) -> str | None:
            """Return a normalised header value or None when missing/empty."""

        def process_request(
            self,
            req: falcon.Request,
            resp: falcon.Response,
        ) -> None:
            """Read the configured header and store it on req.context."""

No new external dependencies are required for this task.

## Revision note (required when editing an ExecPlan)

2026-01-04: Marked the plan steps complete, recorded the markdownlint table
fix, and summarised the outcomes and validation results now that implementation
and verification are finished.
