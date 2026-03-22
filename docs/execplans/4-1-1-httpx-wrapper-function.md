# Implement httpx wrapper function (4.1.1)

This Execution Plan (ExecPlan) is a living document. The sections
`Constraints`, `Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`,
`Decision log`, and `Outcomes & retrospective` must be kept up to date as work
proceeds.

Status: COMPLETE

## Purpose / big picture

The middleware stores correlation IDs in a `ContextVar` (`correlation_id_var`)
during Falcon request handling. Task 4.1.1 adds wrapper functions around
`httpx.request` that automatically inject this correlation ID as an outgoing
`X-Correlation-ID` header, enabling downstream service traceability without
manual header management. This is the first step in the "downstream
propagation" milestone (roadmap section 4).

The design specification[^1] describes the wrapper function approach in section
3.5.1.4 and provides a reference implementation in section 4.3 (lines 879-921).

Success is observable when:

- `request_with_correlation_id(method, url, **kwargs)` is a public function
  in `src/falcon_correlate/httpx.py`.
- `async_request_with_correlation_id(method, url, **kwargs)` is its async
  variant in the same module.
- When `correlation_id_var` is set, both functions inject the
  `X-Correlation-ID` header into the outgoing request.
- When `correlation_id_var` is not set, neither function adds the header.
- Existing headers passed by the caller are preserved in all cases.
- Both functions are importable from the package root:
  `from falcon_correlate import request_with_correlation_id`.
- Both functions appear in `falcon_correlate.__all__`.
- `httpx` is an optional dependency: the module can be imported without
  `httpx` installed, but calling the functions requires it.
- All existing tests continue to pass unchanged.
- New unit tests (pytest) and behavioural tests (pytest-bdd) cover every
  code path.
- `docs/users-guide.md` documents the httpx propagation wrapper functions.
- `docs/roadmap.md` shows task 4.1.1 as complete.
- All quality gates pass (`make check-fmt`, `make typecheck`, `make lint`,
  `make test`).

## Constraints

- Follow test-driven development (TDD): write tests first, then implement.
- Do not change existing public function signatures or existing tests.
- `httpx` is an optional dependency, not a runtime requirement. The wrapper
  module must be importable without `httpx` installed. Use lazy imports inside
  function bodies.
- Use `DEFAULT_HEADER_NAME` from `middleware.py` rather than hardcoding the
  header string.
- Use the roadmap function names (`request_with_correlation_id` and
  `async_request_with_correlation_id`), not the design doc names.
- Follow the project's British English spelling conventions in
  documentation.
- Markdown must wrap at 80 columns (paragraphs and bullets); code blocks
  at 120 columns. Use `-` for list bullets.
- Python line length limit is 88 characters.
- Max function args is 4 (ruff PLR0913). The wrapper signatures
  `(method, url, **kwargs)` have 2 positional + kwargs and are compliant.

## Tolerances (exception triggers)

- Scope: if implementation requires more than 12 files or 400 net lines
  changed, stop and escalate.
- Interface: if any existing public API signature must change, stop and
  escalate.
- Dependencies: if a new runtime dependency (beyond dev-only `httpx`) is
  required, stop and escalate.
- Iterations: if tests still fail after two fix attempts for the same root
  cause, stop and escalate with findings.
- Ambiguity: if the lazy import of `httpx` inside
  `falcon_correlate/httpx.py` causes a self-import conflict, rename the module
  and escalate the naming decision.

## Risks

- Risk: naming conflict between module `falcon_correlate/httpx.py` and the
  third-party `httpx` package when `import httpx` is called inside the module.
  Severity: high. Likelihood: low (Python 3 uses absolute imports by default;
  the module is `falcon_correlate.httpx`, not `httpx`). Mitigation: use
  `import httpx as _httpx` inside function bodies for clarity. Verify with a
  test that the import resolves to the third-party package.

- Risk: test isolation -- context variables set in tests may leak between
  tests. Severity: medium. Likelihood: medium. Mitigation: all unit tests that
  call `.set()` on context variables must run inside
  `contextvars.copy_context().run()` via the `isolated_context` fixture. BDD
  steps must include a `_reset_context_variables` autouse fixture.

- Risk: `ANN401` ruff rule triggers on `**kwargs: typ.Any`. Severity: low.
  Likelihood: certain. Mitigation: suppress with `# noqa: ANN401` -- the
  wrapper passes through arbitrary httpx keyword arguments and cannot narrow
  the type.

- Risk: type checker cannot resolve `httpx.Response` return annotation
  when `httpx` is only conditionally imported. Severity: low. Likelihood: low.
  Mitigation: `httpx` is imported under `if typ.TYPE_CHECKING:` at module
  level, and `from __future__ import annotations` defers annotation evaluation.

## Progress

- [x] (2026-03-05) Write ExecPlan.
- [x] (2026-03-05) Add `httpx` to dev dependencies in `pyproject.toml`;
  run `uv sync --group dev`.
- [x] (2026-03-05) Add unit tests (TDD red phase).
- [x] (2026-03-05) Add BDD feature file and step definitions (TDD red
  phase).
- [x] (2026-03-05) Implement `request_with_correlation_id` and
  `async_request_with_correlation_id` in `src/falcon_correlate/httpx.py`.
- [x] (2026-03-05) Implement `_prepare_headers` private helper.
- [x] (2026-03-05) Export both public functions in `__init__.py` and
  `__all__`.
- [x] (2026-03-05) Run tests to confirm they pass (TDD green phase).
- [x] (2026-03-05) Update `docs/users-guide.md` with httpx propagation
  section.
- [x] (2026-03-05) Record design decisions in design document
  (Appendix A.6).
- [x] (2026-03-05) Mark task 4.1.1 complete in `docs/roadmap.md`.
- [x] (2026-03-05) Run all quality gates (`make check-fmt`,
  `make typecheck`, `make lint`, `make test`). `make markdownlint` skipped
  (tool not available in this environment; CI-only).

## Surprises & discoveries

- Observation: ruff rule PLR0402 flags `import unittest.mock as mock`
  and wants `from unittest import mock`. The project's `banned-from` list bans
  `from unittest.mock import ...` (direct submodule imports), but
  `from unittest import mock` is fine because it imports from `unittest`, not
  from `unittest.mock`. The existing test files
  (`test_validation_integration.py`, `test_generator_invocation.py`) already
  use `from unittest import mock`. Impact: used the `from unittest import mock`
  pattern in all new test files.

- Observation: ruff PLR2004 (magic value in comparison) triggered on
  `assert captured_kwargs["timeout"] == 5`. Impact: extracted a module-level
  `_EXPECTED_TIMEOUT = 5` constant for test assertions.

- Observation: `asyncio.get_event_loop()` in the BDD async step caused
  a `DeprecationWarning` in Python 3.12. Impact: replaced with
  `asyncio.new_event_loop()` / `loop.run_until_complete()` / `loop.close()`
  pattern to avoid the warning.

- Observation: the module naming of `falcon_correlate/httpx.py` did not
  cause any self-import conflict. Python 3 absolute imports correctly resolve
  `import httpx` to the third-party package, not to the module itself
  (`falcon_correlate.httpx`). The `import httpx as _httpx` alias was kept for
  additional clarity.

## Decision log

- Decision: Create a new module `src/falcon_correlate/httpx.py` rather than
  adding functions to `middleware.py`. Rationale: httpx propagation is a
  distinct feature domain. `middleware.py` already encapsulates middleware
  configuration, validation, UUID generation, the log filter, and the
  middleware class. A separate module follows the "group by feature, not layer"
  convention (AGENTS.md) and isolates the httpx optional dependency.

- Decision: Use lazy `import httpx as _httpx` inside function bodies.
  Rationale: `httpx` is not a runtime dependency. The module itself can be
  safely imported (and re-exported from `__init__.py`) without `httpx`
  installed. Users get a standard `ImportError` only when they call the
  function, which is the expected Python pattern for optional integrations
  (mirrors the structlog approach for dev-only testing).

- Decision: Extract a private `_prepare_headers` helper function.
  Rationale: the header preparation logic (pop headers from kwargs, convert to
  mutable dict, inject correlation ID) is identical between the sync and async
  variants. Extracting it eliminates duplication and makes both public
  functions thinner and easier to read.

- Decision: Use `DEFAULT_HEADER_NAME` constant from `middleware.py`.
  Rationale: keeps the header name in sync with the middleware default. The
  wrapper provides the common case; users needing a custom header name can use
  the custom transport approach (task 4.1.2) or write their own wrapper.

- Decision: Use roadmap function names (`request_with_correlation_id`,
  `async_request_with_correlation_id`) rather than the design doc names
  (`client_request_with_correlation_id`,
  `async_client_request_with_correlation_id`). Rationale: the roadmap
  represents the accepted requirements; the design doc names are illustrative
  examples.

## Outcomes & retrospective

The httpx wrapper function implementation is complete. Two public functions
(`request_with_correlation_id` and `async_request_with_correlation_id`) are
defined in `src/falcon_correlate/httpx.py` alongside a private
`_prepare_headers` helper, and exported via `__init__.py` as part of the public
API.

New tests: 19 unit tests in `test_httpx_wrapper.py` covering four categories
(sync wrapper, async wrapper, `_prepare_headers` helper, and public API
exports) plus 4 BDD scenarios in `httpx_propagation.feature`. Total test suite:
292 passed, 11 skipped (CI-only workflow tests).

All quality gates passed: `make check-fmt`, `make lint`, `make typecheck`,
`make test`.

Key lessons: (1) The `from unittest import mock` pattern is the correct one for
this project, not `import unittest.mock as mock`. (2) Python 3 absolute imports
handle the `falcon_correlate/httpx.py` vs third-party `httpx` naming without
conflict. (3) Use `asyncio.new_event_loop()` instead of deprecated
`asyncio.get_event_loop()` in non-async test contexts.

## Context and orientation

The project is `falcon-correlate`, a correlation ID middleware for the Falcon
web framework. The package source lives under `src/falcon_correlate/`. The
middleware class (`CorrelationIDMiddleware`) and the two context variables
(`correlation_id_var`, `user_id_var`) are defined in
`src/falcon_correlate/middleware.py`. The public API is exported from
`src/falcon_correlate/__init__.py` via an `__all__` list.

Unit tests are co-located in `src/falcon_correlate/unittests/` and follow a
class-based pattern with descriptive docstrings (one test file per concern).
Shared unit-test fixtures (`request_response_factory`, `isolated_context`,
`logger_with_capture`) live in `src/falcon_correlate/unittests/conftest.py`.
Behavioural tests live in `tests/bdd/` as Gherkin `.feature` files with
accompanying `test_*_steps.py` step definition files using `pytest-bdd`. Step
definition files use a `Context` TypedDict for passing state between steps.

The design specification[^1] describes the wrapper function approach in section
3.5.1.4 and provides a reference implementation in section 4.3.

[^1]: `docs/falcon-correlation-id-middleware-design.md`

### Key files

- `src/falcon_correlate/httpx.py` -- Create -- Wrapper functions and
  `_prepare_headers` helper.
- `src/falcon_correlate/__init__.py` -- Edit -- Add new functions to
  imports and `__all__`.
- `src/falcon_correlate/unittests/test_httpx_wrapper.py` -- Create --
  Unit tests.
- `tests/bdd/httpx_propagation.feature` -- Create -- BDD feature file.
- `tests/bdd/test_httpx_propagation_steps.py` -- Create -- BDD step
  definitions.
- `docs/users-guide.md` -- Edit -- Add httpx propagation section; update
  current status.
- `docs/roadmap.md` -- Edit -- Mark 4.1.1 subtasks as `[x]`.
- `docs/falcon-correlation-id-middleware-design.md` -- Edit -- Record
  implementation decisions (Appendix A.6).

### Existing patterns to reuse

- Unit test structure: class-based tests with descriptive docstrings, as
  in `test_context_variables.py` and `test_structlog_integration.py`.
- `isolated_context` fixture from
  `src/falcon_correlate/unittests/conftest.py` for context variable isolation.
- `pytest.importorskip("structlog")` pattern at module level for optional
  dependency tests, as in `test_structlog_integration.py`.
- BDD step definitions: `Context` TypedDict,
  `scenarios("feature_name.feature")`, `@given`/`@when`/`@then` decorators, as
  in `test_context_variables_steps.py`.
- Public export test pattern from `test_context_variables.py`.

## Plan of work

### Stage A: Add httpx dev dependency

Edit `pyproject.toml` to add `"httpx>=0.27,<1"` to the
`[dependency-groups] dev` list. Run `uv sync --group dev` to install.

### Stage B: Add unit tests (TDD red phase)

Create `src/falcon_correlate/unittests/test_httpx_wrapper.py` with the
following test classes and methods:

**1. `TestRequestWithCorrelationId`** -- sync wrapper:

- `test_adds_correlation_id_header_when_set` -- Set `correlation_id_var`
  in an isolated context, mock `httpx.request`, call wrapper, assert headers
  contain `X-Correlation-ID`.
- `test_does_not_add_header_when_context_is_empty` -- Context var at
  default, assert header absent.
- `test_preserves_existing_caller_headers` -- Pass existing headers,
  assert both preserved and correlation ID added.
- `test_handles_none_headers_argument` -- Pass `headers=None`, assert
  no error.
- `test_passes_through_additional_kwargs` -- Pass `json=...`, assert
  forwarded.
- `test_converts_immutable_headers_to_mutable` -- Pass
  `MappingProxyType`, assert no error.

**2. `TestAsyncRequestWithCorrelationId`** -- async wrapper:

- Mirror of sync tests 1-5 above, using `httpx.AsyncClient` mock and
  `@pytest.mark.asyncio`.

**3. `TestPrepareHeaders`** -- private `_prepare_headers` helper:

- `test_extracts_headers_from_kwargs` -- Headers popped from kwargs.
- `test_returns_empty_dict_when_no_headers` -- Empty kwargs returns `{}`.
- `test_injects_correlation_id` -- Context var set, header present.
- `test_does_not_inject_when_no_correlation_id` -- `None`, header absent.

**4. `TestHttpxWrapperExports`** -- public API:

- `test_request_with_correlation_id_in_all`
- `test_async_request_with_correlation_id_in_all`
- `test_request_with_correlation_id_importable`
- `test_async_request_with_correlation_id_importable`

### Stage C: Add BDD scenarios (TDD red phase)

Create `tests/bdd/httpx_propagation.feature`:

    Feature: httpx correlation ID propagation
      The httpx wrapper functions propagate the correlation ID
        to downstream services automatically by injecting it
        as a header in outgoing requests

      Scenario: Wrapper injects correlation ID header
      Scenario: Wrapper preserves existing caller headers
      Scenario: Wrapper does not add header when context is empty
      Scenario: Async wrapper injects correlation ID header

Create `tests/bdd/test_httpx_propagation_steps.py` with step definitions
following the `test_context_variables_steps.py` pattern.

### Stage D: Implement production code

Create `src/falcon_correlate/httpx.py` with:

1. `request_with_correlation_id(method, url, **kwargs)` -- sync wrapper.
2. `async_request_with_correlation_id(method, url, **kwargs)` -- async
   wrapper.
3. `_prepare_headers(kwargs)` -- private helper for header enrichment.

### Stage E: Update public exports

Edit `src/falcon_correlate/__init__.py`:

- Add import from `.httpx`.
- Add both function names to `__all__`.

### Stage F: Update documentation

1. `docs/users-guide.md` -- Add "httpx propagation" section.
2. `docs/falcon-correlation-id-middleware-design.md` -- Add Appendix A.6.
3. `docs/roadmap.md` -- Mark 4.1.1 subtasks as `[x]`.

### Stage G: Quality gates

Run all quality gates using `set -o pipefail` and `tee`:

    set -o pipefail
    make check-fmt 2>&1 | tee /tmp/fc-check-fmt.log
    make typecheck 2>&1 | tee /tmp/fc-typecheck.log
    make lint 2>&1 | tee /tmp/fc-lint.log
    make test 2>&1 | tee /tmp/fc-test.log
    make markdownlint 2>&1 | tee /tmp/fc-markdownlint.log

## Validation and acceptance

Quality criteria:

- Tests: `make test` passes. All new tests fail before implementation and
  pass after. All existing tests pass throughout.
- Lint: `make lint` passes with no new warnings.
- Formatting: `make check-fmt` passes.
- Type checking: `make typecheck` passes.
- Markdown: `make markdownlint` passes.

Behavioural acceptance:

- `from falcon_correlate import request_with_correlation_id` succeeds.
- `from falcon_correlate import async_request_with_correlation_id`
  succeeds.
- When `correlation_id_var` is set to `"test-123"`, calling
  `request_with_correlation_id("GET", url)` sends a request with header
  `X-Correlation-ID: test-123`.
- When `correlation_id_var` is not set, no `X-Correlation-ID` header is
  added.
- Existing headers passed by the caller are preserved in all cases.

## Idempotence and recovery

All steps are safe to re-run. If a test fails after implementation, adjust the
implementation or tests and re-run `make test`. If formatting fails, run
`make fmt` and re-run `make check-fmt`. The quality gate commands can be
repeated without side effects.

## Artifacts and notes

Keep the log files created via `tee` for evidence of passing checks:

- `/tmp/fc-check-fmt.log`
- `/tmp/fc-typecheck.log`
- `/tmp/fc-lint.log`
- `/tmp/fc-test.log`
- `/tmp/fc-markdownlint.log`

## Interfaces and dependencies

New public names added to `falcon_correlate.__all__`:

- `request_with_correlation_id` -- sync wrapper function.
- `async_request_with_correlation_id` -- async wrapper function.

New internal name (not exported):

- `_prepare_headers` -- private helper for header enrichment.

Dependencies: `httpx` (optional, dev-only). Not a runtime dependency. Added to
`[dependency-groups] dev` in `pyproject.toml`.

## Files to modify

- `pyproject.toml` -- Edit -- Add `httpx` to dev dependencies.
- `src/falcon_correlate/httpx.py` -- Create -- Wrapper functions.
- `src/falcon_correlate/__init__.py` -- Edit -- Add exports.
- `src/falcon_correlate/unittests/test_httpx_wrapper.py` -- Create --
  Unit tests.
- `tests/bdd/httpx_propagation.feature` -- Create -- BDD feature file.
- `tests/bdd/test_httpx_propagation_steps.py` -- Create -- BDD step
  definitions.
- `docs/users-guide.md` -- Edit -- Add httpx propagation section.
- `docs/roadmap.md` -- Edit -- Mark 4.1.1 complete.
- `docs/falcon-correlation-id-middleware-design.md` -- Edit -- Add
  Appendix A.6.
- `docs/execplans/4-1-1-httpx-wrapper-function.md` -- Create -- This
  ExecPlan file.

## Revision note (required when editing an ExecPlan)

2026-03-05: Initial draft created to cover roadmap task 4.1.1 -- implement
httpx wrapper functions with unit tests, BDD tests, and documentation updates.

2026-03-05: Marked plan complete. Updated progress, surprises, decisions, and
outcomes to reflect the implemented wrapper functions, quality gate results,
and lessons about import patterns and async event loops.
