# Implement Celery worker signal handlers (4.2.2)

This Execution Plan (ExecPlan) is a living document. The sections
`Constraints`, `Tolerances`, `Risks`, `Progress`, `Surprises &
Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up
to date as work proceeds.

Status: DRAFT

Implementation must not begin until this plan is explicitly approved.

## Purpose / big picture

Task 4.2.2 closes the worker-side gap in roadmap section 4.2. After this work,
Celery tasks that arrive with a propagated AMQP `correlation_id` will expose
that value through `falcon_correlate.correlation_id_var` while the task body is
running, and the worker process will clear that context again after the task
finishes. That gives logging filters and downstream propagation utilities the
same correlation context inside Celery workers that Falcon request handlers
already have inside web requests.

Success is observable when all of the following are true:

- `src/falcon_correlate/celery.py` defines
  `setup_correlation_id_in_worker` for `task_prerun` and
  `clear_correlation_id_in_worker` for `task_postrun`;
- the worker-side handlers use stored reset tokens rather than bluntly setting
  `correlation_id_var` to `None`;
- a unit test proves `correlation_id_var.get()` returns the task request's
  correlation ID during worker execution;
- a unit test proves worker cleanup restores a clean context after task
  execution;
- a behavioural test written with `pytest-bdd` demonstrates the worker-side
  lifecycle through a realistic Celery task boundary;
- `docs/users-guide.md` tells consumers how worker processes gain this
  behaviour and what to expect inside tasks;
- `docs/falcon-correlation-id-middleware-design.md` records the final
  implementation decisions for the worker path;
- `docs/roadmap.md` marks item 4.2.2 complete only after code, tests, and
  documentation are done; and
- the repository passes `make check-fmt`, `make typecheck`, `make lint`,
  `make test`, `make markdownlint`, and `make nixie`.

## Context and orientation

The current publish-path integration already exists in
`src/falcon_correlate/celery.py`. That module is the correct starting point for
this task because it already isolates the optional Celery dependency,
registers signals idempotently, and is re-exported safely from
`src/falcon_correlate/__init__.py`.

The current tests for Celery publish propagation live in
`src/falcon_correlate/unittests/test_celery_publish_signal.py`,
`tests/bdd/celery_publish_signal.feature`, and
`tests/bdd/test_celery_publish_signal_steps.py`. Those files establish the
repository's conventions for optional Celery tests, `pytest.importorskip`, and
behaviour-driven scenarios that exercise Celery without requiring a live
external broker.

The worker-side behaviour is described in
`docs/falcon-correlation-id-middleware-design.md` section 3.5.2.4 and in the
example code block in section 4.4. Those sections already prescribe the core
shape of the feature: read `task.request.correlation_id` during `task_prerun`,
store reset tokens, and reset the context during `task_postrun`.

The current user guide in `docs/users-guide.md` explicitly says the present
release covers only the publish path and that worker-side setup will be added
later. This task must remove that limitation and replace it with concrete
worker guidance.

The complexity guidance in
`docs/complexity-antipatterns-and-refactoring-strategies.md` matters here
because Celery signal functions can easily turn into a "bumpy road" of
conditionals. The implementation should keep the public signal handlers thin
and, if needed, extract small private helpers so the worker lifecycle stays
easy to read and test.

## Constraints

- Follow test-driven development. Write or update the relevant unit and
  behavioural tests first, run them, and confirm they fail for the expected
  missing worker behaviour before implementation begins.
- Keep Celery optional. `import falcon_correlate` must continue to succeed when
  Celery is not installed.
- Extend the existing feature module `src/falcon_correlate/celery.py` rather
  than creating a second Celery integration module.
- Reuse the existing `correlation_id_var`; do not introduce a second worker
  context variable for the same value.
- Store reset tokens in an internal worker-specific `ContextVar` so cleanup can
  call `reset()` and restore any pre-existing ambient value correctly.
- Keep the implementation scoped to roadmap item 4.2.2. Do not implement the
  public `configure_celery_correlation(app)` helper from 4.2.3 in the same
  change unless a blocker makes it strictly necessary.
- Preserve import-time signal registration behaviour. Importing the package in
  a Celery worker process should remain sufficient to register the integration
  when Celery is installed.
- Use British English in documentation.
- Wrap Markdown paragraphs and list items at 80 columns, and keep code blocks
  within 120 columns.
- Before ending the implementation turn, run the full validation suite:
  `make check-fmt`, `make typecheck`, `make lint`, `make test`,
  `make markdownlint`, and `make nixie`.

## Tolerances

- Scope: if the work grows beyond roughly 12 files changed or 450 net lines,
  stop and ask whether worker setup should be split from documentation or API
  surfacing changes.
- API shape: if making the worker handlers public requires a broader package
  API redesign than adding two exports, stop and confirm the intended public
  surface before proceeding.
- Worker test boundary: if a realistic local worker-lifecycle test cannot be
  exercised without an external broker or a long-running Celery worker after
  two focused attempts, stop and ask whether a signal-level behavioural test is
  acceptable.
- Context restoration: if the implementation cannot preserve pre-existing
  ambient `correlation_id_var` values via reset tokens, stop and escalate
  instead of substituting a lossy cleanup strategy.
- Tooling: if `make check-fmt`, `make typecheck`, `make lint`, or `make test`
  fail for unrelated reasons that cannot be resolved within two focused fix
  attempts, stop and document the failures.

## Risks

- Risk: `task_postrun` may run without a matching stored token, for example in
  tests or partial signal registration. Mitigation: make cleanup a no-op when
  the token store is empty, and cover that path with a unit test.
- Risk: a worker thread might already have an ambient correlation ID set before
  `task_prerun` runs. Mitigation: store the `ContextVar.set()` token and call
  `reset(token)` during cleanup rather than forcing `None`.
- Risk: Celery eager execution may not populate `task.request.correlation_id`
  in exactly the same way as a real worker. Mitigation: begin with a short
  prototype to determine the smallest realistic boundary that still proves the
  worker contract.
- Risk: adding more import-time signal registration could create duplicate
  receivers across reloads. Mitigation: mirror the existing publish-path use of
  stable `dispatch_uid` values and add a regression test for idempotent worker
  registration.
- Risk: the internal token store can become stale if cleanup forgets to clear
  it after `reset()`. Mitigation: assert in tests that the internal store is
  empty after `task_postrun`.

## Proposed implementation

### Milestone 1: characterise the worker boundary before changing code

Start by confirming the smallest realistic Celery execution path that exposes
`task.request.correlation_id` and fires `task_prerun` and `task_postrun`. The
goal is to choose a behavioural test that proves the worker contract without
guessing.

Inspect the current dependency state and run a short prototype before writing
tests:

```plaintext
set -o pipefail
make build | tee /tmp/4-2-2-build.log
python - <<'PY'
from celery import Celery
from celery.signals import task_postrun, task_prerun

app = Celery("probe", broker="memory://")
app.conf.task_always_eager = True

events = []

@task_prerun.connect(dispatch_uid="probe-prerun", weak=False)
def on_prerun(task=None, **kwargs):
    events.append(("prerun", getattr(task.request, "correlation_id", None)))

@task_postrun.connect(dispatch_uid="probe-postrun", weak=False)
def on_postrun(task=None, **kwargs):
    events.append(("postrun", getattr(task.request, "correlation_id", None)))

@app.task(name="probe.echo")
def echo(value):
    events.append(("body", value))
    return value

echo.apply(args=("payload",), correlation_id="probe-correlation-id")
print(events)
PY
```

If that prototype proves eager execution already exercises the worker contract,
use it as the behavioural boundary. If it does not, fall back to an explicit
signal-driven task object in the BDD layer and record that decision in the
design document during implementation.

### Milestone 2: write failing tests for worker setup and cleanup

Add dedicated worker-focused tests rather than folding this behaviour into the
publish-path files. The preferred file layout is:

- `src/falcon_correlate/unittests/test_celery_worker_signal.py`
- `tests/bdd/celery_worker_signal.feature`
- `tests/bdd/test_celery_worker_signal_steps.py`

The unit tests should use `pytest.importorskip("celery")` and cover at least
these cases:

1. `setup_correlation_id_in_worker` reads `task.request.correlation_id`,
   writes it into `correlation_id_var`, and stores the reset token in the
   internal token store.
2. `setup_correlation_id_in_worker` is a no-op when the task request has no
   correlation ID.
3. `clear_correlation_id_in_worker` resets `correlation_id_var` using the
   stored token and clears the token store.
4. `clear_correlation_id_in_worker` is a no-op when no tokens were stored.
5. worker signal registration is connected once, using stable dispatch IDs.
6. if the new handlers are re-exported from `src/falcon_correlate/__init__.py`,
   the package-root exports are covered explicitly.

The behavioural test should prove the consumer-visible lifecycle:

1. arrange a Celery task whose execution body reads `correlation_id_var.get()`;
2. trigger the smallest realistic worker path chosen in Milestone 1;
3. assert the task body observed the propagated correlation ID; and
4. assert `correlation_id_var.get()` is clean again after the task completes.

Run the new test files and confirm the red phase fails because the worker
handlers do not yet exist.

```plaintext
set -o pipefail
uv run pytest -v \
  src/falcon_correlate/unittests/test_celery_worker_signal.py \
  tests/bdd/test_celery_worker_signal_steps.py \
  | tee /tmp/4-2-2-red-tests.log
```

The failure should be a missing symbol or missing behaviour, not an
environmental problem.

### Milestone 3: implement the worker signal handlers in the existing Celery module

Extend `src/falcon_correlate/celery.py` rather than creating a new file.

Add a small internal token store, likely named `_celery_context_tokens`, using
`contextvars.ContextVar[...]`. The stored value should be a typed mapping of
reset tokens keyed by context name so the worker path can grow cleanly later if
`user_id_var` is propagated too.

Implement `setup_correlation_id_in_worker` so it:

1. reads `task.request.correlation_id` safely;
2. returns immediately when the value is missing or falsey;
3. calls `correlation_id_var.set(...)` and stores the returned reset token in
   the internal token store; and
4. remains small enough that its control flow is obvious at a glance.

Implement `clear_correlation_id_in_worker` so it:

1. reads the stored tokens from the internal token store;
2. resets `correlation_id_var` with the stored token when present; and
3. clears the internal token store afterwards.

Add an internal worker-signal connection helper such as
`_maybe_connect_celery_worker_signals()` and call it from the module import
path beside the existing publish-signal helper. Use dedicated stable dispatch
IDs for `task_prerun` and `task_postrun`, and keep the helper idempotent.

If the package root already re-exports public Celery helpers, extend
`src/falcon_correlate/__init__.py` and `__all__` to include the new worker
handlers so the public API stays coherent. If implementation reveals a reason
not to expose them publicly, stop and confirm that API choice before
proceeding.

After implementation, rerun the targeted tests:

```plaintext
set -o pipefail
uv run pytest -v \
  src/falcon_correlate/unittests/test_celery_worker_signal.py \
  tests/bdd/test_celery_worker_signal_steps.py \
  | tee /tmp/4-2-2-green-tests.log
```

### Milestone 4: update the design doc, user guide, and roadmap

Update `docs/falcon-correlation-id-middleware-design.md` in two places.

First, revise the implementation appendix so it records the actual worker-side
decisions, including:

- where the worker handlers live;
- how reset tokens are stored;
- how signal registration stays idempotent; and
- what behavioural test boundary was chosen and why.

Second, if the design doc still presents the section 4.4 code as aspirational,
make sure it matches the concrete implementation or clearly points to the final
library API.

Update `docs/users-guide.md` so consumers know:

- worker processes must import `falcon_correlate` just as publisher processes
  do;
- `correlation_id_var.get()` is available inside a running Celery task when
  the incoming task request carried a correlation ID; and
- the worker context is cleared automatically after the task finishes.

Replace the current sentence that says worker-side setup will be added later
with concrete worker behaviour and a small example that is useful to a consumer
configuring task logging.

Only after the code, tests, and documentation are complete should
`docs/roadmap.md` item 4.2.2 and its child checkboxes be changed from `[ ]` to
`[x]`.

### Milestone 5: run the full validation suite

Before ending the implementation turn, run the full project gates through
`tee`, keeping `pipefail` enabled so failures are not hidden:

```plaintext
set -o pipefail
make check-fmt | tee /tmp/4-2-2-check-fmt.log
make typecheck | tee /tmp/4-2-2-typecheck.log
make lint | tee /tmp/4-2-2-lint.log
make test | tee /tmp/4-2-2-test.log
make markdownlint | tee /tmp/4-2-2-markdownlint.log
make nixie | tee /tmp/4-2-2-nixie.log
```

Implementation is complete only when every command above succeeds and the new
worker tests remain green inside the full suite.

## Progress

- [x] 2026-04-08: Reviewed the current roadmap item, design sections 3.5.2.4
  and 4.4, the existing Celery publish integration, the current user guide
  wording, and the complexity guidance.
- [x] 2026-04-08: Drafted this ExecPlan in
  `docs/execplans/4-2-2-celery-worker-signal-handlers.md`.
- [ ] After approval: run Milestone 1 and choose the final worker test
  boundary.
- [ ] After approval: add failing unit and behavioural tests for worker setup
  and cleanup.
- [ ] After approval: implement the worker handlers and idempotent signal
  registration.
- [ ] After approval: update the design doc, user guide, and roadmap.
- [ ] After approval: run the full validation suite and capture the evidence.

## Surprises & Discoveries

- The publish side of Celery propagation is already implemented in
  `src/falcon_correlate/celery.py`, so 4.2.2 should extend that file rather
  than introducing a second Celery integration module.
- `docs/users-guide.md` currently documents Celery publish propagation and
  explicitly states that worker-side setup has not been added yet. That text
  must change as part of the implementation turn.
- The design document already contains a concrete worker-side code sketch,
  including an internal `_celery_context_tokens` store. The implementation
  should stay aligned with that unless a tested Celery constraint proves the
  sketch wrong.

## Decision Log

- 2026-04-08: This plan assumes worker-side behaviour belongs in
  `src/falcon_correlate/celery.py`, not in `middleware.py` or a new module,
  because the existing Celery publish integration already owns the optional
  dependency boundary.
- 2026-04-08: This plan requires reset-token storage for cleanup instead of a
  hard reset to `None`, because `ContextVar.reset(token)` is the only safe way
  to restore any pre-existing ambient value in the current execution context.
- 2026-04-08: The plan includes a short prototype milestone to choose the
  behavioural test boundary. Celery eager execution may or may not expose the
  same request metadata as a real worker, and that should be proven before the
  tests are committed.

## Outcomes & Retrospective

No implementation has started. Populate this section after the plan is
approved and executed, including the final test boundary chosen, the commands
run, and any follow-up work that should feed roadmap item 4.2.3.
