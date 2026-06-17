# Write and gate docstrings for all public APIs (6.1.1)

This ExecPlan (execution plan) is a living document. The sections
`Constraints`, `Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`,
`Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work
proceeds.

Status: DRAFT

## Purpose / big picture

After this change, every public symbol of `falcon-correlate` carries a complete,
consistent NumPy-style docstring, and the build mechanically guarantees that
those docstrings stay accurate. A newcomer running `help(falcon_correlate)` (or,
later, browsing generated API docs from milestone 6.1.2) finds: a documented
purpose for each class, function, context variable, and constant; documented
parameters, return values, and raised exceptions that match the actual
signatures; and runnable usage examples.

You can observe success in four ways:

1. `make lint` passes with the Ruff `DOC` (pydoclint) rule group enabled, so
   any docstring whose `Parameters`/`Returns`/`Raises` sections drift from the
   signature fails the build.
2. `make test` passes, including a new doctest pass that executes the `>>>`
   examples embedded in docstrings, and a new introspection test that asserts
   every public symbol (including module-level variables) is documented.
3. `import falcon_correlate; help(falcon_correlate.CorrelationIDMiddleware)`
   shows a full docstring, and the three public module-level names
   (`correlation_id_var`, `user_id_var`, `RECOMMENDED_LOG_FORMAT`) carry inline
   attribute docstrings that Sphinx `autodata`/napoleon will pick up.
4. The convention is written down: a new ADR (`docs/adr-002-*`), a
   "Docstring conventions" section in `docs/developers-guide.md`, and a
   reference from the design document and `docs/contents.md`.

This work is an audit-and-fill exercise, not greenfield writing. Ruff already
enforces `D` (pydocstyle) with `convention = "numpy"`, so every function, class,
method, and module already has *some* docstring. The gaps are: missing
attribute docstrings on module-level variables (pydocstyle cannot flag these);
single-line docstrings that omit `Parameters`/`Returns`/`Raises` sections; and
the absence of any gate that checks docstring *content* against the signature or
that *runs* the examples.

## Constraints

Hard invariants that must hold throughout implementation. Violation requires
escalation, not a workaround.

- Public API surface must not change. The set of names in
  `src/falcon_correlate/__init__.py` `__all__` and every public signature
  (parameter names, order, defaults, return types) must remain identical. This
  is a documentation change only.
- No runtime behaviour change. No edits to function bodies except where a
  docstring is added/edited or an example requires a trivially safe, behaviour-
  preserving change (none is anticipated).
- NumPy docstring convention only. `[tool.ruff.lint.pydocstyle] convention =
  "numpy"` stays in force. Do not switch to Google or reST styles.
- en-GB Oxford spelling (`-ize`/`-yse`/`-our`) in all prose and docstrings,
  except where echoing an external API name (for example, httpx `color`-style
  kwargs or AMQP `correlation_id`). See `docs/documentation-style-guide.md`
  and the `en-gb-oxendict` skill.
- File-size limit: no source file may exceed 400 lines (AGENTS.md). Adding
  docstrings to `middleware.py` (currently 397 lines) will breach this; that
  module must be kept under 400 lines, splitting if necessary (see Risks).
- Each commit must pass all code gates (`make check-fmt`, `make lint`,
  `make typecheck`, `make test`) before it is made (AGENTS.md). Markdown changes
  must additionally pass `make markdownlint` and `make nixie`.

## Tolerances (exception triggers)

Stop and escalate when any of these is reached:

- Interface: if completing a docstring appears to require changing any public
  signature, stop and escalate.
- Scope from DOC rules: if enabling repo-wide `DOC` rules surfaces more than
  roughly 60 distinct violations, or forces edits to more than 12 source files,
  stop and report the count before mass-editing, so the public-only-versus-
  repo-wide trade-off can be reconfirmed.
- DOC false positives: if a `DOC` rule fires on a construct that cannot be
  satisfied without distorting the docstring (for example, a re-raised or
  conditionally raised exception pydoclint cannot see), stop and propose a
  narrowly scoped `# noqa: DOC...` with a justifying comment rather than
  inventing documentation.
- File split: if keeping `middleware.py` under 400 lines requires a non-trivial
  module split (moving public symbols between files), stop and escalate, because
  a split risks the "no public API change" constraint (import paths).
- Iterations: if a single module's gates still fail after 3 fix attempts, stop
  and escalate with the failing output.
- Dependencies: adding any new runtime dependency is out of scope; stop and
  escalate. (Dev-only tooling already present — Ruff, pytest — needs no new
  dependency. Confirm pytest's doctest support needs nothing beyond pytest.)

## Risks

- Risk: enabling `DOC` repo-wide flags many private helpers that currently pass
  with one-line docstrings (for example `_validate_header_name`,
  `_parse_network`, `_process_request`).
  Severity: medium. Likelihood: high.
  Mitigation: this scope was explicitly chosen (Decision Log D3). Complete the
  private docstrings module-by-module; if the count exceeds the Tolerance,
  escalate.

- Risk: `middleware.py` is at 397 lines; adding docstrings pushes it past the
  400-line limit.
  Severity: medium. Likelihood: high.
  Mitigation: prefer concise docstrings; if still over, escalate before
  splitting (a split touches import paths and risks the public-API constraint).

- Risk: doctest examples that need a request context, network, or optional
  dependency (httpx, Celery) would fail or hang under `--doctest-modules`.
  Severity: medium. Likelihood: medium.
  Mitigation: only use executable `>>>` prompts for offline, dependency-free
  examples (context-variable get/set, `default_uuid_validator`); render
  integration examples as non-executed literal code blocks (`::` /
  `.. code-block:: python`). Codify this rule in the ADR.

- Risk: `--doctest-modules` import-file-mismatch because the package is both
  installed (editable, via `make build`) and present under `src/`.
  Severity: medium. Likelihood: medium.
  Mitigation: run doctests with `--import-mode=importlib` and target the
  installed module path; verify collection in milestone 1 before relying on it.

- Risk: doctest collection imports every module, including `celery.py` and
  `httpx.py`.
  Severity: low. Likelihood: low.
  Mitigation: both modules are already import-safe without their optional
  dependency (verified: `celery.py` and `httpx.py` guard optional imports).

- Risk: `DOC` rules are in Ruff preview and their behaviour may shift between
  Ruff versions.
  Severity: low. Likelihood: low.
  Mitigation: Ruff is pinned in the dev dependency group; record the version in
  the ADR. `preview = true` is already set in `pyproject.toml`.

## Progress

- [ ] Milestone 0 — Orientation and branch setup (no code changes).
- [ ] Milestone 1 (Red) — Enable `DOC` rules and the doctest harness; capture
      the failing gate output as the red baseline.
- [ ] Milestone 2 (Red) — Add the public-API docstring introspection test;
      observe it fail for undocumented module-level variables.
- [ ] Milestone 3 (Green) — Public API: inline attribute docstrings and
      completed class/function/method docstrings, module by module.
- [ ] Milestone 4 (Green) — Private helpers: complete docstrings to satisfy
      repo-wide `DOC`, module by module.
- [ ] Milestone 5 (Refactor/Docs) — ADR, developers-guide section, design-doc
      and contents.md references, users-guide check.
- [ ] Milestone 6 — Full gate sweep, CodeRabbit review, mark roadmap 6.1.1 done.

## Surprises & discoveries

- Observation: 6.1.1 is largely already implemented. Most public symbols carry
  substantial NumPy docstrings, added incrementally by the milestone plans for
  sections 2–5.
  Evidence: `leta show` of each `__all__` symbol; Ruff `D` is enabled with
  `convention = "numpy"`, so no public callable can lack a docstring.
  Impact: the work is an audit-and-fill plus a verification-gate upgrade, not
  greenfield authoring.

- Observation: `default_uuid_validator` already contains `>>>` doctest examples
  that nothing currently executes.
  Evidence: `src/falcon_correlate/middleware_utils.py` ~lines 220-225; no
  `--doctest-modules` in `[tool.pytest.ini_options]`.
  Impact: a doctest gate immediately gains value and validates existing
  examples.

- Observation: `preview = true` is already set under `[tool.ruff]`.
  Evidence: `pyproject.toml` ruff section.
  Impact: enabling `DOC` rules needs only adding `"DOC"` to `select`; no extra
  flag.

## Decision log

- Decision: Document module-level public variables (`correlation_id_var`,
  `user_id_var`, `RECOMMENDED_LOG_FORMAT`) with inline attribute docstrings (a
  string literal immediately after the assignment), not via an `Attributes`
  section in the module docstring.
  Rationale: the Sphinx/numpydoc canonical example states both forms are valid
  but must not be mixed; inline docstrings colocate documentation with the
  definition and are picked up by Sphinx `autodata`/napoleon for 6.1.2.
  Date/Author: 2026-06-17, planning agent.

- Decision: Use the Ruff `DOC` (pydoclint) rule group as a permanent, repo-wide
  gate, completing private-helper docstrings as needed.
  Rationale: user selection during planning ("Also commit DOC repo-wide as a
  permanent gate"). `DOC` verifies docstring content against signatures, which
  `D` does not.
  Date/Author: 2026-06-17, user + planning agent.

- Decision: Add a `--doctest-modules` gate so docstring examples are executed;
  restrict executable `>>>` examples to offline, dependency-free cases and use
  non-executed literal blocks for integration examples.
  Rationale: AGENTS.md requires function documentation to "include clear
  examples demonstrating usage and outcome"; an unexecuted example can rot.
  Date/Author: 2026-06-17, user + planning agent.

- Decision: Record the docstring/verification convention in a new ADR
  (`docs/adr-002-*`), referenced from the design document and
  `docs/contents.md`, and add a "Docstring conventions" section to
  `docs/developers-guide.md`.
  Rationale: user selection during planning; matches the existing
  `adr-001-two-tier-linting.md` practice.
  Date/Author: 2026-06-17, user + planning agent.

## Outcomes & retrospective

To be completed at milestone boundaries and at completion. Compare the result
against the Purpose: are all public symbols documented, do the gates enforce it,
and is the convention recorded?

## Context and orientation

`falcon-correlate` is a correlation-ID middleware for the Falcon web framework.
The installable package lives under `src/falcon_correlate/`. The public API is
re-exported from `src/falcon_correlate/__init__.py`; its `__all__` is the
authoritative list of public symbols:

- `CorrelationIDMiddleware`, `CorrelationIDMiddlewareASGI`,
  `CorrelationIDConfig` — WSGI middleware, ASGI middleware, and the frozen
  configuration dataclass. Defined in `middleware.py`, `middleware_asgi.py`,
  `middleware_config.py`.
- `correlation_id_var`, `user_id_var` — `contextvars.ContextVar[str | None]`
  module-level variables. Defined in `middleware_utils.py`.
- `ContextualLogFilter`, `RECOMMENDED_LOG_FORMAT` — stdlib logging filter and
  the recommended format string. Defined in `middleware_utils.py`.
- `default_uuid7_generator`, `default_uuid_validator` — default ID generator and
  validator. Defined in `middleware_utils.py`.
- `request_with_correlation_id`, `async_request_with_correlation_id`,
  `CorrelationIDTransport`, `AsyncCorrelationIDTransport` — httpx propagation
  utilities. Defined in `httpx.py`.
- `propagate_correlation_id_to_celery`, `setup_correlation_id_in_worker`,
  `clear_correlation_id_in_worker`, `configure_celery_correlation` — Celery
  propagation utilities. Defined in `celery.py`.
- `hello` — trivial demo function (Rust-or-pure fallback). Defined in
  `pure.py`.

Terms of art:

- "Attribute docstring": a bare string literal placed on the line(s)
  immediately after a module-level (or class-level) assignment. Python does not
  store it on the object at runtime, but Sphinx/numpydoc and tooling read it
  statically. Example: `X = 1` then `"""int: what X is."""`.
- "pydocstyle (`D`) rules": Ruff rules that check docstring *presence* and
  *formatting*. Already enabled.
- "pydoclint (`DOC`) rules": Ruff preview rules that check docstring *content*
  against the signature — that documented parameters/returns/raises exist and
  match. Not yet enabled. Key rules: `DOC201` (missing `Returns`), `DOC202`
  (spurious `Returns`), `DOC402`/`DOC403` (yields), `DOC501` (missing
  documented exception), `DOC502` (spurious documented exception).

Authoritative gap analysis (verified during planning; line numbers approximate
and must be reconfirmed before editing, since edits shift them):

Missing attribute docstrings (highest priority — pydocstyle cannot catch these):

- `correlation_id_var` — `middleware_utils.py` ~line 21.
- `user_id_var` — `middleware_utils.py` ~line 24.
- `RECOMMENDED_LOG_FORMAT` — `middleware_utils.py` ~line 30.

Public docstrings that are single-line and need sections:

- `CorrelationIDMiddlewareASGI.process_request` / `process_response`
  (`middleware_asgi.py`) — need `Parameters`/`Raises` to match the WSGI variant.
- `CorrelationIDTransport` / `AsyncCorrelationIDTransport` classes and their
  `handle_request` / `handle_async_request` methods (`httpx.py`) — need
  `Parameters`/`Raises`/`Returns`.
- `setup_correlation_id_in_worker` / `clear_correlation_id_in_worker`
  (`celery.py`) — need `Parameters`/`Notes`.
- `hello` (`pure.py`) — needs `Returns`.

Existing docstrings missing some sections:

- `CorrelationIDConfig.from_kwargs` — needs `Raises` and `Examples`.
- `CorrelationIDConfig.__post_init__` — needs `Raises`.
- `CorrelationIDConfig`, `CorrelationIDMiddleware` — would benefit from
  `Examples`/`Attributes`.
- `request_with_correlation_id`, `async_request_with_correlation_id` — need
  `Raises` (`ImportError` when httpx absent) and `Examples`.
- `propagate_correlation_id_to_celery`, `configure_celery_correlation` — need
  `Examples`.
- `default_uuid7_generator` — needs `Raises` (`ModuleNotFoundError`) and an
  `Examples` block.

Already complete (leave as reference exemplars): `ContextualLogFilter`,
`default_uuid_validator`, `CorrelationIDMiddlewareASGI` class docstring,
`CorrelationIDMiddleware.process_request`/`process_response`.

Documentation cross-references the docstrings must stay consistent with:

- Dual access pattern (`correlation_id_var.get()` versus
  `req.context.correlation_id`): `docs/users-guide.md` "Accessing the
  correlation ID" and "Context Variables" sections; design doc §3.3.3.
- Logging filter and `RECOMMENDED_LOG_FORMAT`: `docs/users-guide.md` "Logging
  integration"; design doc §3.4.1, §3.4.2, §4.6.8, §4.6.9.
- httpx and Celery utilities: `docs/users-guide.md` "httpx propagation" and
  "Celery propagation"; design doc §3.5.

Relevant tooling and commands (verified):

- `make check-fmt` → `uv run ruff format --check`.
- `make lint` → `uv run ruff check` then a PyPy-backed Pylint pass over
  `src tests`.
- `make typecheck` → `ty check`.
- `make test` → `uv run pytest -v -n auto`.
- `make markdownlint` → `markdownlint-cli2 '**/*.md'`; `make nixie` validates
  Mermaid.
- Ruff config: `[tool.ruff] preview = true`, `target-version = "py312"`;
  `[tool.ruff.lint] select` includes `D` and `ANN` but not `DOC`;
  `extend-ignore = ["D203", "D213"]`; `[tool.ruff.lint.pydocstyle] convention =
  "numpy"`.
- pytest config: `[tool.pytest.ini_options]` has `timeout = 30`,
  `pythonpath = ["."]`, markers; no `addopts`, no doctest collection.

## Plan of work

The work follows Red-Green-Refactor. Documentation is the "production code"
here; the deterministic gates (`DOC` lint, doctest, and an introspection test)
are the tests. We make the gates fail first (Red), then write docstrings until
they pass (Green), then tidy prose, spelling, and cross-references (Refactor).

### Stage A — orientation (Milestone 0)

No code changes. Reconfirm the gap analysis against the current tree with
`leta show <symbol>` and `leta grep`, because line numbers above are
approximate. Read `docs/adr-001-two-tier-linting.md` as the ADR template and
`docs/documentation-style-guide.md` for spelling and example conventions. Load
the `leta`, `python-types-and-apis`, `python-testing`,
`python-errors-and-logging`, and `en-gb-oxendict` skills (see Interfaces and
dependencies).

### Stage B — red gates (Milestones 1–2)

Milestone 1: enable the content gates and capture the red baseline.

1. In `pyproject.toml`, add `"DOC"` to `[tool.ruff.lint] select` (a comment:
   `# DOC: pydoclint - docstrings match signatures (preview)`).
2. Add a doctest gate. Prefer a dedicated, opt-in invocation to keep the main
   `make test` fast and avoid surprising parallelism interactions, but it must
   be wired into the committed gates. Concretely: add a `doctest` recipe to the
   `Makefile` running
   `uv run pytest --doctest-modules --import-mode=importlib
   src/falcon_correlate --ignore=src/falcon_correlate/unittests`, and either
   call it from the `test` target or add it to CI. Decide in milestone 1 after
   confirming collection works (Risk: import-file-mismatch); record the choice
   in the Decision Log.
3. Run `make lint` and the doctest recipe; tee output to
   `/tmp/lint-<project>-<branch>.out` and
   `/tmp/doctest-<project>-<branch>.out`. The expected red state: Ruff reports
   `DOC` violations across public and private symbols; doctest collects and runs
   the existing `default_uuid_validator` examples (these should pass — they are
   correct). Record the DOC violation count and the file list. If the count
   exceeds the Tolerance, stop and escalate.

Milestone 2: add the introspection test (covers what lint cannot — runtime
docstrings on public callables and attribute docstrings on public variables).

Create `src/falcon_correlate/unittests/test_public_api_docstrings.py`:

- Parametrize over `falcon_correlate.__all__`. For callables and classes,
  assert `inspect.getdoc(obj)` is non-empty and longer than a trivial summary
  threshold. Exclude `hello` from the length threshold if desired, but still
  require a docstring.
- For the module-level variables (`correlation_id_var`, `user_id_var`,
  `RECOMMENDED_LOG_FORMAT`), runtime `__doc__` is unavailable, so assert their
  attribute docstrings exist by parsing the defining module with `ast`: for
  each target assignment in `middleware_utils.py`, assert the next sibling
  statement is an `ast.Expr` wrapping an `ast.Constant` string. Provide a small
  helper that maps each public variable name to its module and checks this.

Run `make test` (tee to `/tmp/test-<project>-<branch>.out`). Expected red:
the variable attribute-docstring assertions fail (no attribute docstrings yet);
callable assertions mostly pass but flag any thin single-line docstrings if the
threshold is set to catch them. Commit the red tests with
`@pytest.mark.xfail(strict=True, reason="6.1.1 docstrings pending")` only if a
clean red commit is required by gates; otherwise keep them failing locally and
proceed straight to green within the same milestone, removing any xfail markers
as the green steps land. Record which approach is used in the Decision Log.

### Stage C — green (Milestones 3–4)

Work module by module. After each module: run `make check-fmt`, `make lint`,
`make typecheck`, `make test`, and the doctest recipe; commit when all pass.

Milestone 3 — public API:

1. `middleware_utils.py`: add inline attribute docstrings for
   `correlation_id_var`, `user_id_var`, `RECOMMENDED_LOG_FORMAT`. Each begins
   with a type-prefixed summary per the numpydoc inline form, for example:

   ```python
   # python
   correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
       "correlation_id", default=None
   )
   """contextvars.ContextVar[str | None]: Ambient correlation ID for the current
   request or task.

   Set by the middleware in ``process_request`` and reset in
   ``process_response``. Read it with ``correlation_id_var.get()`` from code that
   has no access to the Falcon ``req`` object (logging filters, downstream
   clients). Within responders, prefer ``req.context.correlation_id``. See the
   design document §3.3.3 for the dual-access pattern.

   Examples
   --------
   >>> from falcon_correlate import correlation_id_var
   >>> token = correlation_id_var.set("abc123")
   >>> correlation_id_var.get()
   'abc123'
   >>> correlation_id_var.reset(token)
   """
   ```

   Add `Raises` (`ModuleNotFoundError`) and an `Examples` block to
   `default_uuid7_generator`. Leave `default_uuid_validator` and
   `ContextualLogFilter` as exemplars (top up only if `DOC` flags them).
2. `middleware_asgi.py`: bring `process_request`/`process_response` to parity
   with the WSGI variant (`Parameters`, and `Raises` where exceptions
   propagate).
3. `httpx.py`: complete `CorrelationIDTransport`/`AsyncCorrelationIDTransport`
   class docstrings (`Parameters` for the inherited `__init__`:
   `wrapped_transport`, `header_name`; `Raises`) and their
   `handle_request`/`handle_async_request`
   methods (`Parameters`, `Returns`). Add `Raises` (`ImportError`) and
   non-executed integration `Examples` to `request_with_correlation_id` and
   `async_request_with_correlation_id`.
4. `celery.py`: add `Parameters`/`Notes` to `setup_correlation_id_in_worker`
   and `clear_correlation_id_in_worker` (explain the LIFO reset-token stack);
   add non-executed `Examples` to `propagate_correlation_id_to_celery` and
   `configure_celery_correlation`.
5. `middleware_config.py`: add `Raises` to `from_kwargs` and `__post_init__`;
   add `Examples`/`Attributes` to `CorrelationIDConfig` where helpful.
6. `middleware.py`: add `Examples`/`Attributes` to `CorrelationIDMiddleware`
   only as far as the 400-line limit allows; if the limit binds, prefer a
   concise `Examples` block and escalate before splitting.
7. `pure.py`: add `Returns` to `hello`.

Milestone 4 — private helpers flagged by repo-wide `DOC`. Iterate over the
remaining `DOC` violations from the milestone 1 baseline (for example
`_validate_header_name`, `_validate_trusted_sources`, `_parse_network`,
`_normalise_trusted_sources`, `_resolve_generator`,
`_get_incoming_header_value`, `_is_trusted_source`, `_is_valid_id`,
`_process_request`,
`_echo_correlation_id_header`, `_reset_correlation_id_context`,
`_process_response`, `_inject_correlation_id_header`, `_prepare_headers`,
`_require_httpx`, `_current_result_backend_uses_rpc`,
`_get_task_request_correlation_id`, `_safe_connect_signal`, and the
`_maybe_connect_*` helpers). Add the missing `Parameters`/`Returns`/`Raises`
sections. Where a `DOC` finding is a genuine false positive (a re-raised or
conditionally raised exception pydoclint cannot trace), apply a narrowly scoped
`# noqa: DOC...` with a one-line justification rather than fabricating
documentation; record each such suppression in Surprises & Discoveries.

### Stage D — refactor and documentation (Milestone 5)

1. Write `docs/adr-002-docstring-completeness-and-doctest-gates.md` in the style
   of `docs/adr-001-two-tier-linting.md`. Capture: NumPy convention; inline
   attribute-docstring rule for module variables; repo-wide `DOC` gate with the
   pinned Ruff version; the doctest gate and the "executable `>>>` only for
   offline examples" rule; and the rationale.
2. Add a "Docstring conventions" section to `docs/developers-guide.md`,
   positioned just after the "Episodic lint policy" section, expanding the
   existing "keep docstrings in NumPy style" note with a short template and the
   attribute-docstring and doctest rules. Link to ADR-002.
3. Reference ADR-002 from `docs/falcon-correlation-id-middleware-design.md`
   (in the appendix/references area) and add it to `docs/contents.md` under
   "Architecture and decisions", and add this ExecPlan under "Planning
   documents".
4. Review `docs/users-guide.md` for any statement the completed docstrings now
   contradict or that should be cross-referenced; update only if a real
   inconsistency exists (the audit found it already consistent).
5. Run `make fmt` (formats Markdown), `make markdownlint`, and `make nixie`.

### Milestone 6 — final sweep and review

Run the full gate set in sequence (not in parallel, per the environment note):
`make check-fmt`, `make lint`, `make typecheck`, `make test`, plus the doctest
recipe, `make markdownlint`, and `make nixie`. Then run `coderabbit review
--agent` and clear every concern before considering the milestone done. Only
after all deterministic gates are green should CodeRabbit be invoked. Finally,
mark roadmap item 6.1.1 (and its four sub-bullets) as done in
`docs/roadmap.md`.

## Concrete steps

Run from the repository root (the worktree directory). Tee long outputs for
review, per the environment guidance.

```bash
# bash
# Milestone 0: reconfirm gaps (examples)
leta show correlation_id_var
leta grep "process_request" -k method

# Milestone 1: after editing pyproject.toml + Makefile
uv run ruff check 2>&1 | tee /tmp/lint-falcon-correlate-$(git branch --show-current).out
uv run pytest --doctest-modules --import-mode=importlib \
  src/falcon_correlate --ignore=src/falcon_correlate/unittests 2>&1 \
  | tee /tmp/doctest-falcon-correlate-$(git branch --show-current).out

# Per-module green loop (repeat for each edited module)
make check-fmt 2>&1 | tee /tmp/check-fmt-falcon-correlate-$(git branch --show-current).out
make lint      2>&1 | tee /tmp/lint-falcon-correlate-$(git branch --show-current).out
make typecheck 2>&1 | tee /tmp/typecheck-falcon-correlate-$(git branch --show-current).out
make test      2>&1 | tee /tmp/test-falcon-correlate-$(git branch --show-current).out

# Milestone 5: markdown gates
make markdownlint 2>&1 | tee /tmp/mdlint-falcon-correlate-$(git branch --show-current).out
make nixie        2>&1 | tee /tmp/nixie-falcon-correlate-$(git branch --show-current).out
```

Expected transcripts:

- Milestone 1 `ruff check`: a non-zero exit listing `DOC2xx`/`DOC5xx` findings
  across `src/falcon_correlate/*.py`. Record the count.
- Milestone 1 doctest: `... passed` for the `default_uuid_validator` examples;
  zero failures. If collection errors with import-file-mismatch, add
  `--import-mode=importlib` (already in the command) and re-run; if it persists,
  escalate.
- Green loop end state: `ruff check` reports "All checks passed!"; `pytest`
  reports all tests passed including the new introspection test; doctest reports
  all examples passed.

## Validation and acceptance

Acceptance is behavioural and gate-based:

- Red evidence (capture in Progress/Artifacts): with `"DOC"` added to Ruff
  `select`, `uv run ruff check` fails and lists the docstring-content
  violations; the new
  `src/falcon_correlate/unittests/test_public_api_docstrings.py` fails on the
  three module-level variables before their attribute docstrings exist. Any
  `xfail(strict=True)` markers used must be observed failing, then removed in
  the green step.
- Green evidence: after the docstring work, `uv run ruff check` prints "All
  checks passed!"; `make test` passes including the introspection test; the
  doctest recipe runs the `>>>` examples and reports zero failures.
- Manual check: `python -c "import falcon_correlate as f;
  help(f.CorrelationIDMiddleware)"` shows a complete docstring; opening
  `src/falcon_correlate/middleware_utils.py` shows inline attribute docstrings
  beneath `correlation_id_var`, `user_id_var`, and `RECOMMENDED_LOG_FORMAT`.

Quality criteria ("done"):

- Tests: `make test` green; new introspection test present and passing; doctest
  recipe green.
- Lint/typecheck: `make check-fmt`, `make lint` (with `DOC` enabled), and
  `make typecheck` all green.
- Docs: `make markdownlint` and `make nixie` green; ADR-002 present and linked;
  developers-guide section added; design-doc and contents.md updated.
- Review: `coderabbit review --agent` run with all concerns cleared.
- Roadmap: 6.1.1 and its sub-bullets marked done.

Quality method: run each gate via its Makefile target in sequence, tee output,
and review. Do not run gates in parallel (build-cache guidance). CodeRabbit only
after deterministic gates pass.

This task type does not warrant BDD (`pytest-bdd`), property tests
(`hypothesis`), snapshot tests (`syrupy`), or end-to-end tests: docstrings
introduce no new runtime behaviour, invariant over inputs, multivariant output
format, or externally observable workflow. The relevant validations are the
`DOC`/`D` lint gates, the doctest execution of examples, and the introspection
test for documentation presence. Record this rationale in the Decision Log if
challenged.

## Idempotence and recovery

All edits are additive docstring text plus three config/test additions; re-
running any gate is safe and side-effect-free. Each module is committed only
when green, so recovery is `git checkout -- <file>` or reverting the last
commit. The doctest and DOC gates are deterministic and repeatable. No
destructive operations are involved.

## Artifacts and notes

Record here, as work proceeds: the milestone-1 `DOC` violation count and file
list; any `# noqa: DOC...` suppressions with justification; the final
"All checks passed!" transcript; and the resolved file-line for each added
attribute docstring.

## Interfaces and dependencies

No new runtime or dev dependencies. Use tooling already present:

- Ruff (linter/formatter) — enable `DOC` via `pyproject.toml`
  `[tool.ruff.lint] select`. `preview = true` already set.
- pytest with `--doctest-modules --import-mode=importlib` — no plugin needed.
- `ty` for typechecking; `ast` and `inspect` (stdlib) for the introspection
  test.

New artifacts to exist at completion:

- `src/falcon_correlate/unittests/test_public_api_docstrings.py` — introspection
  test over `falcon_correlate.__all__` plus AST checks for attribute docstrings.
- `docs/adr-002-docstring-completeness-and-doctest-gates.md` — convention ADR.
- A `doctest` target in `Makefile` (wired into the committed gates).
- Inline attribute docstrings in `src/falcon_correlate/middleware_utils.py` for
  `correlation_id_var`, `user_id_var`, `RECOMMENDED_LOG_FORMAT`.

Signposted documentation:

- `docs/falcon-correlation-id-middleware-design.md` — §3.3 (contextvars),
  §3.3.3 (req.context dual access), §3.4/§4.6.8/§4.6.9 (logging filter and
  `RECOMMENDED_LOG_FORMAT`), §3.5 (propagation).
- `docs/users-guide.md` — "Accessing the correlation ID", "Context Variables",
  "Logging integration", "httpx propagation", "Celery propagation".
- `docs/developers-guide.md` — "Episodic lint policy" / docstring convention.
- `docs/documentation-style-guide.md` — spelling, examples, formatting.
- `docs/adr-001-two-tier-linting.md` — ADR template.
- `docs/complexity-antipatterns-and-refactoring-strategies.md` — referenced by
  the task brief for refactoring guidance if a module split is forced.
- `docs/contents.md` — documentation index to update.

Signposted skills:

- `execplans` — maintain this plan as a living document.
- `leta` — symbol navigation for the audit and edits (load first).
- `python-types-and-apis` — public signature/typing conventions docstrings
  describe.
- `python-testing` — doctest and the introspection test.
- `python-errors-and-logging` — accurate `Raises` documentation and the
  `ContextualLogFilter` description.
- `en-gb-oxendict` — en-GB Oxford spelling in prose and docstrings.
- `changelog` — only if a CHANGELOG is introduced (it is not; roadmap 6.3.1).
