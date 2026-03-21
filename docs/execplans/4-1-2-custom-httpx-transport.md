# Implement custom httpx transport (4.1.2)

This Execution Plan (ExecPlan) is a living document. The sections
`Constraints`, `Tolerances`, `Risks`, `Progress`, `Surprises &
Discoveries`, `Decision log`, and `Outcomes & retrospective` must be kept up
to date as work proceeds.

Status: DRAFT

Implementation must not begin until the user explicitly approves this plan.

## Purpose / big picture

Task 4.1.2 adds a second downstream HTTP propagation mechanism alongside the
existing wrapper functions in `src/falcon_correlate/httpx.py`. After this work,
library consumers will be able to configure `httpx.Client` and
`httpx.AsyncClient` with transport objects that automatically inject the
current correlation ID from `correlation_id_var` into outgoing requests.
Unlike the wrapper functions, this transport-based approach works even when the
calling code is built around shared client instances.

Success is observable when:

- `CorrelationIDTransport` subclasses `httpx.BaseTransport` and is available
  from `falcon_correlate.httpx`.
- `AsyncCorrelationIDTransport` subclasses `httpx.AsyncBaseTransport` and is
  available from `falcon_correlate.httpx`.
- Both transports inject the configured correlation header before delegating to
  the wrapped transport when `correlation_id_var.get()` returns a value.
- Neither transport adds the header when the context variable is unset or
  `None`.
- Behaviour is covered by unit tests (`pytest`) and behavioural tests
  (`pytest-bdd`).
- `docs/users-guide.md` explains when to use the transport approach and shows
  both sync and async client configuration.
- `docs/falcon-correlation-id-middleware-design.md` records the concrete
  implementation decisions taken during delivery.
- `docs/roadmap.md` marks item 4.1.2 complete.
- The repository passes `make check-fmt`, `make typecheck`, `make lint`, and
  `make test`.

## Context and orientation

The relevant feature code already lives in `src/falcon_correlate/httpx.py`.
That module currently provides:

- `request_with_correlation_id`
- `async_request_with_correlation_id`
- `_prepare_headers`

The current wrapper implementation already establishes three conventions that
the new transport work should follow unless validation proves they are wrong:

1. `httpx` remains an optional dependency, so imports must stay safe for users
   who do not install the `httpx` extra.
2. The default outbound header name comes from `DEFAULT_HEADER_NAME` in
   `src/falcon_correlate/middleware.py`.
3. Existing caller intent should be preserved where practical, rather than
   blindly overwriting provided headers.

Tests currently live in two places:

- Unit tests under `src/falcon_correlate/unittests/`
- Behavioural tests under `tests/bdd/`

Task 4.1.1 already created `test_httpx_wrapper.py` and
`httpx_propagation.feature`. Those files prove the wrapper path, but they are
already large enough that transport-specific scenarios should go into new,
dedicated files to keep the transport work easy to read and maintain.

The design document section for this task is
`docs/falcon-correlation-id-middleware-design.md` §3.5.1.3. The roadmap entry
is `docs/roadmap.md` item 4.1.2. The complexity guidance in
`docs/complexity-antipatterns-and-refactoring-strategies.md` argues against
growing large, lumpy functions and files, so the implementation should favour
small helpers and narrowly scoped tests.

## Constraints

- Follow test-driven development. Add or update tests first, confirm they fail,
  then implement the transports.
- Keep `httpx` as an optional dependency. The module
  `src/falcon_correlate/httpx.py` must remain importable without `httpx`
  installed.
- Reuse `DEFAULT_HEADER_NAME` instead of hardcoding `X-Correlation-ID`.
- Do not regress or rename the existing wrapper-function API from task 4.1.1.
- Keep the transport implementation additive. Existing callers using wrapper
  functions must continue to behave exactly as before.
- Keep the implementation aligned with the current package layout unless the
  work proves that `src/falcon_correlate/httpx.py` has become too crowded.
- Use British English in documentation.
- Wrap Markdown paragraphs and list items at 80 columns, and keep code blocks
  within 120 columns.
- Run repository quality gates before finishing the implementation turn:
  `make check-fmt`, `make typecheck`, `make lint`, and `make test`. Because
  this task edits Markdown files as well, also run `make markdownlint` and
  `make nixie`.

## Tolerances (exception triggers)

- Scope: if the work needs more than 10 files changed or more than 350 net
  lines, stop and ask whether the task should be split.
- API: if transport usability requires changing the existing wrapper-function
  signatures or their documented behaviour, stop and escalate.
- Dependency: if the implementation requires a new runtime dependency beyond
  the existing optional `httpx` extra, stop and escalate.
- Semantics: if `httpx` transport hooks require overwriting an explicitly
  provided outbound correlation header to function correctly, stop and confirm
  that behaviour before shipping it.
- Tooling: if `make test` or `make typecheck` fail for reasons unrelated to
  this task and cannot be resolved within two focused fix attempts, stop and
  document the failures.

## Risks

- Risk: the exact `httpx` transport method names differ by sync versus async
  base class. Mitigation: inspect the installed `httpx` version after running
  `make build`, then implement the exact methods required by that version
  rather than relying on memory.
- Risk: transport objects often need lifecycle delegation such as `close()` or
  `aclose()` in addition to request handling. Mitigation: inspect the base
  classes and wrapped transport contract, add delegation methods if needed, and
  cover them with unit tests if the contract is public.
- Risk: mutating the `httpx.Request.headers` object may accidentally override a
  caller-supplied header. Mitigation: define the intended precedence in tests
  before implementation.
- Risk: optional-dependency import patterns can confuse the type checker.
  Mitigation: keep runtime imports lazy and use `typing.TYPE_CHECKING` for
  annotations, following the existing wrapper module pattern.
- Risk: adding transport scenarios to the existing wrapper test files will make
  those files harder to maintain. Mitigation: use separate transport-focused
  unit and BDD files.

## Proposed implementation

### Milestone 1: verify the transport contract and write failing tests

Start by syncing the dev environment and confirming which `httpx` transport
methods exist in the installed version.

```plaintext
make build
python - <<'PY'
import inspect
import httpx
print(httpx.__version__)
print(inspect.signature(httpx.BaseTransport.handle_request))
print(inspect.signature(httpx.AsyncBaseTransport.handle_async_request))
PY
```

Then add transport-specific failing tests before changing feature code.

Create `src/falcon_correlate/unittests/test_httpx_transport.py` with focused
tests for:

- sync transport injects the header when a correlation ID exists
- async transport injects the header when a correlation ID exists
- sync transport leaves the request unchanged when the context is empty
- async transport leaves the request unchanged when the context is empty
- the wrapped transport is called exactly once with the same `httpx.Request`
  object after header enrichment
- transport lifecycle delegation (`close` / `aclose`) if required by the local
  `httpx` version

Create `tests/bdd/httpx_transport.feature` and
`tests/bdd/test_httpx_transport_steps.py` with scenarios a consumer can read as
behaviour:

- a configured sync client sends the correlation header automatically
- a configured async client sends the correlation header automatically
- no header is added when the correlation context is empty

Run the targeted tests and confirm they fail before implementation.

```plaintext
set -o pipefail
uv run pytest -v src/falcon_correlate/unittests/test_httpx_transport.py \
  tests/bdd/test_httpx_transport_steps.py \
  | tee /tmp/4-1-2-red-tests.log
```

The red-phase evidence should show failures due to missing transport classes or
missing behaviour, not unrelated import or environment failures.

### Milestone 2: implement the transport classes

Extend `src/falcon_correlate/httpx.py` rather than creating a second feature
module. This keeps all `httpx` propagation primitives in one place.

Implement:

- `CorrelationIDTransport`
- `AsyncCorrelationIDTransport`

The implementation should be intentionally thin. A small private helper should
own the request-mutation policy so that sync and async transports do not
duplicate header-injection logic. The helper should read
`correlation_id_var.get()`, check whether the header is already present, and
only inject when appropriate.

The constructor contract should be validated against the local `httpx` API
during implementation. The preferred shape is:

- accept a wrapped transport instance
- default to `DEFAULT_HEADER_NAME`
- delegate actual I/O to the wrapped transport

If the local `httpx` API makes the constructor shape materially different, note
that change in the decision log and update the design document accordingly.

If these classes are intended to be public consumer utilities, export them from
`src/falcon_correlate/__init__.py` and add them to `__all__`. If implementation
shows that only module-level access is appropriate, document that decision in
the design appendix and the users' guide.

After implementation, rerun the targeted test set:

```plaintext
set -o pipefail
uv run pytest -v src/falcon_correlate/unittests/test_httpx_transport.py \
  tests/bdd/test_httpx_transport_steps.py \
  | tee /tmp/4-1-2-green-tests.log
```

### Milestone 3: update consumer-facing documentation

Update `docs/users-guide.md` to describe:

- when to prefer wrapper functions versus custom transports
- how to configure `httpx.Client(transport=...)`
- how to configure `httpx.AsyncClient(transport=...)`
- what happens when no correlation ID is present in context

Update `docs/falcon-correlation-id-middleware-design.md` with a new appendix
entry for task 4.1.2. Record the decisions that materially affect maintainers,
especially:

- transport constructor shape
- whether existing request headers are preserved or overwritten
- whether the classes are re-exported from the package root
- whether close/aclose delegation was required

Update `docs/roadmap.md` by checking off 4.1.2 and its sub-items only after
the code and tests are complete.

### Milestone 4: run full validation

Run formatting, lint, type checking, tests, and Markdown validation with tee so
the logs survive truncation.

```plaintext
set -o pipefail
make check-fmt | tee /tmp/4-1-2-check-fmt.log
set -o pipefail
make typecheck | tee /tmp/4-1-2-typecheck.log
set -o pipefail
make lint | tee /tmp/4-1-2-lint.log
set -o pipefail
make test | tee /tmp/4-1-2-test.log
set -o pipefail
make markdownlint | tee /tmp/4-1-2-markdownlint.log
set -o pipefail
make nixie | tee /tmp/4-1-2-nixie.log
```

If any command fails, inspect the corresponding log file before making further
changes so the next fix is based on the real failure rather than guesswork.

## Progress

- [x] (2026-03-21) Reviewed roadmap item 4.1.2, the transport design section,
  the documentation style guide, the complexity guidance, and the existing
  4.1.1 ExecPlan.
- [x] (2026-03-21) Drafted this ExecPlan.
- [ ] Await user approval.
- [ ] Sync the development environment and confirm the local `httpx` transport
  API.
- [ ] Add failing unit tests for sync and async transport behaviour.
- [ ] Add failing BDD scenarios for sync and async client configuration.
- [ ] Implement `CorrelationIDTransport` and
  `AsyncCorrelationIDTransport`.
- [ ] Export the transport classes if they are part of the public API.
- [ ] Update `docs/users-guide.md`.
- [ ] Update `docs/falcon-correlation-id-middleware-design.md`.
- [ ] Mark roadmap item 4.1.2 complete in `docs/roadmap.md`.
- [ ] Run all required quality gates and inspect the tee logs.

## Surprises & discoveries

- `httpx` is declared in the project as an optional dependency and in the dev
  dependency group, but it is not installed in the current shell environment
  yet. Any implementation turn should begin with `make build` or
  `uv sync --group dev`.
- The existing wrapper test file (`test_httpx_wrapper.py`) and BDD feature
  already cover six scenarios. Keeping transport coverage in separate files
  will reduce the chance of creating a transport-plus-wrapper "bumpy road" test
  file.
- The roadmap wording says "Inject header in `handle_request` method", but the
  async base class almost certainly uses a different method name. The
  implementation must follow the real local `httpx` API rather than this
  shorthand roadmap wording.

## Decision log

- Decision: place the transport implementation in
  `src/falcon_correlate/httpx.py`. Rationale: the existing wrapper functions
  already established this module as the feature boundary for outbound `httpx`
  propagation.
- Decision: use dedicated transport test files rather than expanding the
  existing wrapper test files. Rationale: this keeps each test module focused
  and follows the repository's complexity guidance.
- Proposed decision to validate during implementation: preserve an explicitly
  supplied outbound correlation header instead of overwriting it. Rationale:
  this matches the existing `_prepare_headers` behaviour and avoids surprising
  callers. If `httpx` transport usage makes overwrite semantics necessary, this
  must be escalated because it changes the public contract.

## Outcomes & retrospective

This section is intentionally incomplete because implementation has not started.

When the task is complete, replace this paragraph with a concise summary of:

- what shipped
- which files changed
- how success was verified
- what design lessons should inform later roadmap items such as Celery
  propagation
