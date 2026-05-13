# Validate optional Celery integration (4.2.4)

This Execution Plan (ExecPlan) is a living document. The sections
`Constraints`, `Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`,
`Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work
proceeds.

Status: COMPLETE

## Purpose / big picture

Roadmap item 4.2.4 validates that Celery support remains an optional
integration. A developer should be able to run the project test suite in an
environment where the `celery` package is absent and see Celery-dependent unit
tests and Behaviour-Driven Development (BDD) tests reported as skipped, not as
collection errors or import failures.

The change matters because `falcon-correlate` exposes Celery propagation as an
optional extra. Consumers who do not install `falcon-correlate[celery]` should
still be able to install, import, test, and use the library's non-Celery
features. Success is observable when:

- `import falcon_correlate` succeeds without Celery installed;
- the package module `falcon_correlate.celery` remains import-safe without
  Celery installed;
- Celery-specific unit test modules are skipped during collection when Celery
  is unavailable;
- Celery-specific BDD step modules are skipped during collection when Celery is
  unavailable;
- the same Celery tests still execute normally when Celery is installed in the
  development environment;
- `docs/falcon-correlation-id-middleware-design.md` records the skip policy and
  why Celery absence is a supported test environment;
- `docs/users-guide.md` continues to describe Celery as an optional dependency,
  and is updated only if implementation discovers missing consumer-facing
  behaviour; and
- `docs/roadmap.md` marks 4.2.4 complete only after implementation,
  documentation, and validation are finished.

This plan was approved on 2026-05-09 and has now been implemented.

## Constraints

- Do not implement this plan until it has explicit approval.
- Keep Celery optional. `celery` must remain in the `celery` optional extra and
  development dependency group, not in the base runtime dependencies.
- Preserve import safety. `import falcon_correlate` and
  `import falcon_correlate.celery` must not require Celery to be installed.
- Preserve current Celery behaviour when Celery is installed, including
  publish-time propagation, worker context setup and cleanup, explicit
  configuration through `configure_celery_correlation(app)`, idempotent signal
  registration, and the `rpc://` result-backend exception.
- Use `pytest.importorskip("celery")` or a small shared equivalent for
  Celery-only tests. Do not replace missing-Celery skips with broad exception
  swallowing.
- Do not add a new external dependency for this validation.
- Keep the implementation scoped to roadmap item 4.2.4. Do not introduce new
  Celery propagation features.
- Write or update tests before changing production code or documentation that
  claims new behaviour.
- Use `pytest` for unit tests and `pytest-bdd` for behavioural tests where
  Celery behaviour is externally observable through task publish or worker
  lifecycle contracts.
- Use `hypothesis` only for invariant-style coverage. The main missing-Celery
  skip contract is an environment and collection contract, so property tests
  are not expected unless the implementation introduces a reusable classifier
  or marker-generation function with a meaningful input range.
- Record design decisions in
  `docs/falcon-correlation-id-middleware-design.md`.
- Update `docs/users-guide.md` only if the implementation changes or clarifies
  consumer-facing Celery installation, activation, or test-running behaviour.
- Check off roadmap item 4.2.4 only after implementation and validation are
  complete.
- Follow the Markdown style requirements in `AGENTS.md`: wrap prose at 80
  columns, wrap code blocks at 120 columns, use dashes for bullets, and run the
  Markdown gates before committing documentation changes.
- Run project quality gates sequentially. Do not run formatting, linting,
  typechecking, or tests in parallel.

## Tolerances

- Scope: if implementation needs changes to more than 8 files or more than 220
  net lines, stop and ask whether to split the skip validation from any test
  helper refactor.
- Public API: if the work appears to require changing public function names,
  signatures, exports, or optional extras, stop and escalate.
- Runtime behaviour: if the missing-Celery test strategy requires changing
  production Celery signal behaviour, stop and present alternatives.
- Dependency model: if a new package, pytest plugin, or build tool is needed,
  stop and request approval.
- Test environment: if a reliable missing-Celery validation cannot be achieved
  without creating a second dependency environment, stop and document the
  available options.
- Test iterations: if the targeted Celery validation still fails after three
  focused attempts, stop, update the `Decision Log`, and ask for direction.
- Documentation scope: if the users' guide needs more than a short note about
  optional Celery test behaviour, stop and confirm the intended audience for
  that guidance.
- Continuous Integration (CI) scope: if validating this properly requires a new
  CI job that installs the package without development dependencies, stop and
  ask whether that CI change belongs in 4.2.4 or a follow-up item.

## Risks

- Risk: the existing Celery tests already use `pytest.importorskip("celery")`,
  so an implementation may be only a documentation change unless the
  missing-dependency path is explicitly tested. Severity: medium. Likelihood:
  high. Mitigation: add a targeted validation for collection/import behaviour
  when Celery is unavailable, or document why the existing import-skip guards
  are already sufficient and how they were verified.

- Risk: Celery is currently included in the development dependency group, so
  normal `make test` always runs with Celery installed after `make build`.
  Severity: medium. Likelihood: high. Mitigation: design the missing-Celery
  validation as a focused test or command that simulates Celery absence without
  disrupting the normal development environment.

- Risk: directly importing Celery test modules in a meta-test may cause
  `pytest.skip.Exception` to escape in a way that confuses linters, xdist, or
  collection. Severity: medium. Likelihood: medium. Mitigation: prefer
  pytest-supported collection checks or a small subprocess command that runs
  selected Celery tests with Celery import blocked, and assert skipped output
  rather than importing test modules ad hoc.

- Risk: a subprocess-based missing-Celery check may be brittle if it relies on
  exact pytest summary wording. Severity: low. Likelihood: medium. Mitigation:
  assert stable signals such as return code `0`, the presence of `skipped`, and
  the absence of `ERROR` or `FAILED`, not an exact count unless the collected
  file list is fixed.

- Risk: broadening BDD skip helpers could accidentally skip feature files that
  should continue running when Celery is installed. Severity: medium.
  Likelihood: low. Mitigation: keep the skip guard at the top of
  Celery-specific step modules and preserve installed-Celery behavioural tests
  as normal executable tests.

## Progress

- [x] (2026-05-08T19:16:45Z) Loaded the `execplans`, `leta`,
  `commit-message`, `pr-creation`, and `en-gb-oxendict-style` skills needed for
  planning, repository navigation, committing, and draft Pull Request (PR)
  preparation.
- [x] (2026-05-08T19:16:45Z) Confirmed the starting branch was not the main
  branch and renamed it to `4-2-4-validate-optional-celery-integration`.
- [x] (2026-05-08T19:16:45Z) Created a context pack for Wyvern agent team
  findings and recorded their documentation and test-surface summaries.
- [x] (2026-05-08T19:16:45Z) Reviewed `docs/roadmap.md`,
  `docs/falcon-correlation-id-middleware-design.md`, `docs/users-guide.md`,
  `pyproject.toml`, `Makefile`, `src/falcon_correlate/celery.py`, and the
  existing Celery unit and BDD tests.
- [x] (2026-05-08T19:16:45Z) Drafted this pre-implementation ExecPlan.
- [x] (2026-05-09T11:48:01Z) Received explicit approval to implement the
  planned functionality.
- [x] (2026-05-09T11:48:01Z) Reconfirmed that each current Celery-specific
  unit test module and BDD step module calls `pytest.importorskip("celery")`
  before importing Celery symbols.
- [x] (2026-05-12T15:09:08Z) Addressed review comments by deriving the project
  root from `pyproject.toml`, adding the missing PYTHONPATH environment edge
  case, relaxing stderr validation to error-marker checks, and defining
  Markdown acronyms on first use.
- [x] (2026-05-09T11:48:01Z) Added
  `src/falcon_correlate/unittests/test_optional_celery_dependency.py` with
  child-process validation for import safety and missing-Celery test skips.
- [x] (2026-05-09T11:48:01Z) Observed the first missing-Celery child pytest run
  fail the parent assertion because pytest exits with code 5 when all selected
  modules skip during collection.
- [x] (2026-05-09T11:48:01Z) Adjusted the child pytest run to include a
  passing non-Celery sentinel test, matching a normal suite where non-Celery
  tests continue while Celery-only modules skip.
- [x] (2026-05-09T11:48:01Z) Updated the Celery design appendix and users'
  guide with the optional-dependency validation decision and consumer-facing
  import-safety note.
- [x] (2026-05-09T11:50:52Z) Ran targeted installed-Celery validation; the
  existing Celery unit and BDD tests reported `33 passed in 0.23s`.
- [x] (2026-05-09T11:50:52Z) Ran the new optional-Celery validation directly;
  it reported `2 passed in 5.71s`.
- [x] (2026-05-09T11:50:52Z) Checked off roadmap item 4.2.4 after
  implementation and targeted validation.
- [x] Implement the approved plan.
- [x] (2026-05-09T11:50:52Z) Ran all required validation gates and recorded
  the results in this plan.
- [x] (2026-05-09T11:50:52Z) Updated `docs/roadmap.md` to check off 4.2.4
  after implementation.
- [x] (2026-05-10T00:25:41Z) Addressed review findings by isolating package
  import checks in separate subprocesses, deriving Celery test modules from
  filesystem globs, injecting child-process environment mappings, and replacing
  broad pytest-output substring checks with a normalized exact snapshot.
- [x] (2026-05-10T00:25:41Z) Expanded the optional-Celery validation module
  docstring and roadmap entry to capture the subprocess strategy, pytest
  collection relationship, import-safety outcome, and design-doc A.11 link.
- [x] (2026-05-13T11:50:37Z) Addressed review feedback by making the
  missing-Celery child subprocess working directory explicit and rooted at the
  repository root.

## Surprises & Discoveries

- Observation: all current Celery unit and BDD step modules already call
  `pytest.importorskip("celery")` before importing Celery symbols. Evidence:
  the guard is present in
  `src/falcon_correlate/unittests/test_celery_publish_signal.py`,
  `src/falcon_correlate/unittests/test_celery_worker_signal.py`,
  `src/falcon_correlate/unittests/test_celery_configuration.py`,
  `tests/bdd/test_celery_publish_signal_steps.py`,
  `tests/bdd/test_celery_worker_signal_steps.py`, and
  `tests/bdd/test_celery_configuration_steps.py`. Impact: the implementation
  should focus on explicit validation and documentation of the
  optional-dependency test contract, not on inventing a different skip
  mechanism unless the current guards are proven insufficient.

- Observation: normal project validation installs Celery because the Makefile
  runs `uv sync --group dev`, and the dev group includes `celery>=5,<6`.
  Evidence: `Makefile` target `test` depends on `build`, and `pyproject.toml`
  includes Celery in `[dependency-groups].dev`. Impact: the missing-Celery path
  needs a targeted validation strategy outwith the normal `make test`
  environment.

- Observation: a pytest subprocess that selects only Celery-dependent modules
  while Celery is blocked reports `6 skipped` but exits with code 5 because no
  runnable tests were collected. Impact: the validation includes a generated
  one-test non-Celery sentinel so the child process represents a normal mixed
  test suite and can assert exit code 0 plus skipped Celery modules.

- Observation: pytest quiet output for modules skipped during collection does
  not emit one `s` progress marker per skipped module. Evidence: after adding
  the exact output assertion, the child output normalised to `. [100%]`
  followed by `1 passed, 6 skipped in <duration>`. Impact: the snapshot records
  pytest's actual collection-skip output instead of expecting per-module
  progress markers.

## Decision Log

- Decision: Treat 4.2.4 as a validation and documentation task unless targeted
  testing proves a skip guard is missing. Rationale: the existing tests already
  use `pytest.importorskip("celery")`, and changing working test modules
  without evidence would add churn rather than improve the optional integration
  contract. Date/Author: 2026-05-08T19:16:45Z / Codex with Wyvern agent
  findings.

- Decision: Do not check off `docs/roadmap.md` while drafting this plan.
  Rationale: the user explicitly stated that the plan must be approved before
  implementation. The roadmap item should be closed only after implementation
  and validation complete. Date/Author: 2026-05-08T19:16:45Z / Codex.

- Decision: Keep missing-Celery validation separate from the normal `make test`
  dependency environment unless approval adds a no-Celery CI lane. Rationale:
  normal gates intentionally install development dependencies, while 4.2.4
  needs proof of behaviour when one optional dependency is absent. Date/Author:
  2026-05-08T19:16:45Z / Codex.

- Decision: Use a child-process import blocker rather than uninstalling Celery
  or creating a second dependency environment. Rationale: a temporary
  `sitecustomize.py` on the child `PYTHONPATH` can make only `celery` imports
  unavailable while preserving the existing project environment, which gives
  realistic pytest collection behaviour without mutating shared dependencies.
  Date/Author: 2026-05-09T11:48:01Z / Codex.

- Decision: Keep the missing-Celery validation as subprocess harness coverage
  rather than a Hypothesis property test. Rationale: the behaviour is an
  environment and pytest collection contract, not an invariant over a range of
  generated inputs. Date/Author: 2026-05-09T11:48:01Z / Codex.

- Decision: Derive Celery test modules with repository-relative glob patterns
  rather than maintaining a fixed tuple of paths. Rationale: the validation
  should automatically include future Celery-specific unit modules and BDD step
  modules that follow the existing naming convention. Date/Author:
  2026-05-10T00:25:41Z / Codex.

## Outcomes & Retrospective

Roadmap item 4.2.4 is implemented. The final change keeps the existing
`pytest.importorskip("celery")` guards in the Celery unit and BDD step modules
and adds explicit validation in
`src/falcon_correlate/unittests/test_optional_celery_dependency.py`.

The missing-Celery validation uses a subprocess with a temporary
`sitecustomize.py` import hook that raises `ModuleNotFoundError` for `celery`
and `celery.*`. That child process proves `falcon_correlate` and
`falcon_correlate.celery` remain import-safe without Celery, then runs pytest
against the Celery-specific test modules and verifies they are skipped without
collection errors.

No production Celery behaviour, public API, optional extra, or dependency group
changed. The users' guide now clarifies that importing the package without the
Celery extra is safe and leaves Celery signal integration inactive. The design
appendix records the skip strategy, the subprocess import blocker, and the
pytest exit-code discovery for all-skipped selected runs.

## Context and orientation

The repository implements `falcon-correlate`, a Falcon middleware package that
tracks correlation IDs for HTTP requests, logging, downstream HTTP clients, and
Celery tasks. A correlation ID is a request-scoped identifier used to connect
logs and downstream work back to the originating request. Celery is a task
queue library. In this package, Celery support is optional: users install it
with the `celery` extra only if they need task propagation.

The key package file is `src/falcon_correlate/celery.py`. It defines:

- `propagate_correlation_id_to_celery(**kwargs)`, which copies the ambient
  `correlation_id_var` value into Celery publish properties when appropriate;
- `setup_correlation_id_in_worker(task=...)`, which reads a task request's
  `correlation_id` and binds it to `correlation_id_var` for the task body;
- `clear_correlation_id_in_worker(**kwargs)`, which restores the prior
  `correlation_id_var` value after task execution;
- `_maybe_connect_celery_publish_signal()`, which imports `celery.signals`
  dynamically and connects the publish handler only when Celery exists;
- `_maybe_connect_celery_worker_signals()`, which does the same for worker
  lifecycle handlers;
- `_maybe_connect_celery_signals()`, which connects all supported handlers; and
- `configure_celery_correlation(app)`, which provides an explicit public setup
  call while keeping registration idempotent.

The relevant test files are:

- `src/falcon_correlate/unittests/test_celery_publish_signal.py`;
- `src/falcon_correlate/unittests/test_celery_worker_signal.py`;
- `src/falcon_correlate/unittests/test_celery_configuration.py`;
- `tests/bdd/celery_publish_signal.feature`;
- `tests/bdd/test_celery_publish_signal_steps.py`;
- `tests/bdd/celery_worker_signal.feature`;
- `tests/bdd/test_celery_worker_signal_steps.py`;
- `tests/bdd/celery_configuration.feature`; and
- `tests/bdd/test_celery_configuration_steps.py`.

The Celery test modules currently place `pytest.importorskip("celery")` before
Celery imports. That is the correct high-level pattern because it lets pytest
report a controlled skip when the optional dependency is unavailable.

The relevant configuration files are:

- `pyproject.toml`, where Celery is declared under
  `[project.optional-dependencies]` as `celery = ["celery>=5,<6"]` and in the
  development dependency group for the normal local test environment;
- `Makefile`, where `make test` runs `uv run pytest -v -n auto` after building
  the development environment; and
- `uv.lock`, which records the resolved development dependency graph.

The relevant documentation files are:

- `docs/roadmap.md`, where 4.2.4 is now checked off with both the
  missing-Celery skip and import-safety outcomes;
- `docs/falcon-correlation-id-middleware-design.md`, especially appendix
  sections A.8, A.9, A.10, and A.11 for Celery design decisions;
- `docs/users-guide.md`, especially the "Celery propagation" section that
  describes optional installation and `configure_celery_correlation(app)`; and
- `docs/complexity-antipatterns-and-refactoring-strategies.md`, which should
  be treated as a general design guardrail against adding unnecessary helper
  layers or tangled conditional code.

## Relevant documentation and skills

Keep these project documents open while implementing:

- `docs/roadmap.md`;
- `docs/falcon-correlation-id-middleware-design.md`;
- `docs/complexity-antipatterns-and-refactoring-strategies.md`;
- `docs/users-guide.md`;
- `docs/documentation-style-guide.md`;
- `docs/execplans/4-2-1-celery-task-publish-signal-handler.md`;
- `docs/execplans/4-2-2-celery-worker-signal-handlers.md`; and
- `docs/execplans/4-2-3-celery-configuration-utilities.md`.

Use these skills:

- `/home/leynos/.codex/skills/execplans/SKILL.md` for keeping this plan
  self-contained and current.
- `/home/leynos/.codex/skills/leta/SKILL.md` for code navigation before
  modifying the Celery module or tests.
- `/home/leynos/.codex/skills/commit-message/SKILL.md` when committing each
  approved, gated change.
- `/home/leynos/.codex/skills/pr-creation/SKILL.md` when creating or updating
  the draft pull request.
- `/home/leynos/.codex/skills/en-gb-oxendict/SKILL.md` when editing
  documentation or PR prose.

Rust skills are not relevant because this item touches Python tests and
Markdown documentation only.

## Plan of work

### Milestone 1: confirm the current optional-dependency surface

Start by re-reading the current Celery package and test modules. Confirm that
each Celery-specific unit test file and BDD step file performs a module-level
skip before importing Celery symbols. Also confirm that
`src/falcon_correlate/celery.py` uses dynamic imports for Celery and returns
without raising `ImportError` when Celery is absent.

Use `leta` for symbol navigation in Python code where possible, and use `rg`
only for literal string searches such as `pytest.importorskip("celery")`.

Go/no-go point: if any Celery-specific test imports Celery before its skip
guard, fix that test file first. If all guards are already correct, do not
rewrite them for style only.

### Milestone 2: add explicit missing-Celery validation

Add a focused unit-level validation that proves Celery absence is handled
cleanly. Prefer the smallest approach that is reliable under pytest and xdist.
Two acceptable approaches are:

1. Add a meta-test that runs pytest in a subprocess against the Celery-specific
   test files while blocking Celery imports with a temporary import hook.
   Assert return code `0`, skipped output, and no collection errors.
2. Add a smaller in-process test helper that exercises the skip guard in the
   Celery test modules without importing Celery, if pytest exposes the needed
   behaviour cleanly and without brittle private APIs.

The subprocess approach is more likely to match real user behaviour because it
exercises pytest collection. Keep it targeted to the Celery unit and BDD step
modules rather than the full suite.

The validation must cover:

- the happy path, where Celery is installed and the existing Celery unit and
  BDD tests still run under normal `make test`;
- the unhappy path, where Celery is unavailable and Celery-dependent tests are
  reported as skipped;
- package import safety without Celery; and
- absence of collection errors for BDD step modules when Celery is missing.

If the missing-Celery validation introduces a reusable helper, add direct unit
coverage for the helper. If it is only a test subprocess harness, keep the test
names and assertions clear enough that no property test is needed.

### Milestone 3: update documentation

Update `docs/falcon-correlation-id-middleware-design.md` with an appendix entry
for task 4.2.4. Record that Celery test modules use pytest's import-skip
mechanism at module import time, that normal development validation still runs
Celery tests because the dev group includes Celery, and that the missing-Celery
path is validated separately.

Review `docs/users-guide.md`. If the implementation does not change
consumer-facing installation or runtime behaviour, avoid adding noisy prose. If
the implementation clarifies a useful consumer-facing fact, such as how
optional dependency absence appears in downstream test suites, add a short note
in the Celery propagation section.

Update this ExecPlan as the implementation proceeds. Record findings in
`Surprises & Discoveries`, decisions in `Decision Log`, command outputs in
`Artifacts and notes`, and final validation in `Outcomes & Retrospective`.

Do not update `docs/roadmap.md` yet in this milestone unless implementation and
validation are already complete.

### Milestone 4: run targeted and full validation

Run targeted tests first, then the full gates. Use `tee` for long outputs and
run gates sequentially.

The minimum targeted tests are:

```bash
UV_CACHE_DIR=.uv-cache UV_TOOL_DIR=.uv-tools uv run pytest -v \
  src/falcon_correlate/unittests/test_celery_publish_signal.py \
  src/falcon_correlate/unittests/test_celery_worker_signal.py \
  src/falcon_correlate/unittests/test_celery_configuration.py \
  tests/bdd/test_celery_publish_signal_steps.py \
  tests/bdd/test_celery_worker_signal_steps.py \
  tests/bdd/test_celery_configuration_steps.py
```

Also run the new missing-Celery validation test directly. If that test is a
subprocess harness, document the exact command it launches and the expected
skip summary in this plan.

After targeted validation passes, run:

```bash
make check-fmt 2>&1 | tee /tmp/check-fmt-falcon-correlate-4-2-4-validate-optional-celery-integration.out
```

```bash
make typecheck 2>&1 | tee /tmp/typecheck-falcon-correlate-4-2-4-validate-optional-celery-integration.out
```

```bash
make lint 2>&1 | tee /tmp/lint-falcon-correlate-4-2-4-validate-optional-celery-integration.out
```

```bash
make test 2>&1 | tee /tmp/test-falcon-correlate-4-2-4-validate-optional-celery-integration.out
```

For Markdown changes, also run:

```bash
make fmt 2>&1 | tee /tmp/fmt-falcon-correlate-4-2-4-validate-optional-celery-integration.out
```

```bash
make markdownlint 2>&1 | tee /tmp/markdownlint-falcon-correlate-4-2-4-validate-optional-celery-integration.out
```

```bash
make nixie 2>&1 | tee /tmp/nixie-falcon-correlate-4-2-4-validate-optional-celery-integration.out
```

If `make fmt` changes files, inspect the diff and rerun `make check-fmt`
afterwards.

### Milestone 5: close the roadmap item and commit

Only after implementation, documentation, and validation pass, update
`docs/roadmap.md` so item 4.2.4 and its child task are checked. Then update
this plan's `Progress`, `Decision Log`, `Outcomes & Retrospective`, and
`Artifacts and notes` sections with final evidence.

Commit the implementation as a focused change using the file-based commit
message workflow from the `commit-message` skill. If a later refactor is
needed, make it a separate approved, gated commit.

## Concrete steps

All commands in this section run from the repository root:

```bash
cd /home/leynos/.lody/repos/github---leynos---falcon-correlate/worktrees/1578ca20-3bcd-4717-acce-fa648d48c4db
```

Confirm branch and status:

```bash
git branch --show-current
git status --short --branch
```

Expected branch output:

```plaintext
4-2-4-validate-optional-celery-integration
```

Find existing skip guards:

```bash
rg -n 'pytest\.importorskip\("celery"\)' src/falcon_correlate/unittests tests/bdd
```

Expected result: one match in each Celery-specific unit and BDD step module.

Inspect package dynamic imports:

```bash
rg -n 'import_module\("celery|import_module\("celery\.signals|except ImportError' src/falcon_correlate/celery.py
```

Expected result: dynamic import and `ImportError` handling in the Celery module
rather than unconditional runtime imports.

Run targeted installed-Celery tests:

```bash
UV_CACHE_DIR=.uv-cache UV_TOOL_DIR=.uv-tools uv run pytest -v \
  src/falcon_correlate/unittests/test_celery_publish_signal.py \
  src/falcon_correlate/unittests/test_celery_worker_signal.py \
  src/falcon_correlate/unittests/test_celery_configuration.py \
  tests/bdd/test_celery_publish_signal_steps.py \
  tests/bdd/test_celery_worker_signal_steps.py \
  tests/bdd/test_celery_configuration_steps.py
```

Expected result: tests pass or report expected skips if Celery is deliberately
absent in the current environment.

Run the new missing-Celery validation test directly. Record the exact command
after the test file is written. The expected result is a zero exit status and a
pytest summary that includes skipped Celery tests, with no collection errors.

Run the required quality gates sequentially:

```bash
make check-fmt 2>&1 | tee /tmp/check-fmt-falcon-correlate-4-2-4-validate-optional-celery-integration.out
```

```bash
make typecheck 2>&1 | tee /tmp/typecheck-falcon-correlate-4-2-4-validate-optional-celery-integration.out
```

```bash
make lint 2>&1 | tee /tmp/lint-falcon-correlate-4-2-4-validate-optional-celery-integration.out
```

```bash
make test 2>&1 | tee /tmp/test-falcon-correlate-4-2-4-validate-optional-celery-integration.out
```

For documentation changes, also run:

```bash
make fmt 2>&1 | tee /tmp/fmt-falcon-correlate-4-2-4-validate-optional-celery-integration.out
```

```bash
make markdownlint 2>&1 | tee /tmp/markdownlint-falcon-correlate-4-2-4-validate-optional-celery-integration.out
```

```bash
make nixie 2>&1 | tee /tmp/nixie-falcon-correlate-4-2-4-validate-optional-celery-integration.out
```

Historical note: the initial implementation commit staged the approved plan and
additional implementation files after the validation gates passed. Future
follow-up commits should stage the changed files, inspect the staged diff, and
commit using a message file:

```bash
git add docs/execplans/4-2-4-validate-optional-celery-integration.md
git diff --cached
```

The first implementation commit was made after approval. Later follow-up
commits should follow the same file-based commit-message workflow.

## Validation and acceptance

The implementation is accepted only when all of the following are true:

- `pytest` reports Celery-specific tests as skipped, not failed or errored,
  when Celery imports are unavailable.
- `pytest` runs the existing Celery unit and BDD tests successfully in the
  normal development environment where Celery is installed.
- `import falcon_correlate` succeeds without Celery installed.
- `import falcon_correlate.celery` succeeds without Celery installed and does
  not connect signals.
- Existing Celery publish behaviour still preserves Celery's generated
  correlation ID when no ambient request correlation ID exists.
- Existing Celery publish behaviour still uses the ambient request correlation
  ID when one exists and the result backend is not `rpc://`.
- Existing worker behaviour still exposes the task request correlation ID
  during task execution and restores the previous ambient context afterwards.
- `docs/falcon-correlation-id-middleware-design.md` records the 4.2.4 design
  decision.
- `docs/users-guide.md` is either unchanged because no consumer-facing
  behaviour changed, or updated with a concise note where useful.
- `docs/roadmap.md` checks off 4.2.4 only after the implementation is complete.
- `make check-fmt`, `make typecheck`, `make lint`, and `make test` pass.
- Markdown gates for changed docs pass: `make markdownlint` and `make nixie`.

Expected final gate summaries should show zero failures. Record the final
summary lines in `Artifacts and notes` before marking the plan complete.

## Idempotence and recovery

Most implementation steps are additive and safe to repeat. Running pytest or
Makefile gates multiple times should not change source files, except `make fmt`
may reformat Markdown or Python files. If `make fmt` changes files, inspect the
diff before continuing.

If the missing-Celery validation uses a subprocess import hook, keep that hook
inside a test-scoped temporary file or command argument so it cannot affect the
developer's real environment. Do not uninstall Celery from the shared
development environment to simulate absence.

If a test run leaves `.pytest_cache`, `.coverage`, or temporary files behind,
do not remove unrelated files. Use existing project clean targets only when
needed and only after checking for unrelated user work.

If implementation discovers that the current `pytest.importorskip("celery")`
guards already fully satisfy the requirement, the recovery path is to keep code
unchanged, document the validation evidence, and close 4.2.4 with the smallest
possible test or documentation update that proves the contract.

## Artifacts and notes

Wyvern agent findings from 2026-05-08:

- Celery is optional in `pyproject.toml` and also installed by the dev group.
- `src/falcon_correlate/celery.py` is already written to be import-safe when
  Celery is missing.
- The three Celery unit test files and three Celery BDD step files already use
  `pytest.importorskip("celery")`.
- The main gap is explicit validation of the missing-Celery path, because the
  standard `make test` path installs Celery before running tests.

Validation evidence will be appended here during implementation.

Validation evidence appended during implementation:

- The direct optional-Celery test command initially reported one pass and one
  failure because the child pytest process returned code 5 for an all-skipped
  selected test set.
- After adding a generated sentinel test to the child process, the same direct
  command reported `2 passed in 14.09s`.
- `uv run pytest -v
  src/falcon_correlate/unittests/test_celery_publish_signal.py
  src/falcon_correlate/unittests/test_celery_worker_signal.py
  src/falcon_correlate/unittests/test_celery_configuration.py
  tests/bdd/test_celery_publish_signal_steps.py
  tests/bdd/test_celery_worker_signal_steps.py
  tests/bdd/test_celery_configuration_steps.py` reported `33 passed in 0.23s`.
- `uv run pytest -v
  src/falcon_correlate/unittests/test_optional_celery_dependency.py` reported `2
   passed in 5.71s`.
- `make fmt` passed after wrapping one long ExecPlan evidence line and moving
  one Python-only type annotation import behind `TYPE_CHECKING`.
- `make check-fmt` reported `50 files already formatted`.
- `make typecheck` reported `All checks passed!`.
- `make lint` reported `All checks passed!`.
- `make test` reported `353 passed, 11 skipped in 8.33s`.
- `make markdownlint` reported `Summary: 0 error(s)`.
- `make nixie` reported `All diagrams validated successfully!`.
- Follow-up validation after review changes:
  `uv run pytest -v src/falcon_correlate/unittests/test_optional_celery_dependency.py`
   reported `7 passed in 6.43s`.
- Follow-up `make check-fmt` reported `50 files already formatted`.
- Follow-up `make typecheck` reported `All checks passed!`.
- Follow-up `make lint` reported `All checks passed!`.
- Follow-up `make test` reported `358 passed, 11 skipped in 9.80s`.
- Follow-up `make markdownlint` reported `Summary: 0 error(s)`.
- Follow-up `make nixie` reported `All diagrams validated successfully!`.
- Review-comment validation:
  `uv run pytest -v src/falcon_correlate/unittests/test_optional_celery_dependency.py`
   reported `10 passed in 6.89s`.
- Review-comment `make check-fmt` reported `50 files already formatted`.
- Review-comment `make typecheck` reported `All checks passed!`.
- Review-comment `make lint` reported `All checks passed!`.
- Review-comment `make test` reported `361 passed, 11 skipped in 9.65s`.
- Review-comment `make markdownlint` reported `Summary: 0 error(s)`.
- Review-comment `make nixie` reported `All diagrams validated successfully!`.
- Explicit child-CWD validation:
  `uv run pytest -v src/falcon_correlate/unittests/test_optional_celery_dependency.py`
   reported `10 passed in 7.20s`.
- Explicit child-CWD `make check-fmt` reported `50 files already formatted`.
- Explicit child-CWD `make typecheck` reported `All checks passed!`.
- Explicit child-CWD `make lint` reported `All checks passed!`.
- Explicit child-CWD `make test` reported `361 passed, 11 skipped in 10.48s`.

## Interfaces and dependencies

This work should not add new public runtime interfaces. The existing public
interfaces must remain:

```python
def propagate_correlation_id_to_celery(**kwargs: object) -> None: ...
def setup_correlation_id_in_worker(*, task: object | None = None, **_: object) -> None: ...
def clear_correlation_id_in_worker(**_: object) -> None: ...
def configure_celery_correlation[CeleryAppT](app: CeleryAppT) -> CeleryAppT: ...
```

The existing dependency model must remain:

```toml
[project.optional-dependencies]
celery = ["celery>=5,<6"]

[dependency-groups]
dev = [
    "celery>=5,<6",
]
```

The test skip interface should remain pytest-native:

```python
import pytest

celery = pytest.importorskip("celery")
```

If repetition across Celery test modules becomes a maintenance problem, an
approved implementation may introduce a tiny test-only helper under `tests/` or
`src/falcon_correlate/unittests/`, but it must not become a runtime dependency
or public API.

Revision note, 2026-05-08: Initial pre-implementation draft created from
`docs/roadmap.md` item 4.2.4, the Celery design appendix, the users' guide, and
Wyvern agent findings. This establishes the approval gate and does not
implement or close the roadmap item.
