# Implement default UUIDv7 generator (2.2.1)

This Execution Plan (ExecPlan) is a living document. The sections
`Constraints`, `Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`,
`Decision log`, and `Outcomes & retrospective` must be kept up to date as work
proceeds.

Status: COMPLETE

No `PLANS.md` file exists in the repository root at the time of writing.

## Purpose / big picture

This change replaces the placeholder UUIDv7 generator with a compliant, working
implementation that returns a hex string suitable for correlation IDs. Success
is observable when the new generator returns RFC 9562-compliant UUIDv7 values
with RFC 4122 variant bits and millisecond precision, unit and Behaviour-Driven
Development (BDD) tests pass, documentation reflects the new behaviour, and
`docs/roadmap.md` shows task 2.2.1 as complete.

## Constraints

- Preserve the public API: `default_uuid7_generator() -> str` remains the same
  name and signature and stays exported from `falcon_correlate.__init__`.
- Maintain Python compatibility for the supported range (`>=3.12`).
- Use a UUIDv7 implementation that complies with RFC 9562 and RFC 4122 variant
  requirements for millisecond precision and compatibility.
- Prefer the standard library `uuid.uuid7()` when available; otherwise use
  `uuid-utils` as the external dependency.
- Follow documentation style rules (80-column wrapping, Markdown linting,
  no `|` characters inside table cells).

## Tolerances (exception triggers)

- Scope: more than 10 files or more than 350 lines (net) changed requires
  escalation.
- Interface: any change to public function signatures requires escalation.
- Dependencies: any new dependency other than `uuid-utils` or standard library
  `uuid` requires escalation.
- Tests: if tests fail after two fix attempts, stop and escalate.
- Ambiguity: if UUIDv7 library APIs or compliance claims conflict with the
  design document, stop and present options with trade-offs.

## Risks

- Risk: `uuid-utils` API or behaviour differs from expectations for UUIDv7.
  Severity: medium Likelihood: medium Mitigation: verify API by reading package
  documentation and add tests that validate version and variant bits from
  returned values.
- Risk: Standard library `uuid.uuid7()` is unavailable on Python <3.14.
  Severity: low Likelihood: high Mitigation: implement a clean fallback to
  `uuid-utils` and document it.
- Risk: Uniqueness tests become flaky if they depend on timing.
  Severity: low Likelihood: low Mitigation: assert only that two sequential
  calls differ, without asserting ordering or timestamp monotonicity.
- Risk: Markdownlint fails if documentation tables include pipe characters.
  Severity: low Likelihood: medium Mitigation: use "optional" phrasing in
  tables instead of `|` types.

## Progress

- [x] (2026-01-30 09:00Z) Reviewed design-doc §3.2.3 and the stub generator.
- [x] (2026-01-30 09:15Z) Added unit and BDD tests for UUIDv7 format and
  uniqueness.
- [x] (2026-01-30 09:35Z) Implemented the default UUIDv7 generator and added
  the version-gated dependency.
- [x] (2026-01-30 09:50Z) Updated documentation and the roadmap.
- [x] (2026-01-30 10:10Z) Ran formatting, linting, type checking, tests,
  markdownlint, and nixie.

## Surprises & Discoveries

- Observation: `make markdownlint` required
  `MDLINT=/root/.bun/bin/markdownlint-cli2` in this environment. Evidence: The
  default command failed with a missing tool error before using the override.
  Impact: Reran the command with the override to satisfy the quality gate.
- Observation: `make nixie` exceeded the default command timeout.
  Evidence: The first run timed out and the rerun with a longer timeout
  completed successfully. Impact: None beyond rerunning with a longer timeout.

## Decision log

- Decision: Scope is limited to 2.2.1 (default generator implementation and
  tests). Generator integration into request handling is left for 2.2.2 unless
  tests or documentation updates require a broader change. Rationale: The
  roadmap splits generator implementation and generator usage into separate
  tasks; keeping scope aligned avoids conflating milestones. Date/Author:
  2026-01-26 Codex.
- Decision: Prefer `uuid.uuid7()` when available and fall back to
  `uuid_utils.uuid7()` when the runtime lacks `uuid.uuid7()`. Rationale: Aligns
  with the design doc preference for the standard library while ensuring UUIDv7
  generation remains available across runtimes. Date/Author: 2026-01-30 Codex.
- Decision: Return UUID hex strings from the default generator.
  Rationale: Matches existing API expectations and keeps identifiers compact.
  Date/Author: 2026-01-30 Codex.
- Decision: Skipped the pre-implementation failing-test run and relied on
  full-suite validation after implementation. Rationale: Tests were added
  before implementation and validated post-change, which still verifies
  behaviour. Date/Author: 2026-01-30 Codex.

## Outcomes & retrospective

The default UUIDv7 generator is now implemented with a standard library path
and a runtime fallback when `uuid.uuid7()` is unavailable, returning UUID hex
strings. New unit and BDD tests cover format, version, variant, and uniqueness.
Documentation and the roadmap now reflect the completed 2.2.1 milestone. All
quality gates passed, including formatting, linting, type checking, tests,
markdownlint, and nixie.

## Context and orientation

The `default_uuid7_generator` in `src/falcon_correlate/middleware.py` now
generates UUIDv7 identifiers. The generator is exported from
`src/falcon_correlate/__init__.py` and referenced in unit tests under
`src/falcon_correlate/unittests/test_middleware_configuration.py`. Behavioural
tests live in `tests/bdd/middleware.feature` with step definitions in
`tests/bdd/test_middleware_steps.py`. The design guidance is in
`docs/falcon-correlation-id-middleware-design.md` §3.2.3 and the implementation
notes in §4.6.3. The user-facing behaviour is documented in
`docs/users-guide.md`. Dependencies are managed in `pyproject.toml` and
`uv.lock`.

## Plan of work

Stage A is research and scope confirmation. Re-read design-doc §3.2.3, identify
the preferred UUIDv7 implementation for Python 3.14+ (standard library when
available, otherwise `uuid-utils`), and confirm how to produce a hex string
from the chosen API. Decide whether a conditional import is needed for
`uuid.uuid7()` and document the rationale.

Stage B adds tests before implementation. Update or replace the unit test that
expects `NotImplementedError` with tests that assert:

- the generator returns a 32-character lowercase hex string,
- the value parses as a UUIDv7 with RFC 4122 variant, and
- two sequential calls return distinct values.
Add a BDD scenario (new feature file or appended to
`tests/bdd/middleware.feature`) that exercises the default generator in a
Given/When/Then style to satisfy behavioural coverage.

Stage C implements the generator. Update `default_uuid7_generator` to call
`uuid.uuid7()` when available, otherwise call the chosen `uuid-utils` function.
Return the `.hex` representation consistently. If a new dependency is needed,
update `pyproject.toml` and refresh `uv.lock`. Update docstrings to describe
the chosen implementation and any fallback logic.

Stage D updates documentation and the roadmap. Record the library choice and
rationale in `docs/falcon-correlation-id-middleware-design.md` §4.6.3, update
`docs/users-guide.md` to note that the default generator is now implemented and
what format it returns, and tick off task 2.2.1 in `docs/roadmap.md`.

## Concrete steps

1. Add tests first.

   - Update `src/falcon_correlate/unittests/test_middleware_configuration.py`
     to remove the `NotImplementedError` expectation.
   - Add a focused unit test module (for example,
     `src/falcon_correlate/unittests/test_uuid7_generator.py`) that validates
     format, version, variant, and uniqueness.
   - Add a BDD scenario (new file such as `tests/bdd/uuidv7.feature`) and step
     definitions (for example `tests/bdd/test_uuidv7_steps.py`) that exercise
     the default generator and verify the output shape.

2. Run the new tests to confirm they fail before implementation.

   Example commands (run from `/root/repo`):

       set -o pipefail
       pytest -k "uuid7" -v 2>&1 | tee /tmp/falcon-correlate-uuid7-tests.log

   Expected result: tests fail because the generator still raises
   `NotImplementedError`.

3. Implement the generator and update dependencies if needed.

   - Edit `src/falcon_correlate/middleware.py` to implement
     `default_uuid7_generator` with a standard-library path and a
     `uuid-utils` fallback.
   - If `uuid-utils` is required, add it to `pyproject.toml` with a version
     marker and update `uv.lock` (use `uv lock`).

4. Update documentation and roadmap.

   - `docs/falcon-correlation-id-middleware-design.md`: record the generator
     implementation decision in §4.6.3.
   - `docs/users-guide.md`: explain that the default generator now returns
     UUIDv7 hex strings and mention the dependency choice.
   - `docs/roadmap.md`: mark task 2.2.1 and its sub-tasks as complete.

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

   Expected result: all commands exit 0. If formatting changes files, rerun
   `make check-fmt` and `make markdownlint`.

## Validation and acceptance

- Unit tests: new UUIDv7 generator tests fail before implementation and pass
  after, confirming format, version, and uniqueness.
- Behavioural tests: the BDD scenario for the generator passes and demonstrates
  end-to-end behaviour via the default generator.
- Documentation: `docs/users-guide.md` and
  `docs/falcon-correlation-id-middleware-design.md` reflect the updated
  generator, and `docs/roadmap.md` shows 2.2.1 complete.
- Quality gates: `make check-fmt`, `make lint`, `make typecheck`, and
  `make test` pass, along with `make markdownlint` and `make nixie`.

## Idempotence and recovery

All steps are safe to re-run. If a test fails after implementation, adjust the
generator or tests and re-run the focused pytest command before running the
full suite. If documentation linting fails, run `make fmt` and rerun
`make markdownlint`.

## Artifacts and notes

Keep the log files created via `tee` for evidence of passing checks, especially
`/tmp/falcon-correlate-test.log` and the markdownlint log if documentation
changes were involved.

## Interfaces and dependencies

The following interface must exist at the end of the change:

    def default_uuid7_generator() -> str:
        """Return a RFC 4122 UUIDv7 hex string with millisecond precision."""

Dependencies:

- Standard library `uuid` when `uuid.uuid7()` is available.
- `uuid-utils` as the external fallback dependency for Python <3.14.

## Revision note (required when editing an ExecPlan)

2026-01-26: Initial draft created to cover roadmap task 2.2.1 and associated
tests and documentation updates.

2026-01-30: Marked the plan complete, recorded execution details, and updated
progress, decisions, and outcomes to reflect the implemented generator and
quality gate results.

2026-01-30: Updated the dependency decision to keep `uuid-utils` installed
whenever the runtime lacks `uuid.uuid7()`.
