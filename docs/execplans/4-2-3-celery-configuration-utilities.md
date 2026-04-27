# Provide Celery configuration utilities (4.2.3)

This Execution Plan (ExecPlan) is a living document. The sections
`Constraints`, `Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`,
`Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work
proceeds.

Status: COMPLETE

## Purpose / big picture

Roadmap item 4.2.3 adds an explicit public entry point for Celery users who
want one obvious configuration call instead of relying on import-time side
effects. A consumer can now call
`configure_celery_correlation(app)` once during Celery application setup and
know that all supported correlation propagation handlers are connected:
publish-time propagation through `before_task_publish`, and worker lifecycle
setup and cleanup through `task_prerun` and `task_postrun`.

Success is observable when all of the following are true:

- `src/falcon_correlate/celery.py` exports a public
  `configure_celery_correlation(app)` helper;
- calling that helper connects the publish and worker handlers in one
  idempotent call;
- existing Celery publish behaviour and worker behaviour still work after
  configuration, including the `rpc://` result-backend exception and the
  worker reset-token cleanup semantics;
- unit tests written with `pytest` prove the helper connects every supported
  signal, is safe to call repeatedly, and remains import-safe;
- behavioural tests written with `pytest-bdd` prove a consumer can use the new
  helper to enable both publish propagation and worker-side context exposure;
- `docs/users-guide.md` explains when to use the helper and how it relates to
  the existing import-time auto-registration behaviour;
- `docs/falcon-correlation-id-middleware-design.md` records the final design
  choice for the helper and its relationship to the existing signal handlers;
- `docs/roadmap.md` marks item 4.2.3 complete only after code, tests, and
  documentation are finished; and
- the repository passes `make check-fmt`, `make typecheck`, `make lint`,
  `make test`, `make markdownlint`, and `make nixie`.

Implementation is complete in commit `7189e56` ("Add explicit Celery
correlation configuration", 2026-04-27), with hook-environment validation
stabilized in commit `fc92042` ("Make validation tools available to hooks",
2026-04-27). Verification completed on 2026-04-27 with `make check-fmt`,
`make typecheck`, `make lint`, `make test`, `make markdownlint`, and
`make nixie`.

## Context and orientation

The current Celery integration already lives in
`src/falcon_correlate/celery.py`. That file defines three public handlers:
`propagate_correlation_id_to_celery`,
`setup_correlation_id_in_worker`, and
`clear_correlation_id_in_worker`. It also defines two private registration
helpers, `_maybe_connect_celery_publish_signal()` and
`_maybe_connect_celery_worker_signals()`, and it calls both helpers at module
import time.

The current package root in `src/falcon_correlate/__init__.py` re-exports the
three public handlers and the public `configure_celery_correlation(app)`
configuration helper. The current user guide documents both automatic
registration on import and explicit configuration through the helper, so 4.2.3
is additive rather than a replacement for the existing behaviour.

The existing test suite already covers the publish and worker paths
independently:

- `src/falcon_correlate/unittests/test_celery_publish_signal.py`
- `src/falcon_correlate/unittests/test_celery_worker_signal.py`
- `tests/bdd/celery_publish_signal.feature`
- `tests/bdd/test_celery_publish_signal_steps.py`
- `tests/bdd/celery_worker_signal.feature`
- `tests/bdd/test_celery_worker_signal_steps.py`

Those files are the starting point for 4.2.3 because they already capture the
real behavioural contracts that the new helper must preserve.

The design and maintenance documents that matter most are:

- `docs/roadmap.md` item 4.2.3 for the concrete requirement;
- `docs/falcon-correlation-id-middleware-design.md` sections 3.5.2.2,
  3.5.2.4, and 4.4 for the existing publish and worker contracts;
- `docs/falcon-correlation-id-middleware-design.md` appendices A.8 and A.9
  for the decisions already taken in 4.2.1 and 4.2.2;
- `docs/complexity-antipatterns-and-refactoring-strategies.md` for the
  "bumpy road" warning against growing Celery signal code into a tangle of
  special cases; and
- `docs/users-guide.md` section "Celery propagation" for the current
  consumer-facing story.

## Relevant documentation and skills

The implementer should keep these references open while working:

- `docs/execplans/4-2-1-celery-task-publish-signal-handler.md`
- `docs/execplans/4-2-2-celery-worker-signal-handlers.md`
- `/root/.codex/skills/execplans/SKILL.md`
  Use this to keep the ExecPlan current during implementation.
- `/root/.codex/skills/leta/SKILL.md`
  Use this for semantic navigation of the existing Celery module and tests.
- `/root/.codex/skills/hypothesis-debugging/SKILL.md`
  Use this only if Celery signal behaviour differs from the current test
  assumptions and the root cause is unclear.

## Constraints

- Follow test-driven development. Update or add the relevant unit and
  behavioural tests first, run them, and confirm they fail for the missing
  helper behaviour before implementation begins.
- Keep Celery optional. `import falcon_correlate` must continue to succeed
  when the Celery extra is not installed.
- Preserve the current import-time auto-registration behaviour. The new helper
  is an explicit configuration convenience, not a breaking change in startup
  semantics.
- Implement the helper in `src/falcon_correlate/celery.py` and keep it close
  to the existing signal registration code instead of creating a second Celery
  integration module.
- Reuse the existing public handlers and stable dispatch UIDs. Do not create a
  second copy of the publish or worker signal logic just to satisfy the helper
  API.
- Connect all three supported handlers in one call:
  `before_task_publish`, `task_prerun`, and `task_postrun`.
- Keep the helper idempotent. Repeated calls must not create duplicate
  receivers.
- Keep the helper public and discoverable from the package root unless that
  would break import safety when Celery is absent.
- Keep the implementation scoped to roadmap item 4.2.3. Do not widen the work
  into new propagation features beyond the configuration helper and the
  documentation needed to explain it.
- Record any design decisions in
  `docs/falcon-correlation-id-middleware-design.md`.
- Update `docs/users-guide.md` with any consumer-facing API or behaviour
  change.
- Check off roadmap item 4.2.3 only after implementation, documentation, and
  validation are complete.
- Use British English in documentation.
- Wrap Markdown paragraphs and list items at 80 columns, and keep code blocks
  within 120 columns.
- Before ending the implementation turn, run the full validation suite:
  `make check-fmt`, `make typecheck`, `make lint`, `make test`,
  `make markdownlint`, and `make nixie`.

## Tolerances

- Scope: if the work grows beyond roughly 8 files changed or 250 net lines,
  stop and ask whether the helper should be split from test refactoring or
  documentation updates.
- API shape: if `configure_celery_correlation(app)` cannot cleanly accept the
  roadmap-mandated `app` parameter without a materially different public API,
  stop and confirm the intended signature before proceeding.
- Registration model: if Celery's actual signal semantics require app-specific
  registration rather than the current global-signal model, stop and escalate
  before changing the design.
- Import safety: if exporting the helper from `src/falcon_correlate/__init__.py`
  would make `import falcon_correlate` fail when Celery is absent, stop and
  confirm whether the helper should instead remain under
  `falcon_correlate.celery`.
- Test boundary: if proving the helper behaviour requires a live external
  broker or long-running worker after two focused attempts, stop and ask for a
  decision rather than improvising an unverified substitute.
- Tooling: if `make check-fmt`, `make typecheck`, `make lint`, `make test`,
  `make markdownlint`, or `make nixie` fail for unrelated reasons that cannot
  be fixed within two focused attempts, stop and document the failures.

## Risks

- Risk: the existing import-time registration may hide a broken helper because
  the signals are already connected before tests call it. Mitigation: write
  tests that explicitly disconnect the known receivers by dispatch UID, then
  call the helper and assert reconnection.
- Risk: the `app` parameter may mislead consumers into thinking the helper
  performs app-local registration even though Celery signals are currently
  global. Mitigation: document that contract explicitly and keep the helper
  implementation thin and honest.
- Risk: repeated helper calls or module reloads may register duplicate signal
  receivers. Mitigation: reuse the existing stable dispatch UIDs and add a
  regression test that counts receivers after repeated calls.
- Risk: refactoring the current private registration helpers could accidentally
  change already-working publish or worker semantics. Mitigation: keep the new
  helper as a composition layer over the existing connection logic and rerun
  the existing targeted Celery tests.
- Risk: BDD tests for the helper could become brittle if they duplicate too
  much publish and worker setup. Mitigation: share small local fixtures or
  helper functions, but keep the behavioural assertions focused on the public
  configuration entry point.

## Proposed implementation

### Milestone 1: characterize the existing registration contract

Start by confirming exactly how the current module registers Celery signals and
what needs to be refactored to make that registration available through one
public helper without changing behaviour.

Inspect the current receiver state and verify that the known dispatch UIDs are
the ones already used by the module:

```python
from celery.signals import before_task_publish, task_postrun, task_prerun

from falcon_correlate.celery import (
    _BEFORE_TASK_PUBLISH_DISPATCH_UID,
    _TASK_POSTRUN_DISPATCH_UID,
    _TASK_PRERUN_DISPATCH_UID,
)

print(before_task_publish.receivers)
print(task_prerun.receivers)
print(task_postrun.receivers)
print(_BEFORE_TASK_PUBLISH_DISPATCH_UID)
print(_TASK_PRERUN_DISPATCH_UID)
print(_TASK_POSTRUN_DISPATCH_UID)
```

The goal of this milestone is to remove guesswork before any tests are
written. The implementation turn should know whether it can simply compose the
existing helpers or whether it needs a small internal refactor such as a
single `_maybe_connect_celery_signals()` helper that both import-time startup
and `configure_celery_correlation(app)` can call.

### Milestone 2: write failing tests for the public configuration helper

Prefer focused new tests for the helper rather than burying the new assertions
inside the older publish and worker files. The preferred layout is:

- `src/falcon_correlate/unittests/test_celery_configuration.py`
- `tests/bdd/celery_configuration.feature`
- `tests/bdd/test_celery_configuration_steps.py`

The unit tests should use `pytest.importorskip("celery")` and cover at least
these cases:

1. `configure_celery_correlation(app)` reconnects
   `before_task_publish`, `task_prerun`, and `task_postrun` when those
   receivers have been disconnected by dispatch UID.
2. Calling the helper twice still yields exactly one integration receiver per
   signal.
3. The helper returns the same `app` instance if that contract is chosen, so
   application-factory code can write
   `celery_app = configure_celery_correlation(celery_app)`.
4. The helper is re-exported from `src/falcon_correlate/__init__.py` if that
   remains import-safe.
5. Existing targeted tests for publish and worker semantics still pass after
   the registration refactor.

The behavioural tests should prove the consumer-visible story. The cleanest
shape is two scenarios:

1. A scenario that disconnects the known receivers, configures a Celery app
   with `configure_celery_correlation(app)`, publishes a task, and observes
   that the outgoing broker publish uses the ambient request correlation ID.
2. A scenario that disconnects the known receivers, configures a Celery app
   with `configure_celery_correlation(app)`, drives the worker lifecycle, and
   observes that `correlation_id_var.get()` is visible inside the task and
   cleaned up afterwards.

Run the targeted tests and confirm the red phase fails because the helper does
not exist yet or does not connect all signals in one call.

```plaintext
set -o pipefail
uv run pytest -v \
  src/falcon_correlate/unittests/test_celery_configuration.py \
  tests/bdd/test_celery_configuration_steps.py \
  | tee /tmp/4-2-3-red-tests.log
```

The failure must be a missing symbol or missing behaviour, not an environment
problem.

### Milestone 3: implement the helper by composing the existing signal wiring

Extend `src/falcon_correlate/celery.py`.

The implementation should stay deliberately small:

1. Factor the existing registration path so there is one internal function
   that can connect all supported Celery handlers.
2. Add a public `configure_celery_correlation(app)` helper that calls that
   internal registration function.
3. Keep the helper idempotent by reusing the existing dispatch UIDs and
   `_safe_connect_signal(...)`.
4. Preserve import-time registration by calling the same internal function
   from module import time.
5. Export the helper in `__all__`, and re-export it from
   `src/falcon_correlate/__init__.py` if import safety remains intact.

The helper should not introduce per-app state unless Milestone 1 proves that
the current global-signal model is insufficient. If the `app` parameter is
not otherwise needed, the helper may still accept and return the app for
ergonomic, explicit configuration in application factories. That is the
current draft direction for approval.

After implementation, rerun the targeted tests:

```plaintext
set -o pipefail
uv run pytest -v \
  src/falcon_correlate/unittests/test_celery_configuration.py \
  tests/bdd/test_celery_configuration_steps.py \
  src/falcon_correlate/unittests/test_celery_publish_signal.py \
  src/falcon_correlate/unittests/test_celery_worker_signal.py \
  tests/bdd/test_celery_publish_signal_steps.py \
  tests/bdd/test_celery_worker_signal_steps.py \
  | tee /tmp/4-2-3-green-tests.log
```

### Milestone 4: update consumer and maintainer documentation

Update `docs/users-guide.md` so the Celery section explains both supported
activation styles:

- implicit activation through package import, which remains supported;
- explicit activation through `configure_celery_correlation(app)`, which is
  the clearer option for application factories and worker bootstrap code.

Document the exact contract chosen for the helper:

- its import path;
- whether it returns the app instance;
- that it connects publish and worker handlers together; and
- that calling it repeatedly is safe.

Update `docs/falcon-correlation-id-middleware-design.md` with a new appendix
entry for task 4.2.3 that records the final design decision, including why the
helper exists even though import-time registration already works.

Only after code, tests, and docs are complete should `docs/roadmap.md` mark
4.2.3 as done.

### Milestone 5: run the full repository validation suite

Run the full required gates, capturing output with `tee`:

```plaintext
set -o pipefail
make check-fmt | tee /tmp/4-2-3-check-fmt.log
set -o pipefail
make typecheck | tee /tmp/4-2-3-typecheck.log
set -o pipefail
make lint | tee /tmp/4-2-3-lint.log
set -o pipefail
make test | tee /tmp/4-2-3-test.log
set -o pipefail
make markdownlint | tee /tmp/4-2-3-markdownlint.log
set -o pipefail
make nixie | tee /tmp/4-2-3-nixie.log
```

Review the logs if any command fails. The work is not complete until all six
commands pass.

## Progress

- [x] 2026-04-21: Reviewed `docs/roadmap.md`, the current Celery design
  sections, the user guide, the complexity guidance, and the completed
  execplans for 4.2.1 and 4.2.2.
- [x] 2026-04-21: Inspected `src/falcon_correlate/celery.py`,
  `src/falcon_correlate/__init__.py`, and the current Celery unit and BDD
  tests to establish the real starting point for 4.2.3.
- [x] 2026-04-21: Drafted this ExecPlan and recorded the proposed approach for
  approval before implementation.
- [x] 2026-04-27: Resumed implementation on branch
  `celery-correlation-propagation-5nogn4`; confirmed the worktree was clean
  and the checked-in plan still represented the pre-implementation draft.
- [x] 2026-04-27: Treated the user's continuation request as approval to
  implement the planned functionality.
- [x] 2026-04-27: Added targeted unit and behavioural tests for
  `configure_celery_correlation(app)`.
- [x] 2026-04-27: Confirmed the targeted red phase failed during collection
  because `configure_celery_correlation` was not yet importable from
  `falcon_correlate.celery`.
- [x] 2026-04-27: Implemented the helper as a thin public wrapper around a new
  `_maybe_connect_celery_signals()` internal connector and re-exported it from
  the package root.
- [x] 2026-04-27: Ran the Celery-focused targeted suite; 27 tests passed,
  covering the new configuration helper and existing publish and worker signal
  behaviour.
- [x] Implement the helper and any minimal internal refactor required to share
  signal connection logic.
- [x] 2026-04-27: Updated the users' guide, design document, and roadmap for
  the explicit configuration helper and marked roadmap item 4.2.3 complete.
- [x] Update the users' guide, design document, and roadmap as part of the
  implementation turn.
- [x] 2026-04-27: Ran the full validation suite successfully:
  `make check-fmt`, `make typecheck`, `make lint`, `make test`,
  `make markdownlint`, and `make nixie`.
- [x] Run the full validation suite and record outcomes.

## Surprises & Discoveries

- The repository already has import-time Celery signal registration in
  `src/falcon_correlate/celery.py`, so 4.2.3 is not about inventing Celery
  propagation. It is about surfacing an explicit, consumer-friendly
  configuration API over behaviour that already exists.
- The current BDD fixtures connect the existing private registration helpers
  directly. That means the new helper can become the public behavioural entry
  point without needing a live broker or long-running worker.
- The current users' guide already tells consumers that importing the package
  is enough. The helper documentation must therefore explain "why use this"
  rather than pretending there was no previous configuration path.
- 2026-04-27: The resumed worktree did not contain the implementation
  described in the previous task context. The only branch-local commit was the
  ExecPlan draft, so implementation is proceeding from the documented starting
  point rather than attempting to preserve unavailable edits.
- 2026-04-27: Tests that prove the helper must disconnect the known
  `before_task_publish`, `task_prerun`, and `task_postrun` receivers by
  dispatch UID first; otherwise import-time registration can make a missing or
  incomplete helper look correct.

## Decision Log

- 2026-04-21: Draft decision: keep `configure_celery_correlation(app)`
  additive to import-time auto-registration rather than replacing it.
  Rationale: that preserves backwards compatibility and matches the current
  user-guide contract.
- 2026-04-21: Draft decision: implement the helper as a thin composition layer
  over the existing publish and worker connection helpers, or over a tiny new
  shared internal helper if that refactor makes the code clearer. Rationale:
  this avoids duplicating signal logic and respects the complexity guidance in
  `docs/complexity-antipatterns-and-refactoring-strategies.md`.
- 2026-04-21: Draft decision: prefer returning the same `app` instance from
  `configure_celery_correlation(app)` so Celery application factory code gets
  a clean, chainable API. Rationale: the roadmap fixes the parameter name but
  not the return type, and returning the app is the most ergonomic public
  contract if it does not create type or import-safety problems.
- 2026-04-27: Final decision: return the same `app` instance from
  `configure_celery_correlation(app)`. Rationale: the helper does not need
  app-local state because the existing integration uses Celery's global signal
  registry, and returning the app keeps application-factory code concise.

## Outcomes & Retrospective

Roadmap item 4.2.3 is complete. The package now exposes
`configure_celery_correlation(app)` from both `falcon_correlate.celery` and
the package root. The helper reuses the existing publish and worker signal
registration helpers through `_maybe_connect_celery_signals()`, returns the
same app instance, and remains idempotent through the existing Celery dispatch
UIDs.

The main implementation lesson is that tests for explicit configuration must
first disconnect the import-time receivers by dispatch UID. Without that setup,
automatic registration can mask a broken helper because the signals are
already connected before the test exercises the public API.

Validation completed successfully on 2026-04-27:

- `make check-fmt`
- `make typecheck`
- `make lint`
- `make test` (`345 passed, 11 skipped`)
- `make markdownlint`
- `make nixie`

Post-turn hook validation initially failed because the non-interactive hook
environment did not include the user-local tool directories that provide
`ruff`, `ty`, `uv`, `nixie`, and `markdownlint-cli2`. The Makefile now
prepends `$(HOME)/.local/bin` and `$(HOME)/.bun/bin` to `PATH` so local and
hook validation resolve the same project tools.

Author/verification note: this ExecPlan was synchronized with the delivered
implementation on 2026-04-27 after review of commits `7189e56` and `fc92042`,
the updated user guide, design document, roadmap, unit tests, and BDD tests.
