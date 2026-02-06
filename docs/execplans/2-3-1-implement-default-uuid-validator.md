# Implement default UUID validator (2.3.1)

This Execution Plan (ExecPlan) is a living document. The sections
`Constraints`, `Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`,
`Decision log`, and `Outcomes & retrospective` must be kept up to date as work
proceeds.

Status: COMPLETE

## Purpose / big picture

This change implements a default universally unique identifier (UUID) validator
function that validates incoming correlation IDs against the standard UUID
format (any version). The validator enables the middleware to reject malformed
or excessively long IDs from trusted sources, triggering new ID generation
instead of propagating invalid data.

Success is observable when:

- `default_uuid_validator(id: str) -> bool` function exists and is exported.
- The function returns `True` for valid UUID strings (any version, with or
  without hyphens).
- The function returns `False` for malformed, empty, or excessively long IDs.
- Unit and BDD tests cover all validation scenarios.
- Documentation reflects the new behaviour.
- `docs/roadmap.md` shows task 2.3.1 as complete.
- All quality gates pass (`make check-fmt`, `make typecheck`, `make lint`,
  `make test`).

## Constraints

- Preserve the existing public API; only add `default_uuid_validator` as a new
  export from `falcon_correlate.__init__`.
- Maintain Python compatibility for the supported range (`>=3.12`).
- Use only the standard library `uuid` module for validation (no new
  dependencies).
- The validator must accept standard UUID format (any version 1-8, with or
  without hyphens).
- The validator must reject malformed strings and excessively long inputs
  (>36 characters for hyphenated, >32 for hex-only).
- Follow documentation style rules (80-column wrapping, Markdown linting, no
  `|` characters inside table cells).
- Follow test-driven development (TDD): write tests first, then implement.

## Tolerances (exception triggers)

- Scope: more than 8 files or more than 200 lines (net) changed requires
  escalation.
- Interface: any change to existing public function signatures requires
  escalation.
- Dependencies: any new external dependency requires escalation.
- Tests: if tests fail after two fix attempts, stop and escalate.
- Ambiguity: if UUID format requirements conflict with the design document,
  stop and present options with trade-offs.

## Risks

- Risk: Overly strict validation rejects valid upstream IDs.
  Severity: medium. Likelihood: low. Mitigation: accept both hyphenated
  (8-4-4-4-12) and hex-only (32 chars) UUID formats, any version 1-8.
- Risk: Performance impact from regex or parsing on every request.
  Severity: low. Likelihood: low. Mitigation: use stdlib `uuid.UUID()` parsing
  which is implemented in C and fast; add length check first as early exit.
- Risk: Edge cases around case sensitivity.
  Severity: low. Likelihood: medium. Mitigation: UUID parsing is
  case-insensitive by design; document and test both cases.

## Progress

- [x] (2026-02-03 00:00Z) Research and scope confirmation.
- [x] (2026-02-03 00:10Z) Add unit tests for valid universally unique identifier
      (UUID) formats.
- [x] (2026-02-03 00:10Z) Add unit tests for invalid/malformed formats.
- [x] (2026-02-03 00:15Z) Add BDD scenarios for validator behaviour.
- [x] (2026-02-03 00:20Z) Implement `default_uuid_validator` function.
- [x] (2026-02-03 00:20Z) Export from `falcon_correlate.__init__`.
- [x] (2026-02-03 00:25Z) Update `docs/users-guide.md`.
- [x] (2026-02-03 00:25Z) Update
      `docs/falcon-correlation-id-middleware-design.md` (not needed).
- [x] (2026-02-03 00:25Z) Mark task 2.3.1 complete in `docs/roadmap.md`.
- [x] (2026-02-03 00:30Z) Run all quality gates.

## Surprises & Discoveries

- Observation: BDD step definition for empty string validation required special
  handling. Evidence: pytest-bdd's parser could not match
  `When the validator checks ""` because the empty quotes created ambiguity.
  Impact: Added a separate step `When the validator checks an empty string` to
  handle this edge case cleanly.

## Decision log

- Decision: Accept both hyphenated UUID format
  (`xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`) and hex-only format
  (`xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`). Rationale: The design doc specifies
  "standard UUID format (any version)" and both formats are commonly used. The
  stdlib `uuid.UUID()` constructor accepts both. Date/Author: 2026-02-03.
- Decision: Use stdlib `uuid.UUID()` for validation rather than regex.
  Rationale: The stdlib handles edge cases correctly, is well-tested, and is
  implemented in C for performance. It validates structure, version bits, and
  variant bits. Date/Author: 2026-02-03.
- Decision: Reject inputs longer than 36 characters as an early exit.
  Rationale: Prevents denial of service (DoS) via excessively long strings; 36
  is the max length for a hyphenated UUID. Date/Author: 2026-02-03.

## Outcomes & retrospective

The default UUID validator is now implemented using the stdlib `uuid.UUID()`
constructor for validation. The function accepts both hyphenated and hex-only
UUID formats (any version 1-8), is case-insensitive, and rejects empty,
malformed, or excessively long strings. New unit tests (27 test cases) and BDD
scenarios (5 scenarios) cover all validation edge cases. Documentation in
`docs/users-guide.md` now describes the `default_uuid_validator` function and
provides usage examples. The roadmap shows task 2.3.1 as complete. All quality
gates passed, including formatting, linting, type checking, and tests (160
tests total, 149 passed, 11 skipped for continuous integration (CI)-only tests).

## Context and orientation

The `default_uuid_validator` will be added to
`src/falcon_correlate/middleware.py` alongside `default_uuid7_generator`. It
will be exported from `src/falcon_correlate/__init__.py`. The validator
signature is `Callable[[str], bool]`, matching the existing `validator`
parameter type in `CorrelationIDConfig`.

Key files:

- `src/falcon_correlate/middleware.py` - Implementation location (lines 21-39
  show the generator pattern to follow).
- `src/falcon_correlate/__init__.py` - Public exports.
- `src/falcon_correlate/unittests/uuid7_helpers.py` - Existing UUID validation
  helpers for reference.
- `src/falcon_correlate/unittests/test_uuid7_generator.py` - Test pattern to
  follow.
- `tests/bdd/uuidv7.feature` - BDD pattern to follow.
- `docs/users-guide.md` - User documentation (lines 141-162 show validator
  section).
- `docs/roadmap.md` - Task tracking (lines 80-85 for task 2.3.1).

## Plan of work

### Stage A: Research and scope confirmation

Confirm the UUID validation requirements from design-doc section 3.2.4:

- Validate standard UUID format (any version).
- Return `False` for malformed or excessively long IDs.
- Simple default validator that can be overridden with custom validators.

### Stage B: Add tests before implementation

Create comprehensive test coverage following TDD:

1. Unit tests in `src/falcon_correlate/unittests/test_uuid_validator.py`:
   - Valid hyphenated UUIDs (versions 1, 4, 7).
   - Valid hex-only UUIDs (32 characters, no hyphens).
   - Valid UUIDs with uppercase characters.
   - Invalid: empty string.
   - Invalid: too short.
   - Invalid: too long (>36 characters).
   - Invalid: wrong format (missing hyphens in wrong places).
   - Invalid: non-hex characters.
   - Invalid: None type (if passed incorrectly).

2. BDD scenarios in `tests/bdd/uuid_validator.feature`:
   - Scenario: Valid UUID is accepted.
   - Scenario: Invalid format is rejected.
   - Scenario: Excessively long input is rejected.

3. BDD step definitions in `tests/bdd/test_uuid_validator_steps.py`.

### Stage C: Implement the validator

Add `default_uuid_validator` to `src/falcon_correlate/middleware.py`:

```python
def default_uuid_validator(value: str) -> bool:
    """Validate that a string is a valid UUID (any version).

    Accepts both hyphenated (8-4-4-4-12) and hex-only (32-character) UUID
    formats. Case-insensitive.

    Parameters
    ----------
    value : str
        The string to validate.

    Returns
    -------
    bool
        True if the value is a valid UUID, False otherwise.

    """
    # Early exit for excessively long or empty strings
    if not value or len(value) > 36:
        return False

    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False
```

### Stage D: Export and document

1. Add `default_uuid_validator` to `src/falcon_correlate/__init__.py` exports.

2. Update `docs/users-guide.md`:
   - Document the new `default_uuid_validator` function.
   - Show example usage with the middleware.
   - Update the "Current Status" section.

3. Update `docs/falcon-correlation-id-middleware-design.md` section 4.x if
   implementation details warrant documentation.

4. Mark task 2.3.1 complete in `docs/roadmap.md` (lines 80-85).

### Stage E: Quality gates

Run all quality checks:

```bash
set -o pipefail
make check-fmt 2>&1 | tee /tmp/falcon-correlate-check-fmt.log
make typecheck 2>&1 | tee /tmp/falcon-correlate-typecheck.log
make lint 2>&1 | tee /tmp/falcon-correlate-lint.log
make test 2>&1 | tee /tmp/falcon-correlate-test.log
```

## Concrete steps

1. **Create unit test file**
   `src/falcon_correlate/unittests/test_uuid_validator.py`:
   - Import `default_uuid_validator` (will fail until implemented).
   - Add `TestDefaultUUIDValidator` class with test methods for all cases.

2. **Create BDD feature file** `tests/bdd/uuid_validator.feature`:
   - Add scenarios for valid UUID acceptance.
   - Add scenarios for invalid format rejection.

3. **Create BDD step definitions** `tests/bdd/test_uuid_validator_steps.py`:
   - Implement Given/When/Then steps using `pytest_bdd`.
   - Follow pattern from `tests/bdd/test_uuidv7_steps.py`.

4. **Run tests to confirm they fail** (TDD red phase):

   ```bash
   pytest -k "uuid_validator" -v
   ```

5. **Implement `default_uuid_validator`** in
   `src/falcon_correlate/middleware.py`:
   - Add function after `default_uuid7_generator` (around line 40).
   - Use `uuid.UUID()` for validation with try/except.
   - Add early exit for length check.

6. **Export from `__init__.py`**:
   - Add `default_uuid_validator` to the import and `__all__` list.

7. **Run tests to confirm they pass** (TDD green phase):

   ```bash
   pytest -k "uuid_validator" -v
   ```

8. **Update documentation**:
   - `docs/users-guide.md`: Add validator section (around line 141).
   - `docs/roadmap.md`: Mark 2.3.1 subtasks complete.

9. **Run full quality gate suite**:

   ```bash
   make check-fmt && make typecheck && make lint && make test
   ```

10. **Commit changes** with descriptive message.

## Validation and acceptance

- Unit tests: All `test_uuid_validator.py` tests pass.
- BDD tests: All `uuid_validator.feature` scenarios pass.
- Type checking: `make typecheck` passes with no errors.
- Linting: `make lint` passes.
- Formatting: `make check-fmt` passes.
- Full test suite: `make test` passes.
- Documentation: `docs/users-guide.md` documents the validator.
- Roadmap: Task 2.3.1 marked complete in `docs/roadmap.md`.

## Idempotence and recovery

All steps are safe to re-run. If a test fails after implementation, adjust the
validator or tests and re-run the focused pytest command before running the
full suite. If formatting fails, run `make fmt` and rerun `make check-fmt`.

## Artifacts and notes

Keep the log files created via `tee` for evidence of passing checks:

- `/tmp/falcon-correlate-check-fmt.log`
- `/tmp/falcon-correlate-typecheck.log`
- `/tmp/falcon-correlate-lint.log`
- `/tmp/falcon-correlate-test.log`

## Interfaces and dependencies

The following interface will exist at the end of the change:

```python
def default_uuid_validator(value: str) -> bool:
    """Return True if value is a valid UUID (any version), False otherwise."""
```

Dependencies: Standard library `uuid` module only (no new dependencies).

## Files to modify

- `src/falcon_correlate/middleware.py` - Edit - Add `default_uuid_validator`
  function
- `src/falcon_correlate/__init__.py` - Edit - Export `default_uuid_validator`
- `src/falcon_correlate/unittests/test_uuid_validator.py` - Create - Unit tests
- `tests/bdd/uuid_validator.feature` - Create - BDD scenarios
- `tests/bdd/test_uuid_validator_steps.py` - Create - BDD step definitions
- `docs/users-guide.md` - Edit - Document the validator
- `docs/roadmap.md` - Edit - Mark 2.3.1 complete

## Revision note (required when editing an ExecPlan)

2026-02-03: Initial draft created to cover roadmap task 2.3.1 - implement
default UUID validator with tests and documentation.

2026-02-03: Marked the plan complete, recorded execution details, and updated
progress, decisions, surprises, and outcomes to reflect the implemented
validator and quality gate results.

2026-02-04: Addressed PR review comments: expanded acronyms (UUID, TDD, DoS,
CI) on first use; fixed test count (160, not 161); removed first-person
pronouns from BDD step examples; hyphenated "32-character" as compound
adjective.
