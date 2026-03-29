# Implement Celery task publish signal handler (4.2.1)

This Execution Plan (ExecPlan) is a living document. The sections
`Constraints`, `Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`,
`Decision log`, and `Outcomes & retrospective` must be kept up to date as work
proceeds.

Status: DRAFT

This plan is for the draft phase only. Do not begin implementation until the
user explicitly approves the plan.

## Purpose / big picture

Task 4.2.1 closes the first Celery propagation gap in roadmap section 4.2.
After this work, code running inside a Falcon request that enqueues a Celery
task will automatically publish the current correlation ID into the outgoing
task message properties, using Celery's native `correlation_id` field.

Success is observable when:

- a new signal handler named `propagate_correlation_id_to_celery` exists
  in the library;
- the handler is connected to Celery's `before_task_publish` signal;
- publishing a Celery task while `correlation_id_var` is set results in the
  outgoing message properties containing that value under `correlation_id`;
- publishing a Celery task with no correlation ID in context leaves the
  message properties unchanged;
- the behaviour is covered by unit tests written with `pytest` and
  behavioural tests written with `pytest-bdd`;
- `docs/users-guide.md` documents how a consumer enables and uses the Celery
  publish integration;
- `docs/falcon-correlation-id-middleware-design.md` records the concrete
  implementation decisions for this task;
- `docs/roadmap.md` marks item 4.2.1 complete only after code, tests, and
  documentation are done; and
- the repository passes `make check-fmt`, `make typecheck`, `make lint`,
  `make test`, `make markdownlint`, and `make nixie`.

## Context and orientation

The current package already has one downstream propagation feature domain in
`src/falcon_correlate/httpx.py`. That module is the closest precedent for this
task because it keeps the optional dependency isolated, uses import-safe
runtime guards, and is covered by both unit and BDD tests.

The current package root in `src/falcon_correlate/__init__.py` eagerly
re-exports the `httpx` utilities because that module remains import-safe when
`httpx` is not installed. Celery integration should follow the same import
contract if it is re-exported from the package root; otherwise a user who does
not install the Celery extra could lose the ability to import
`falcon_correlate` at all.

The design document sections relevant to this task are:

- `docs/falcon-correlation-id-middleware-design.md` §3.5.2.1
- `docs/falcon-correlation-id-middleware-design.md` §3.5.2.2
- `docs/falcon-correlation-id-middleware-design.md` §4.4

The roadmap requirements are in `docs/roadmap.md` item 4.2.1. The complexity
guidance in `docs/complexity-antipatterns-and-refactoring-strategies.md` argues
against growing large, mixed-responsibility modules, so the Celery work should
live in its own feature module rather than being added to `middleware.py` or
folded into `httpx.py`.

There is no existing Celery integration in the repository, and `pyproject.toml`
does not yet declare a Celery optional extra or dev dependency. That means the
implementation turn will need to establish a supported Celery version and add
the dependency in a way that preserves the library's optional-integration model.

## Constraints

- Follow test-driven development. Add or update tests first, run them to
  confirm they fail for the expected reason, then implement the feature.
- Keep Celery optional. Installing `falcon-correlate` without the Celery extra
  must continue to work.
- Preserve package import safety. `import falcon_correlate` must still succeed
  when Celery is not installed.
- Use Celery's message `properties["correlation_id"]` field for propagation,
  matching the design document.
- Prefer a new feature module such as `src/falcon_correlate/celery.py` so the
  optional integration remains isolated and easy to discover.
- Reuse the existing `correlation_id_var` rather than introducing a second
  propagation context.
- Keep the implementation narrowly scoped to roadmap item 4.2.1. Do not
  implement worker handlers from 4.2.2 or the full configuration helper from
  4.2.3 in the same change unless that becomes strictly necessary for a working
  publish-path implementation.
- Use British English in documentation.
- Wrap Markdown paragraphs and list items at 80 columns, and keep code blocks
  within 120 columns.
- Run the full required validation suite before finishing the implementation
  turn: `make check-fmt`, `make typecheck`, `make lint`, `make test`,
  `make markdownlint`, and `make nixie`.

## Tolerances (exception triggers)

- Scope: if the work grows beyond 10 files changed or roughly 350 net lines,
  stop and ask whether the Celery work should be split from documentation or
  packaging changes.
- Dependency: if the implementation needs a new mandatory runtime dependency
  instead of an optional Celery extra, stop and escalate.
- API shape: if connecting the signal safely requires changing the existing
  package import contract or renaming the roadmap-mandated handler, stop and
  escalate.
- Signal semantics: if the supported Celery version does not provide a mutable
  `properties` mapping to `before_task_publish`, stop and confirm the fallback
  approach before proceeding.
- Test environment: if Celery publishing cannot be exercised locally without a
  live external broker after two focused attempts, stop and document the
  blocker instead of improvising an unverified substitute.
- Tooling: if `make check-fmt`, `make typecheck`, `make lint`, or `make test`
  fail for unrelated reasons that cannot be resolved within two focused fix
  attempts, stop and document the failures.

## Risks

- Risk: repeated imports or test reloading could connect the same signal
  handler multiple times. Mitigation: inspect Celery signal connection
  mechanics up front and make the connection idempotent, for example via a
  stable dispatch identifier or a guarded connection helper.
- Risk: the design document's `if properties is None: properties = {}` example
  may not actually update the outbound message because rebinding a local
  variable does not mutate Celery's publish state. Mitigation: verify the
  supported signal contract against the installed Celery version and encode the
  real supported behaviour in tests before implementation.
- Risk: publishing a task through Celery may require more setup than the unit
  test boundary. Mitigation: use the `memory://` broker or patch the publish
  boundary with a tight integration test so the behavioural test still proves
  the real publish path without external services.
- Risk: the library now has a precedent of "fill, do not overwrite" for
  propagated metadata in `ContextualLogFilter` and the `httpx` helpers. Celery
  may present an explicit caller-provided `correlation_id`, creating a policy
  choice. Mitigation: decide that policy in the red tests first and document it
  explicitly in the design appendix.
- Risk: adding Celery to the package root exports could break users without the
  extra if the new module is not import-safe. Mitigation: keep all Celery
  imports guarded at runtime or avoid root re-export if import safety cannot be
  preserved cleanly.

## Proposed implementation

### Milestone 1: establish the Celery contract and add the dependency

Start by adding Celery as an optional dependency in `pyproject.toml` and also
to the `dev` dependency group so local validation can exercise the integration.
Pick one supported major range and record it in the design appendix during
implementation. The likely shape is:

- `[project.optional-dependencies].celery = ["celery>=5,<6"]`
- add the same range to `[dependency-groups].dev`

After updating `pyproject.toml`, sync the environment and inspect the concrete
APIs that the code will target.

```plaintext
set -o pipefail
make build | tee /tmp/4-2-1-build.log
python - <<'PY'
import inspect
import celery
from celery.signals import before_task_publish

print(celery.__version__)
print(before_task_publish)
print(inspect.signature(before_task_publish.connect))
PY
```

The goal of this step is to remove guesswork around Celery version behaviour,
signal connection options, and optional-dependency availability before any
tests are written.

### Milestone 2: write failing tests for the publish path

Add new focused tests rather than extending the `httpx` files. Use names that
match the feature domain clearly:

- `src/falcon_correlate/unittests/test_celery_publish_signal.py`
- `tests/bdd/celery_publish_signal.feature`
- `tests/bdd/test_celery_publish_signal_steps.py`

The unit tests should use `pytest.importorskip("celery")` in the same pattern
used for other optional integrations, and they should prove at least the
following:

- `propagate_correlation_id_to_celery` writes the current
  `correlation_id_var.get()` value into an existing `properties` mapping;
- when the context variable is unset or `None`, the handler leaves the mapping
  unchanged;
- the signal handler is connected to `before_task_publish`;
- the connection is effectively idempotent under normal import usage; and
- if the implementation chooses a "do not overwrite explicit
  correlation_id" policy, that behaviour is locked in with a regression test.

The behavioural tests should exercise the real publish path rather than merely
calling the handler directly. The preferred approach is:

1. Create a tiny temporary Celery app configured with `broker="memory://"`
   and a dummy task.
2. Set `correlation_id_var` in the test context.
3. Trigger `task.apply_async()` or `delay()`.
4. Capture the publish-time message properties at the broker boundary, most
   likely by patching the relevant Kombu publish call or attaching a probe that
   can see the final publish kwargs.

That behavioural layer should prove what a consumer cares about: publishing a
task causes the outgoing message to carry the correlation ID automatically.

Run the new test files and confirm they fail before feature code is added.

```plaintext
set -o pipefail
uv run pytest -v \
  src/falcon_correlate/unittests/test_celery_publish_signal.py \
  tests/bdd/test_celery_publish_signal_steps.py \
  | tee /tmp/4-2-1-red-tests.log
```

The red-phase evidence should show missing code or missing behaviour, not
environment breakage.

### Milestone 3: implement the signal handler in a dedicated Celery module

Create a new feature module at `src/falcon_correlate/celery.py`.

That module should:

- define `propagate_correlation_id_to_celery`;
- keep Celery imports guarded so the module remains import-safe when Celery is
  absent;
- connect the handler to `before_task_publish` when Celery is available; and
- keep the connection mechanism small and explicit so roadmap item 4.2.3 can
  later build on it rather than fight it.

The handler itself should stay intentionally thin:

1. Read the current value from `correlation_id_var.get()`.
2. Return immediately if the value is falsey.
3. Mutate the outbound `properties` mapping in place when the supported Celery
   signal contract provides one.
4. Follow the policy chosen in tests for an already-present
   `properties["correlation_id"]` value.

If root-level package re-export is desired, update
`src/falcon_correlate/__init__.py` and `__all__` only if the new module is
genuinely import-safe without Celery. If that cannot be guaranteed cleanly,
keep the public import path explicit as
`falcon_correlate.celery.propagate_correlation_id_to_celery` and document that
decision.

After implementation, rerun the targeted tests:

```plaintext
set -o pipefail
uv run pytest -v \
  src/falcon_correlate/unittests/test_celery_publish_signal.py \
  tests/bdd/test_celery_publish_signal_steps.py \
  | tee /tmp/4-2-1-green-tests.log
```

### Milestone 4: update consumer and maintainer documentation

Update `docs/users-guide.md` with a new Celery propagation section that covers:

- the Celery optional dependency and how to install it;
- where the signal handler lives and whether importing the module is enough to
  register it;
- what behaviour consumers get when they publish tasks inside a request
  context; and
- any important policy detail, such as whether an explicitly supplied
  `correlation_id` wins over the ambient request context.

Update `docs/falcon-correlation-id-middleware-design.md` with a new appendix
entry for this task, most likely `A.8`, recording the concrete design decisions
taken during delivery. Capture at least:

- module placement and optional-dependency strategy;
- signal connection strategy and any idempotence guard;
- the overwrite or preserve policy for pre-existing message
  `correlation_id` values; and
- the supported behaviour when Celery does or does not provide a mutable
  `properties` mapping.

Update `docs/roadmap.md` by checking off 4.2.1 and its sub-items only after the
implementation and full validation are green.

### Milestone 5: run full validation

Run the required quality gates with `tee` so the logs survive command output
truncation:

```plaintext
set -o pipefail
make check-fmt | tee /tmp/4-2-1-check-fmt.log
set -o pipefail
make typecheck | tee /tmp/4-2-1-typecheck.log
set -o pipefail
make lint | tee /tmp/4-2-1-lint.log
set -o pipefail
make test | tee /tmp/4-2-1-test.log
set -o pipefail
make markdownlint | tee /tmp/4-2-1-markdownlint.log
set -o pipefail
make nixie | tee /tmp/4-2-1-nixie.log
```

Success at this milestone means the repository is fully green and the roadmap
item can be marked complete with evidence.

## Progress

- [x] (2026-03-29) Review roadmap, design document, existing execplans, and
  current optional-integration patterns.
- [x] (2026-03-29) Draft this ExecPlan.
- [ ] Add Celery optional dependency and dev dependency; inspect the concrete
  signal contract.
- [ ] Add failing unit tests for the publish signal handler.
- [ ] Add failing behavioural tests for the publish path.
- [ ] Implement `propagate_correlation_id_to_celery` and connect it to
  `before_task_publish`.
- [ ] Update consumer and design documentation.
- [ ] Mark roadmap item 4.2.1 complete.
- [ ] Run `make check-fmt`, `make typecheck`, `make lint`, `make test`,
  `make markdownlint`, and `make nixie`.

## Surprises & discoveries

- Initial discovery: the repository already has a strong optional-dependency
  precedent in `src/falcon_correlate/httpx.py`. Reusing that import-safety
  pattern will reduce risk for Celery work.
- Initial discovery: the design document's sample `properties = {}` fallback
  is not automatically safe, because rebinding a local variable does not prove
  that Celery will publish the new mapping. The implementation turn must verify
  the actual signal contract before encoding that behaviour.

## Decision log

- Draft decision: implement the Celery publish feature in a dedicated
  `src/falcon_correlate/celery.py` module rather than mixing it into
  `middleware.py` or `httpx.py`. Rationale: this keeps the optional dependency
  isolated by feature and follows the existing package structure.
- Draft decision: add Celery as both an optional project extra and a dev
  dependency. Rationale: consumers should opt into the integration, while the
  repository still needs Celery installed locally to run unit and BDD tests.
- Draft decision: write the behavioural test against the real Celery publish
  path, not just direct handler invocation. Rationale: the user requirement is
  about task message behaviour, and a publish-path test is the smallest way to
  prove that the signal connection actually works.
- Open decision for implementation: whether the handler overwrites an explicit
  pre-existing `properties["correlation_id"]` value or preserves it. The plan
  assumes this will be settled in red tests first and then documented in the
  design appendix.

## Outcomes & retrospective

Pending implementation. A complete outcome for this task will include:

- a working `propagate_correlation_id_to_celery` implementation;
- automated proof that publishing a task injects the correlation ID when one
  exists in context;
- updated consumer documentation for the Celery integration path;
- an updated design appendix capturing the final decisions; and
- a green repository across format, type, lint, test, and Markdown validation
  gates.
