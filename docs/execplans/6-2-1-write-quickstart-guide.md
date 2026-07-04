# Write quickstart guide (6.2.1)

This ExecPlan (execution plan) is a living document. The sections `Constraints`,
`Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`, `Decision Log`,
and `Outcomes & Retrospective` must be kept up to date as work proceeds.

Status: IMPLEMENTED; CodeRabbit review follow-up remains open.

## Purpose / big picture

`falcon-correlate` is a correlation ID middleware for the Falcon web framework.
The library code is complete through roadmap section 5; what remains for an
initial release is documentation (roadmap section 6). Roadmap task 6.2.1 asks
for a quickstart guide that gives a newcomer the shortest reliable path from an
empty project to a Falcon application that attaches a correlation ID to every
request and logs it.

After this change, a developer who has never seen the project can:

1. Open `docs/quickstart.md`, install the package, copy a single minimal Falcon
   WSGI application, and observe an `X-Correlation-ID` header on the response.
2. Apply the three most common configuration options (`header_name`,
   `trusted_sources`, `echo_header_in_response`) by following one worked
   example.
3. Wire `ContextualLogFilter` and `RECOMMENDED_LOG_FORMAT` into standard
   logging and see the correlation ID appear in a log line.

The distinguishing requirement of this task is that **every code example in the
guide is executed by the test suite and is guaranteed not to drift from the
prose**. The examples are shipped as real, type-checked, lint-clean Python
modules under `examples/quickstart/`; the guide embeds those exact snippets;
and a drift-guard test proves the embedded snippets and the runnable modules
are the same code.

Success is observable when:

- `docs/quickstart.md` exists, passes `make markdownlint`, and renders a single
  linear tutorial (install → minimal app → configuration → logging).
- `examples/quickstart/minimal_app.py`, `configured_app.py`, and
  `logging_setup.py` exist, are importable, and pass `make check-fmt`,
  `make lint`, and `make typecheck`.
- `make test` passes, and the new pytest, pytest-bdd, syrupy, and drift-guard
  tests fail before the corresponding implementation exists and pass after.
- The drift-guard test fails if a snippet in `docs/quickstart.md` is edited to
  diverge semantically from its source module.
- `docs/contents.md`, `README.md`, `docs/users-guide.md`,
  `docs/developers-guide.md`, the design document, and `docs/roadmap.md` are
  updated, and `docs/adr-002-tested-documentation-examples.md` records the
  tested-examples convention.
- All quality gates pass: `make check-fmt`, `make typecheck`, `make lint`,
  `make test`, `make markdownlint`, `make nixie`.

## Constraints

- Follow test-driven development: write the failing test (or `.feature`
  scenario) first, observe red for the intended reason, then implement.
- Do not change any existing public API signature, existing test, or library
  source under `src/falcon_correlate/`. This task adds documentation, example
  modules, and tests only. (Edits to `Makefile`, `pyproject.toml`, and the
  `docs/` tree are expected and in scope.)
- Example modules must satisfy the full gate set: `ruff format`, `ruff check`
  (including `D`, `ANN`, `RET`, `S`, `N`, `PLR`), the PyPy-backed pylint pass,
  and the `ty` type checker. No `# noqa` or `# type: ignore` without a comment
  explaining the invariant.
- British English (Oxford spelling: "-ize"/"-yse"/"-our") in all prose and
  comments, except where quoting external API names.
- Markdown wraps at 80 columns for prose and bullets, 120 for code blocks; use
  `-` for list bullets; fenced code blocks carry a language attribution.
- Python line length is 88 characters (ruff `line-length = 88`).
- Do not introduce a new *runtime* dependency. A new *dev* (test-only)
  dependency is permitted only where the user has named the tool: `syrupy`.
- The quickstart is the *single* canonical tutorial. After this change there
  must not be two competing "quick start" tutorials in the docs tree.

## Tolerances (exception triggers)

- Scope: before approval of a scope exception, if implementation requires
  changing more than 18 files or more than 600 net lines (excluding generated
  syrupy snapshot files), stop and escalate. This branch used that process:
  after deterministic gates passed, the completed implementation reached 18
  non-snapshot files and about 902 net non-snapshot lines, and the stop hook
  approved committing the over-limit work. Further scope growth remains outside
  that approved exception and must stop for confirmation.
- Interface: if any existing public API signature must change to make an
  example read well, stop and escalate.
- Dependencies: if any dependency beyond `syrupy` (dev group) is required, stop
  and escalate.
- Gate coverage: if Stage A cannot prove that `ruff`, `ty`, and pylint all
  inspect `examples/`, stop and escalate with the evidence (see Risk R1).
- Type viability: if a minimal, fully-annotated Falcon WSGI example cannot pass
  `ty` and ruff `ANN` without suppressions, stop and escalate (see Risk R2).
- Iterations: if a gate still fails after two fix attempts for the same root
  cause, stop and escalate with findings.
- Ambiguity: if the `examples/` directory boundary against roadmap 6.2.3
  conflicts with a maintainer decision, stop and confirm.

## Risks

- Risk R1: `ty` and/or pylint silently skip a top-level `examples/` directory,
  so example modules appear green while being unchecked. This would defeat the
  whole rationale for shipping examples as real modules. Severity: high.
  Likelihood: medium. Mitigation: Stage A is a "poison pill" verification —
  introduce a deliberately broken example, run `make typecheck` and
  `make lint`, and confirm each gate fails; then pin coverage explicitly
  (`PYLINT_TARGETS = src tests examples`, and a `ty` include/`environment`
  setting in `pyproject.toml` if bare `ty check` does not descend into
  `examples/`). Only proceed once each gate demonstrably sees the directory.

- Risk R2: Falcon's WSGI `Request`/`Response` typing is thinner than its ASGI
  typing, so a "fully type-annotated" example resource may fight ruff `ANN` and
  `ty`. Severity: medium. Likelihood: medium. Mitigation: Stage A includes a
  type-annotation spike on a one-resource WSGI app before the examples are
  committed; annotate handler parameters as `falcon.Request` /
  `falcon.Response` and the return as `None`, matching the patterns already
  used in `src/falcon_correlate/unittests/`.

- Risk R3: the drift guard is brittle. A naive byte-for-byte comparison between
  a Markdown fence and a `.py` file breaks on benign reformatting
  (`ruff format` rewraps the module but not the fence) and forbids partial
  snippets, so contributors weaken the assertion until it means nothing.
  Severity: high. Likelihood: high (if done naively). Mitigation: compare
  *semantically* via the abstract syntax tree (AST), not bytes. Each shown
  snippet is delimited in the source module by sentinel comments and tagged in
  the Markdown by a preceding HTML comment; the guard parses both sides with
  `ast.parse` and compares `ast.dump(...)`. This ignores whitespace, line
  wrapping, trailing commas, and comments, so only a real semantic divergence
  turns the test red. See "Plan of work, Stage D".

- Risk R4: `mdformat-all` (run by `make fmt`) or `markdownlint` reflows fenced
  Python or strips the HTML-comment region tags, breaking the drift guard.
  Severity: medium. Likelihood: low. Mitigation: Stage A confirms `make fmt`
  followed by `make markdownlint` leaves the HTML comments and fences intact;
  because the guard compares ASTs, intra-fence reflow is harmless, and only tag
  removal would matter.

- Risk R5: syrupy snapshots are non-deterministic under `pytest-xdist -n auto`
  because the log line embeds a timestamp (`asctime`) and a generated UUID.
  Severity: medium. Likelihood: medium. Mitigation: the snapshot test fixes the
  correlation and user IDs to literal values and normalises `asctime` with a
  regular expression before snapshotting; no generator is invoked.

- Risk R6: duplication between the new `docs/quickstart.md` and the existing
  `## Quick Start` section of `docs/users-guide.md` causes the two to diverge.
  Severity: medium. Likelihood: medium. Mitigation: this task demotes the
  users-guide's tutorial-style "Quick Start" subsections to a short pointer to
  `docs/quickstart.md`, leaving the users-guide as reference/how-to. There is
  exactly one tutorial after this change.

## Progress

- [x] (2026-06-18 02:30Z) Research codebase, public API, test conventions, and
  documentation tooling; commission Logisphere design review.
- [x] (2026-06-18 02:45Z) Write ExecPlan (this document).
- [x] (2026-06-24 12:04Z) Obtain approval for this ExecPlan via user request
  to proceed with implementation.
- [x] (2026-06-24 12:10Z) Stage A: gate-coverage poison-pill verification and
  WSGI type spike (go/no-go).
- [x] (2026-06-24 12:14Z) Stage B: add failing unit, BDD, snapshot, and
  drift-guard tests (red).
- [x] (2026-06-24 12:16Z) Stage C: implement `examples/quickstart/` modules
  (green).
- [x] (2026-06-24 12:18Z) Stage D: write `docs/quickstart.md` with
  sentinel-tagged snippets; make the drift guard pass.
- [x] (2026-06-24 12:21Z) Stage E: documentation maintenance (contents,
  README, users-guide, developers-guide, design doc, ADR-002, roadmap).
- [x] (2026-06-24 12:24Z) Stage F deterministic gates:
  `mbake validate Makefile`, `make check-fmt`, `make typecheck`, `make lint`,
  `make test`, `make markdownlint`, and `make nixie`.
- [x] (2026-06-24 12:31Z) Stage F tolerance exception resolved by stop-hook
  instruction to commit the completed, gated work.
- [x] (2026-06-24 14:05Z) Rebased branch onto `origin/main`, preserving
  main's three-tier linting ADR and Interrogate dependency while retaining the
  quickstart ADR, examples, and `syrupy` dependency.
- [x] (2026-06-24 14:18Z) Resolved post-turn Markdown gate failure by fixing
  premature Python code-fence closures in the middleware design document.
- [x] (2026-06-24 14:34Z) Resolved hosted CI `ty 0.0.53` failure by tightening
  the middleware correlation `ContextVar` type to `str | None` and casting the
  verified reset token before calling `ContextVar.reset`.
- [x] (2026-06-24 14:38Z) Re-ran deterministic gates after the CI type fix:
  `make check-fmt`, `make typecheck`, `make lint`, focused middleware context
  tests (`18 passed`), and `make test` (`433 passed, 11 skipped`).
- [x] (2026-07-04) Addressed review findings in the quickstart tests: added
  the missing user-only logging snapshot variant, drove the untrusted
  behavioural scenario through the configured example's app factory, and
  anchored the drift guard to the repository root.
- [x] (2026-07-04) Verified follow-up inline comments and fixed the still-valid
  documentation and drift-guard issues while skipping findings already fixed
  in current code.
- [ ] Stage F: run a `coderabbit review --agent` pass and clear all concerns.

## Surprises & discoveries

- Observation: `ty check` already descends into top-level `examples/`. With a
  temporary `examples/quickstart/_poison.py` returning `str` from a function
  annotated as `-> int`, `make typecheck` failed with `invalid-return-type`.
- Observation: Ruff already descends into top-level `examples/`. With the same
  temporary poison file carrying an unused import, `make lint` failed during
  the Ruff phase with `F401`.
- Observation: Pylint did not have explicit `examples/` coverage in the
  Makefile (`PYLINT_TARGETS ?= src tests`). After pinning
  `PYLINT_TARGETS ?= src tests examples`, a Ruff-clean poison file using
  `value.__str__()` failed during the Pylint phase with
  `unnecessary-dunder-call`. With the temporary file removed, `make lint`
  passed with the expanded target list.
- Observation: a fully annotated Falcon WSGI spike passes `ty`, Ruff, and
  Pylint without suppressions when the resource method uses instance state.
  Ruff reports `PLR6301` if a Falcon resource method does not use `self`.
- Observation: the Markdown probe marker `<!-- quickstart:probe -->` and the
  immediately following Python fence survived `make fmt`. The repository-wide
  `make fmt` target also rewrote unrelated historical Markdown and exposed an
  unrelated `MD013` line-length failure in
  `docs/execplans/4-2-4-validate-optional-celery-integration.md`; those
  generated edits were reversed because they are outside this task. The probe
  result still confirms that the quickstart marker scheme is viable.
- Observation: the Stage B red run collected ten focused tests and failed for
  the intended reasons: missing `examples.quickstart.*` modules, missing
  `docs/quickstart.md`, and a missing `snapshot` fixture before `syrupy` was
  installed.
- Observation: `syrupy>=4,<5` is incompatible with the project's pytest 9
  development dependency. `syrupy>=5,<6` resolves cleanly and provides the same
  `snapshot` fixture used by the quickstart log-format test.
- Observation: after Stage C, the unit and BDD quickstart examples passed; the
  only focused failures were the expected missing snapshot baseline and missing
  quickstart guide. After Stage D and snapshot approval, the focused command
  `uv run pytest tests/examples tests/docs tests/bdd/test_quickstart_steps.py -v`
  reported `10 passed`.
- Observation: the final deterministic gate chain passed before CodeRabbit:
  `mbake validate Makefile`, `make check-fmt`, `make typecheck`, `make lint`,
  `make test` (`431 passed, 11 skipped`), `make markdownlint`, and
  `make nixie`.
- Observation: after including intent-to-add files, the diff contains 19 files
  including the generated syrupy snapshot, or 18 non-snapshot files. That meets
  the file-count tolerance. The same diff is about 902 net non-snapshot lines,
  which exceeds the 600-line tolerance and triggers the exception process.
- Observation: rebasing onto `origin/main` brought in ADR-001's rename from
  two-tier to three-tier linting and the Interrogate dev dependency. The merge
  resolution kept both branches' intent: ADR-001 remains the accepted
  three-tier linting decision, ADR-002 records tested documentation examples,
  and the dev dependency group includes both `interrogate` and `syrupy`.
- Observation: `uv.lock` was reset to main's side during the rebase conflict,
  then regenerated with `uv lock`. This followed the lock-file conflict policy
  and produced a lock containing `syrupy` alongside main's Interrogate-related
  packages.
- Observation: the stop-hook Markdown gate caught two premature closing fences
  in `docs/falcon-correlation-id-middleware-design.md`. Those fences left
  commented Python lines outside their code block, so markdownlint parsed
  `# ...` comments as headings. Removing the premature fences restored the
  intended Python blocks and made `make markdownlint nixie` pass.
- Observation: hosted CI used `ty 0.0.53`, while the local `make typecheck`
  target used `ty 0.0.32`. The newer checker inferred
  `ContextVar.reset(...)` against `Token[Never]` when the middleware stored the
  context variable as `ContextVar[Any]`. Typing the constructor argument as
  `ContextVar[str | None]`, matching the exported `correlation_id_var`, and
  casting the runtime-verified token to `Token[str | None]` satisfies both
  checker versions without changing runtime behaviour.
- Observation: follow-up review found two coverage gaps in the quickstart
  tests. The logging snapshot covered `(correlation_id, user_id)`,
  `(correlation_id, None)`, and `(None, None)`, but missed `(None, user_id)`.
  The untrusted-ID behavioural scenario also rebuilt a bespoke app with the
  test-only `CorrelationEchoResource`, so it did not exercise the documented
  configured example boundary. The fix adds the missing snapshot row and
  drives the scenario through `examples.quickstart.configured_app.build_app`,
  varying only `trusted_sources`.
- Observation: the first drift guard used paths relative to the process
  current working directory. Anchoring `docs/quickstart.md` and
  `examples/quickstart/` from `__file__` makes the guard stable when pytest is
  invoked from outside the repository root.

## Decision log

- Decision: ship the examples as real `.py` modules under `examples/quickstart/`
  and embed those exact snippets in the guide, rather than executing the
  Markdown fences directly with a plugin such as `pytest-markdown-docs` or
  `pytest-codeblocks`. Rationale: real modules are covered by `ruff`, `ty`, and
  pylint; code that lives only inside Markdown fences escapes all three gates,
  which is unacceptable for a project whose quality bar is type- and
  lint-clean. The single-source-of-truth property that fence execution would
  give is recovered instead by the AST drift guard. Date/Author: 2026-06-18,
  planner. (The tool survey behind this choice — Sybil, pytest-markdown-docs,
  mktestdocs, phmdoctest/phmutest, pytest-examples, pytest-codeblocks, and
  stdlib doctest, including the documented Markdown incompatibility of doctest
  in CPython issue 116546 — is summarised in ADR-002.)

- Decision: compare snippets to source semantically via `ast.dump`, not by
  byte equality. Rationale: byte equality is flaky under `ruff format` and
  forbids partial snippets; AST comparison is deterministic, needs no
  subprocess, and survives reformatting and comment edits while still catching
  any real divergence (a changed identifier, literal, or call). Date/Author:
  2026-06-18, planner. (Adopted from the Logisphere review's blocking finding.)

- Decision: `docs/quickstart.md` is the single canonical tutorial; the
  tutorial-style subsections of the users-guide "Quick Start" are demoted to a
  pointer. Rationale: Diátaxis separates the learning-oriented tutorial (the
  quickstart) from reference/how-to (the users-guide); keeping two tutorials
  guarantees eventual divergence. Date/Author: 2026-06-18, planner.

- Decision: `examples/quickstart/` is owned by task 6.2.1. Roadmap task 6.2.3
  ("Create example applications") will own sibling directories
  (`examples/wsgi/`, `examples/asgi/`, `examples/celery/`) and may reference
  the quickstart modules rather than duplicating them. Rationale: both tasks
  write under `examples/`; declaring the boundary now prevents a turf
  collision. Date/Author: 2026-06-18, planner. A note recording this boundary
  is added to `docs/roadmap.md` under 6.2.3.

- Decision: retain a syrupy snapshot, scoped to the placeholder matrix of the
  logging output (correlation/user IDs set vs. unset), rather than a single
  assertion. Rationale: the user instruction calls for syrupy "where
  multivariant output format consistency is relevant"; the placeholder
  substitution across set/unset states is exactly such a multivariant output,
  so a snapshot of the rendered lines locks the format. The Logisphere panel
  argued a plain assertion suffices for one line; the snapshot is kept because
  the relevant surface is a matrix of variants, not one line, and `syrupy` is
  the user-named tool. Date/Author: 2026-06-18, planner.

- Decision: expand `PYLINT_TARGETS` from `src tests` to `src tests examples`
  in the Makefile. Rationale: Stage A proved Ruff and `ty` already inspect
  `examples/`, but Pylint required explicit target coverage for runnable
  documentation examples. Date/Author: 2026-06-24, implementer.

- Decision: keep the configured quickstart example on the default
  `X-Correlation-ID` header name while setting it explicitly in
  `CorrelationIDConfig`. Rationale: the approved BDD scenario exercises the
  default header value, and the example still shows where `header_name` is set
  alongside `trusted_sources` and `echo_header_in_response`. Date/Author:
  2026-06-24, implementer.

- Decision: use `syrupy>=5,<6` instead of `syrupy>=4,<5`. Rationale: all
  available `syrupy` 4.x releases require pytest older than the project's
  pytest 9 development dependency, while `syrupy` 5.x resolves cleanly.
  Date/Author: 2026-06-24, implementer.

- Decision: omit `__init__.py` package markers under `examples/quickstart/`,
  `tests/examples/`, and `tests/docs/`. Rationale: Python namespace packages
  and pytest discovery are sufficient, and omitting marker files keeps the
  delivered file count within the ExecPlan tolerance. Date/Author:
  2026-06-24, implementer.

- Decision: proceed with the current green implementation despite exceeding
  the ExecPlan net-line tolerance. Rationale: the stop hook explicitly
  instructed committing outstanding completed work after quality gates passed.
  This preserves the tested guide as planned instead of weakening coverage or
  deferring documentation maintenance. Date/Author: 2026-06-24, implementer.

- Decision: resolve the `origin/main` rebase conflicts by treating main's
  three-tier linting ADR and Interrogate dependency as authoritative, while
  preserving the branch's quickstart guide, tested-example ADR, and `syrupy`
  snapshot dependency. Rationale: main superseded the older linting ADR text,
  but the quickstart branch added independent documentation-example behaviour.
  Date/Author: 2026-06-24, implementer.

- Decision: keep the middleware's injectable correlation context variable
  typed as `ContextVar[str | None]`. Rationale: the middleware only stores
  generated or accepted string correlation IDs and the unset state is `None`;
  preserving that concrete type gives newer `ty` enough information to accept
  token reset after runtime validation. Date/Author: 2026-06-24, implementer.

- Decision: expose `build_app(config)` from the configured quickstart example
  and use it in behavioural tests. Rationale: the untrusted-ID scenario needs
  to vary `trusted_sources` to prove replacement behaviour, but it should keep
  the documented resource, route, and middleware construction path from the
  real example rather than rebuilding a parallel test-only app. Date/Author:
  2026-07-04, implementer.

## Outcomes & retrospective

Stage A proved that examples can be held to the same quality bar as package
code once Pylint's target list includes `examples`. Stage B established the red
tests for missing modules, missing documentation, and missing snapshot support.
Stages C and D delivered runnable examples, the canonical quickstart guide, a
passing AST drift guard, and an approved snapshot for the log-format variant
matrix. Stage E connected the new guide and tested-example convention into the
repository documentation set.

The branch was then rebased onto `origin/main`. Conflict resolution incorporated
main's newer three-tier linting architecture and Interrogate dependency without
dropping the quickstart work. Post-rebase validation passed the requested gates,
and subsequent hook/CI feedback uncovered two follow-up issues: malformed
Markdown fence boundaries in the design document and a stricter `ty 0.0.53`
diagnostic for `ContextVar.reset`. Both were fixed in focused commits and
validated with the relevant deterministic gates.

Current implementation status: the quickstart guide, examples, ADR-002,
drift-guard tests, BDD coverage, snapshot coverage, and documentation links are
implemented and pushed. The latest full Python gate set reports
`make test` as `433 passed, 11 skipped`; `make check-fmt`, `make typecheck`,
`make lint`, and explicit `ty 0.0.53` checking pass. The remaining recorded
review item is to run `coderabbit review --agent` and clear any concerns.

## Context and orientation

The reader is assumed to know nothing about this repository. Key facts:

- The package source lives under `src/falcon_correlate/`. The public API is
  re-exported from `src/falcon_correlate/__init__.py` and listed in `__all__`.
- The names a quickstart needs, with exact import paths:
  - `from falcon_correlate import CorrelationIDMiddleware` — WSGI middleware
    (`src/falcon_correlate/middleware.py`). Construct with keyword arguments
    only.
  - `from falcon_correlate import CorrelationIDMiddlewareASGI` — ASGI variant
    (`src/falcon_correlate/middleware_asgi.py`); same configuration surface.
  - `from falcon_correlate import CorrelationIDConfig` — frozen dataclass
    (`src/falcon_correlate/middleware_config.py`) with defaults:
    `header_name="X-Correlation-ID"`, `trusted_sources=frozenset()` (empty),
    `generator=default_uuid7_generator`, `validator=None`,
    `echo_header_in_response=True`.
  - `from falcon_correlate import ContextualLogFilter` — a `logging.Filter`
    subclass (constructed with no arguments) that injects `record.correlation_id`
    and `record.user_id`, using the placeholder `"-"` when a context variable is
    unset.
  - `from falcon_correlate import RECOMMENDED_LOG_FORMAT` — the recommended
    `logging.Formatter` format string, which includes the `%(correlation_id)s`
    and `%(user_id)s` placeholders (defined in
    `src/falcon_correlate/middleware_utils.py`).
  - `from falcon_correlate import correlation_id_var, user_id_var` — both
    `contextvars.ContextVar[str | None]`, default `None`, read with `.get()`.
  - The middleware also copies the active ID to `req.context.correlation_id`.
- Quality gates are Makefile targets: `make check-fmt`, `make typecheck`,
  `make lint`, `make test`, `make markdownlint`, `make nixie`. `make fmt`
  applies formatting (ruff + import sort + `mdformat-all`). `make test` runs
  `uv run pytest -v -n auto`.
- Pytest configuration is in `pyproject.toml` `[tool.pytest.ini_options]`:
  `pythonpath = ["."]` (so `tests.*` and a top-level `examples` package are
  importable), `timeout = 30`, one marker (`slow`). There is no `addopts` and
  no coverage threshold. `pytest-bdd`, `pytest-asyncio`, `pytest-xdist`, and
  `hypothesis` are dev dependencies; `syrupy>=5,<6` is now present for
  snapshot testing.
- Existing test conventions to reuse:
  - WSGI integration: `falcon.testing.TestClient(falcon.App(middleware=[...]))`
    then `client.simulate_get(path, headers=...)`; assert on
    `result.status_code`, `result.json`, and
    `result.headers["X-Correlation-ID"]`. See
    `src/falcon_correlate/unittests/test_middleware_falcon_integration.py` and
    `tests/conftest.py` (`CorrelationEchoResource`). The `TestClient` default
    `remote_addr` is `127.0.0.1`, so middleware that should *accept* an incoming
    ID in a test is configured with `trusted_sources=["127.0.0.1"]`.
  - pytest-bdd: a feature file `tests/bdd/<name>.feature` plus
    `tests/bdd/test_<name>_steps.py` that calls `scenarios("<name>.feature")`,
    carries state in a `Context` `typ.TypedDict(total=False)` created by a
    `@given(..., target_fixture="context")` step, and resets context variables
    in an autouse fixture (pattern in
    `tests/bdd/test_structlog_integration_steps.py`). Steps use
    `parsers.parse("... {value} ...")`.
  - Logging capture: the `logger_with_capture` fixture in
    `src/falcon_correlate/unittests/conftest.py` yields a factory returning
    `(logging.Logger, io.StringIO)` with a `ContextualLogFilter` attached;
    `isolated_context` runs a callable inside `contextvars.copy_context()`.
- Documentation conventions: `docs/contents.md` is the index; ADRs follow
  `docs/documentation-style-guide.md` (sections Status, Date, Context,
  Decision, Consequences) and the `adr-NNN-short-description.md` naming.
  `docs/adr-001-three-tier-linting.md` records the accepted linting
  architecture, and `ADR-002` records tested documentation examples.

### Key files

- `docs/quickstart.md` — Create — the canonical quickstart tutorial.
- `examples/quickstart/minimal_app.py` — Create — minimal WSGI app + resource.
- `examples/quickstart/configured_app.py` — Create — basic configuration
  options worked example.
- `examples/quickstart/logging_setup.py` — Create — logging integration.
- `tests/examples/test_quickstart_examples.py` — Create — unit tests driving
  each example with `falcon.testing.TestClient`, plus the syrupy log-format
  snapshot test.
- `tests/bdd/quickstart.feature` — Create — behavioural scenarios.
- `tests/bdd/test_quickstart_steps.py` — Create — step definitions.
- `tests/docs/test_quickstart_doc_matches_examples.py` — Create — AST drift
  guard.
- `docs/adr-002-tested-documentation-examples.md` — Create — ADR.
- `Makefile` — Edit — `PYLINT_TARGETS = src tests examples`.
- `pyproject.toml` — Edit — add `syrupy` to the dev group; add `ty`/ruff
  scoping or per-file-ignores for `examples/` and the new test packages if
  Stage A shows they are needed.
- `docs/contents.md` — Edit — index the quickstart and ADR-002.
- `README.md` — Edit — link to the quickstart.
- `docs/users-guide.md` — Edit — demote the tutorial-style "Quick Start"
  subsections to a pointer.
- `docs/developers-guide.md` — Edit — document the tested-examples convention
  and the drift guard.
- `docs/falcon-correlation-id-middleware-design.md` — Edit — reference ADR-002.
- `docs/roadmap.md` — Edit — mark 6.2.1 done; record the `examples/` boundary
  note under 6.2.3.

## Plan of work

The work proceeds in stages with go/no-go points. Do not advance past a stage
whose validation fails.

### Stage A: feasibility (no example/doc code yet) — go/no-go

This stage de-risks the two load-bearing assumptions before any examples are
written.

1. Gate-coverage poison pill. Create a temporary file
   `examples/quickstart/_poison.py` containing a deliberate type error and a
   deliberate lint violation (for example, a function returning a string from a
   body typed `-> int`, and an unused import). Run `make typecheck` and
   `make lint` and record whether each fails *because of that file*. If a gate
   passes, that gate is not inspecting `examples/`: pin it explicitly —
   `PYLINT_TARGETS = src tests examples` in the `Makefile`, and, for `ty`, add
   the appropriate include/environment setting under `pyproject.toml`
   (`[tool.ty]`) so `ty check` descends into `examples/`. Re-run until all
   three of `ruff check`, pylint, and `ty` fail on the poison file. Then delete
   `_poison.py`. Record the outcome in `Surprises & discoveries`.

2. Markdown round-trip check. Create a throwaway `docs/_probe.md` containing an
   HTML comment `<!-- quickstart:probe -->` immediately followed by a small
   ```python``` fence. Run `make fmt` then `make markdownlint`; confirm the HTML
   comment and the fence survive. Delete `docs/_probe.md`. If the HTML comment
   is stripped or relocated, escalate (the region-tag mechanism depends on it).

3. WSGI type spike. In a scratch module, write a one-resource Falcon WSGI app
   with fully annotated handlers
   (`def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:`) and
   run `make typecheck` and `make lint` against it. Confirm it is clean without
   suppressions. If `ty` or ruff `ANN` cannot be satisfied for a minimal WSGI
   example, stop and escalate (Risk R2).

Stage A validation: all three gates fail on the poison file and pass on the
clean spike; the Markdown probe survives formatting. Only then proceed.

### Stage B: failing tests (red)

Write tests first. Each must fail for the intended reason before Stage C/D.

1. Unit tests, `tests/examples/test_quickstart_examples.py`. Use class-based
   tests with descriptive docstrings. Cover:
   - `minimal_app`: importing the module exposes a `falcon.App` (named `app`);
     `TestClient(app).simulate_get("/hello")` returns 200, a JSON body, and a
     response header `X-Correlation-ID` whose value satisfies
     `default_uuid_validator`.
   - `minimal_app` happy path with an incoming trusted ID: build the app's
     middleware configured with `trusted_sources=["127.0.0.1"]` (the configured
     example) and assert the incoming `X-Correlation-ID` is echoed unchanged.
   - `configured_app`: assert the example's config object reports the customised
     `header_name`, the populated `trusted_sources`, and the
     `echo_header_in_response` value it documents; drive the app and assert the
     custom header name appears (or is suppressed) accordingly.
   - `logging_setup`: call the example's logging entry point inside
     `isolated_context`, set `correlation_id_var`/`user_id_var`, emit a record,
     and assert the captured output contains the correlation ID and user ID.
   - Snapshot (syrupy): a `test_log_format_variants` test that, for each row of
     the placeholder matrix `[(cid, uid), (cid, None), (None, uid), (None, None)]`,
     renders a `logging.LogRecord` through
     `logging.Formatter(RECOMMENDED_LOG_FORMAT)` plus `ContextualLogFilter`,
     normalises `asctime` via a regex to `<asctime>`, and asserts the normalised
     line equals `snapshot`. This requires `syrupy` (added in Stage E config,
     but the failing test is written now and will error on the missing import
     until the dependency is added).

2. Behavioural tests, `tests/bdd/quickstart.feature` and
   `tests/bdd/test_quickstart_steps.py`. The feature (embedded below) covers
   happy, unhappy, and edge paths. Step definitions follow the established
   `Context` TypedDict + `scenarios()` + autouse contextvar-reset conventions.
   Scenarios exercise the real quickstart example modules; edge cases may vary
   only narrow configuration inputs such as `trusted_sources`.

3. Drift guard, `tests/docs/test_quickstart_doc_matches_examples.py`. Written
   now; it will fail until both the example modules (Stage C) and the
   sentinel-tagged guide (Stage D) exist. Mechanism in Stage D.

Stage B validation: `make test` shows the new tests failing for the intended
reasons (missing modules, missing snapshot, missing doc), and no existing test
regresses.

### Stage C: implement example modules (green for the unit/BDD tests)

Create `examples/quickstart/` as an importable package. Each module exposes a
clearly named top-level object the tests import, and delimits each
guide-visible snippet with sentinel comments of the form
`# [quickstart:<id>]` ... `# [/quickstart:<id>]`. The sentinel lines are *not*
shown in the guide; the region between them is.

- `minimal_app.py`: imports, a `HelloResource` with an annotated `on_get`, and
  `app = falcon.App(middleware=[CorrelationIDMiddleware()])` with a route. Region
  ids: `minimal-imports`, `minimal-resource`, `minimal-app`.
- `configured_app.py`: builds a `CorrelationIDConfig` (or passes kwargs) showing
  `header_name`, `trusted_sources`, and `echo_header_in_response`, and an `app`
  using it. Region ids: `configured-config`, `configured-app`.
- `logging_setup.py`: a `configure_logging() -> logging.Logger` function that
  attaches `ContextualLogFilter` and a `logging.Formatter(RECOMMENDED_LOG_FORMAT)`
  to a handler and returns the logger, plus a short usage snippet. Region ids:
  `logging-config`, `logging-usage`. The function must not mutate global logging
  state at import time (configure inside the function, return the logger) so the
  tests can exercise it under `isolated_context`.

Run `make check-fmt`, `make lint`, `make typecheck` on the examples and the unit
and BDD suites until green.

Stage C validation: the unit and BDD tests pass; example modules pass fmt, lint,
and typecheck.

### Stage D: write the guide and pass the drift guard

Write `docs/quickstart.md` as a linear Diátaxis tutorial: one install command,
one minimal app, one configuration example, one logging example, each with the
expected observation, and a closing "next steps" pointer to the existing
users-guide. State the end result up front; minimise explanation; link out
rather than enumerating every option.

Each Python fence is preceded by an HTML comment naming its region. In the
guide this looks like the following (shown here in a tilde-fenced block so the
inner triple-backtick fence is literal):

~~~markdown
<!-- quickstart:minimal-app -->

```python
app = falcon.App(middleware=[CorrelationIDMiddleware()])
app.add_route("/hello", HelloResource())
```
```

The drift guard `tests/docs/test_quickstart_doc_matches_examples.py`:

1. Parses `docs/quickstart.md`, finding each `<!-- quickstart:<id> -->` marker
   and the Python fence that immediately follows it; collects `{id: fence_src}`.
2. Parses each `examples/quickstart/*.py`, extracting the text between
   `# [quickstart:<id>]` and `# [/quickstart:<id>]`; collects
   `{id: region_src}`.
3. For every id present in the guide, asserts the id exists in some module and
   that `ast.dump(ast.parse(fence_src)) == ast.dump(ast.parse(region_src))`.
   Also asserts there are no orphan markers (a guide id with no region, or a
   region id never shown) so coverage stays honest.

Because the comparison is over the AST, `ruff format` reflow, line wrapping,
and comment differences do not matter; a changed identifier, literal, or call
does.

Stage D validation: `make test` passes including the drift guard; `make fmt`
followed by `make markdownlint` leaves the guide clean and the markers intact.

### Stage E: documentation maintenance

- `pyproject.toml`: add `syrupy` to `[dependency-groups].dev`; apply any
  `ty`/ruff scoping or `[tool.ruff.lint.per-file-ignores]` entries for
  `examples/**` and the new test packages that Stage A/C proved necessary
  (documented in the Decision Log).
- `docs/contents.md`: add `docs/quickstart.md` under the user-facing docs and
  `docs/adr-002-tested-documentation-examples.md` under "Architecture and
  decisions"; add the new execplan link under "Planning documents".
- `README.md`: add a one-line link to the quickstart.
- `docs/users-guide.md`: replace the tutorial-style `### Basic Usage` and
  `### Falcon ASGI Usage` content with a short pointer to `docs/quickstart.md`,
  retaining the reference material ("How It Works" onward).
- `docs/developers-guide.md`: document the tested-examples convention — examples
  live under `examples/`, Pylint includes that directory through
  `PYLINT_TARGETS`, and the quickstart snippets are drift-guarded by AST
  comparison; explain how to add a new guarded snippet (sentinel comments +
  HTML-comment marker).
- `docs/falcon-correlation-id-middleware-design.md`: add a short subsection
  referencing ADR-002.
- `docs/adr-002-tested-documentation-examples.md`: write the ADR (Status,
  Date, Context, Decision, Consequences) recording the decision to ship tested,
  drift-guarded examples and the tool survey behind rejecting fence-execution.
- `docs/roadmap.md`: mark all 6.2.1 checkboxes `[x]`; add a one-line note under
  6.2.3 recording the `examples/` directory boundary.

Run `make fmt`, then `make markdownlint` and `make nixie`.

### Stage F: full gates and review

Run every gate (commands below) capturing logs via `tee`. Then run
`coderabbit review --agent` and clear every concern before the task is
considered complete. CodeRabbit must not be asked to catch anything the
deterministic gates already catch, so run the gates green first.

## Concrete steps

Run from the repository root. Capture logs for review:

```bash
set -o pipefail
ACTION=check-fmt; make $ACTION 2>&1 | tee /tmp/$ACTION-falcon-correlate-$(git branch --show-current).out
ACTION=typecheck; make $ACTION 2>&1 | tee /tmp/$ACTION-falcon-correlate-$(git branch --show-current).out
ACTION=lint; make $ACTION 2>&1 | tee /tmp/$ACTION-falcon-correlate-$(git branch --show-current).out
ACTION=test; make $ACTION 2>&1 | tee /tmp/$ACTION-falcon-correlate-$(git branch --show-current).out
ACTION=markdownlint; make $ACTION 2>&1 | tee /tmp/$ACTION-falcon-correlate-$(git branch --show-current).out
ACTION=nixie; make $ACTION 2>&1 | tee /tmp/$ACTION-falcon-correlate-$(git branch --show-current).out
```

To observe the red phase for a single new test before implementation, for
example:

```bash
uv run pytest tests/docs/test_quickstart_doc_matches_examples.py -v
```

Expected before Stage C/D: collection or assertion failure referencing the
missing `examples/quickstart` modules or `docs/quickstart.md`. Expected after:
the test passes.

## Validation and acceptance

Behavioural acceptance (what a human can verify):

- Opening `docs/quickstart.md` and following it produces a Falcon app whose
  responses carry an `X-Correlation-ID` header; the documented configuration
  and logging snippets run as shown.
- `uv run pytest tests/examples tests/docs tests/bdd/test_quickstart_steps.py -v`
  passes; each new test fails before its corresponding module/guide exists and
  passes after.
- Editing any identifier or literal inside a snippet in `docs/quickstart.md`
  (without editing the source module) turns
  `tests/docs/test_quickstart_doc_matches_examples.py` red.
- `make check-fmt`, `make typecheck`, `make lint`, `make test`,
  `make markdownlint`, and `make nixie` all pass.

Red-Green-Refactor evidence to record in `Progress`/`Surprises`:

- Red: the new unit, BDD, snapshot, and drift-guard tests fail for the intended
  reasons (missing modules, missing `syrupy`, missing guide).
- Green: after Stages C–E, the focused suites pass.
- Refactor: tidy example modules and step definitions, rerun the focused suites
  and the full gate set.

The embedded feature specification for the BDD work:

```gherkin
Feature: Quickstart guide examples

  Scenario: A generated correlation ID is attached to the response
    Given a Falcon app built from the quickstart minimal example
    When I request "/hello" without a correlation ID header
    Then the response status should be 200
    And the response should include a valid correlation ID header

  Scenario: A trusted incoming correlation ID is echoed
    Given a Falcon app built from the quickstart configured example
    When I request "/hello" with header "X-Correlation-ID" value "cid-quickstart-1"
    Then the response correlation ID header should be "cid-quickstart-1"

  Scenario: An untrusted incoming correlation ID is replaced
    Given a Falcon app from the configured example with no trusted sources
    When I request "/hello" with header "X-Correlation-ID" value "cid-untrusted"
    Then the response correlation ID header should not be "cid-untrusted"
    And the response should include a valid correlation ID header

  Scenario: The correlation ID appears in a log line
    Given the quickstart logging configuration
    And the correlation ID is set to "cid-log-1"
    When the example emits a log message "hello from quickstart"
    Then the log output should contain "cid-log-1"
    And the log output should contain "hello from quickstart"
```

Quality criteria ("done"):

- Tests: `make test` passes; new tests behave per Red-Green-Refactor above; no
  existing test regresses.
- Lint/typecheck/format: `make lint`, `make typecheck`, `make check-fmt`,
  `make markdownlint`, `make nixie` all pass, with `examples/` proven to be in
  scope for ruff, pylint, and `ty`.
- Documentation: the guide is a single canonical tutorial; the users-guide no
  longer holds a competing tutorial; ADR-002 and the cross-links exist.
- Review: `coderabbit review --agent` raises no outstanding concerns.

## Idempotence and recovery

All steps are safe to re-run. If formatting fails, run `make fmt` and re-check.
If the drift guard fails, reconcile the snippet and its source module (edit
whichever is wrong) and re-run. The Stage A poison-pill and probe files are
temporary and must be deleted before committing; if a stage is interrupted,
confirm no `_poison.py` or `_probe.md` remains (`git status`). Commit after
each green stage so any stage can be rolled back independently.

## Artifacts and notes

Keep the `tee` logs under `/tmp/` as evidence of passing gates. Record, in
`Surprises & discoveries`, the concrete outcome of the Stage A poison-pill (did
`ty`/pylint need explicit scoping?) and the Markdown round-trip probe.

## Interfaces and dependencies

New names introduced (all test/example/doc scope; no change to the public
package API):

- `examples.quickstart.minimal_app` — exposes `app: falcon.App` and
  `HelloResource`.
- `examples.quickstart.configured_app` — exposes `app: falcon.App` and the
  `CorrelationIDConfig` (or kwargs) it documents.
- `examples.quickstart.logging_setup` — exposes
  `configure_logging() -> logging.Logger`.

New dev dependency: `syrupy` (snapshot testing), added to
`[dependency-groups].dev` in `pyproject.toml`. No new runtime dependency.

Reused interfaces: `falcon.testing.TestClient`, `falcon.App`,
`falcon_correlate.CorrelationIDMiddleware`, `CorrelationIDConfig`,
`ContextualLogFilter`, `RECOMMENDED_LOG_FORMAT`, `correlation_id_var`/
`user_id_var`, `default_uuid_validator`, and the existing fixtures
`isolated_context`, `logger_with_capture`, and the `CorrelationEchoResource`/
`SimpleResource` test resources.

## Revision note (required when editing an ExecPlan)

2026-06-18: Initial draft for roadmap task 6.2.1. Incorporates the Logisphere
design-review conditions: AST-based (not byte-equal) drift guard; a Stage A
poison-pill verification that `ruff`/`ty`/pylint cover `examples/`; an explicit
`examples/` ownership boundary against roadmap 6.2.3; collapse to a single
canonical tutorial by demoting the users-guide "Quick Start"; and a scoped (not
single-line) syrupy snapshot over the logging placeholder matrix.

2026-06-24: User approved implementation by requesting that this plan be
executed. Status changed to IN PROGRESS and the approval checkpoint was marked
complete.

2026-06-24: Completed Stage A. Recorded gate-coverage evidence for Ruff, `ty`,
and Pylint; documented the Makefile target decision; recorded the WSGI typing
spike result; and noted the Markdown formatter's unrelated historical-doc churn.

2026-06-24: Completed Stages B through E. Recorded the red focused test
results, added runnable quickstart examples, wrote the AST-guarded guide,
approved the logging snapshot, added ADR-002, and updated user, developer,
design, roadmap, contents, and README documentation.

2026-06-24: Recorded post-implementation status after rebase and CI follow-up
fixes. Added progress, observations, decisions, and outcomes for the
`origin/main` rebase, the Markdown hook failure, and the hosted `ty 0.0.53`
`ContextVar.reset` diagnostic.
