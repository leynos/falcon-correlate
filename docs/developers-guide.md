# Developers' guide

This guide records day-to-day development practices for `falcon-correlate`. The
project keeps local and Continuous Integration (CI) checks behind Makefile
targets so contributors can run the same gates before opening or updating a
pull request.

## Linting architecture

The Python lint target uses a three-tier linting approach:

- **Tier 1: Ruff.** Ruff runs first through `uv run ruff check`. It is the
  fast linting gate and owns formatting-adjacent checks, import rules, common
  correctness rules, docstring rules, security checks, complexity thresholds,
  and Ruff's Pylint-compatible rule families.
- **Tier 2: Interrogate.** Interrogate runs second through
  `uv run interrogate --fail-under 100`. It enforces package-level docstring
  coverage after Ruff has validated docstring style.
- **Tier 3: Pylint through PyPy.** Pylint runs third through the
  `pylint-pypy-shim` wrapper. This tier focuses on rules that complement Ruff,
  especially logging format correctness, pattern matching safety, refactoring
  suggestions, resource-handling checks, and selected design limits.

Ruff must pass before Interrogate runs, and Interrogate must pass before Pylint
runs. This keeps the slow, deeper lint tier focused on code that has already
passed the high-volume checks and the package docstring coverage gate.

The decision to use this architecture is recorded in
[ADR-001: three-tier linting with Ruff, Interrogate, and PyPy-backed Pylint](adr-001-three-tier-linting.md).

## Internal module architecture

`middleware_config.py` owns validation and freezing of middleware
configuration. Its central export is `CorrelationIDConfig`, an immutable
dataclass that enforces the invariant that all configuration state is immutable
after `__post_init__`, including conversion of `trusted_sources` to a
`frozenset`. `middleware.py` imports this module to construct and expose
validated configuration, and `__init__.py` re-exports the public config class.

`middleware_utils.py` owns the request context-variable lifecycle, logging
integration, and UUID tooling shared by the middleware. It exports
`correlation_id_var` and `user_id_var` for request-scoped state,
`ContextualLogFilter` for logging enrichment, and the default UUID generator
and validator helpers used by middleware configuration.

`middleware.py` and `middleware_asgi.py` both build on
`_CorrelationIDMiddlewareBase`, which owns the shared request selection,
response-header echo, and cleanup logic. The base class uses the narrow
`_RequestLike` and `_ResponseLike` protocols, so the shared lifecycle code only
depends on the request and response methods that Falcon WSGI and ASGI both
provide. `_RequestLike` defines `remote_addr` as a read-only `str` property, so
both Falcon request classes satisfy the boundary without requiring mutation
support. `middleware.py` exposes the WSGI middleware hooks, while
`middleware_asgi.py` exposes the public ASGI class with `async`
`process_request` and `process_response` hooks that delegate to the shared base.

The middleware's request-scoped correlation ID context variable is typed as
`contextvars.ContextVar[str | None]`, matching the exported
`correlation_id_var`. That narrow typing keeps `ty` and Ruff's annotation
checks aligned with the runtime state without changing any public API shape.
The corresponding `ContextVar.reset()` calls cast the verified token back to
`Token[str | None]`, which keeps the middleware clear to the type checker while
preserving the runtime contract.

`process_response` in `middleware.py` is responsible for the response-header
echo and cleanup path. It copies `req.context.correlation_id` into the
configured response header only when `echo_header_in_response` is enabled, the
request has a middleware-owned `correlation_id_var` reset token, and the
request has a resolved correlation ID. This prevents `process_response` from
echoing a spoofed `req.context.correlation_id` that was set by other code after
Falcon short-circuited before this middleware's `process_request` ran. The
method always resets the request-scoped `correlation_id_var` token in a
`finally` block. If `resp.set_header()` fails, the middleware logs a warning,
performs cleanup, and re-raises the exception, so Falcon still sees the failure.

The architectural boundary is deliberately one-way: `middleware.py` imports
from both utility modules, while neither `middleware_config.py` nor
`middleware_utils.py` imports from `middleware.py`. This prevents circular
imports and keeps configuration and runtime helpers usable independently.

`asgi_middleware_helpers.py` lives under `falcon_correlate.unittests` as shared
ASGI middleware test infrastructure. It provides lightweight request and
response doubles (`_Request`, `_Response`, and `_HeaderFailingResponse`) and a
minimal `_Context` object that carries `correlation_id` plus an optional reset
token. Its `_process_request` and `_process_response` async wrappers invoke
`CorrelationIDMiddlewareASGI` hooks with those doubles.
`_HeaderFailingResponse` subclasses `_Response` and raises `RuntimeError` from
`set_header()`, enabling failure-path tests around response-header echo and
cleanup. This module is owned by the unit-test package and must not be imported
by production code.

## Property-based testing

Property-based tests live under `tests/property/` and use Hypothesis for input
generation and repeated execution. Keep this suite focused on behavioural
properties that benefit from broad input coverage rather than example-specific
cases.

Shared fixtures for the property suite live in `tests/property/conftest.py`. The
`isolated_context` fixture runs each generated example inside
`contextvars.copy_context().run()` so `ContextVar` state does not leak between
examples. Use it whenever a property test mutates request-scoped context.

Follow the existing pattern in `tests/property/test_header_injection.py`:

- generate inputs with Hypothesis strategies;
- use `@given` with a conservative `@settings` cap for stable runs;
- suppress `HealthCheck.function_scoped_fixture` when a fixture is required
  per example; and
- assert on the external behaviour of the property rather than the generated
  example itself.

## Tested documentation examples

Runnable documentation examples live under `examples/`. They are source files,
not Markdown-only snippets. The Pylint tier includes `examples` in
`PYLINT_TARGETS` so runnable documentation examples are covered by that tier.

The quickstart guide embeds snippets from `examples/quickstart/`. Each source
region is delimited with sentinel comments:

```python
# [quickstart:region-id]
app.add_route("/hello", HelloResource())

# [/quickstart:region-id]
```

The Markdown guide places an HTML marker immediately before the corresponding
Python fence:

````markdown
<!-- quickstart:region-id -->

```python
app.add_route("/hello", HelloResource())
```
````

`tests/docs/test_quickstart_doc_matches_examples.py` compares the Python
abstract syntax tree (AST) for every marked fence with its source region. This
allows harmless formatting and comment changes while failing on semantic drift.
The `syrupy>=5,<6` development dependency supplies the snapshot fixture used by
the quickstart logging-format test. Run `uv sync --group dev` before the test
to install that fixture.
When adding a guarded snippet, add both markers and run:

```bash
uv run pytest tests/docs/test_quickstart_doc_matches_examples.py -v
```

## Workflow pins and Dependabot

Dependabot owns the upgrade of GitHub Actions and reusable workflows,
including calls into `leynos/shared-actions`. Contract tests that assert a
caller's exact commit SHA create a lockstep dependency: every time Dependabot
opens a bump PR, the test fails until a human edits the pinned constant to
match. That defeats the purpose of automated dependency updates and turns a
routine bump into a manual chore.

Contract tests may still verify the *shape* of a reusable-workflow caller.
They must not verify the specific SHA value.

- Do assert the workflow references the correct reusable workflow path.
- Do assert the ref is pinned to a full 40-character commit SHA, not a
  mutable branch such as `main` or `rolling`.
- Do assert the expected `on:` triggers, least-privilege `permissions:`, and
  the inputs the caller relies on.
- Do not hard-code the current SHA value as an expected string. Match it with
  a pattern instead.
- Do not fail a test purely because Dependabot bumped the pinned SHA.

```python
import re

SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def test_uses_pinned_full_sha(caller_step):
    ref = caller_step["uses"].split("@")[-1]
    assert SHA_RE.match(ref), f"expected a 40-hex commit SHA, got {ref!r}"
```

If a workflow's behaviour genuinely depends on a feature only present from a
particular commit onwards, express that as a comment or a changelog note, not
as a test assertion on the SHA string.

## Roadmap notes

The three-tier linting work described in
[ADR-001: three-tier linting with Ruff, Interrogate, and PyPy-backed Pylint](adr-001-three-tier-linting.md)
is complete. Keep future linting changes aligned with that ADR unless a new
ADR supersedes it.

The tested quickstart example convention is described in
[ADR-002: tested documentation examples](adr-002-tested-documentation-examples.md).

## Running lint checks

Run the full lint gate with:

```bash
make lint
```

`make lint` executes these commands in order:

```bash
$(UV_ENV) $(UV) run ruff check
$(UV_ENV) $(UV) run interrogate --fail-under 100 $(INTERROGATE_TARGETS)
$(PYLINT) $(PYLINT_TARGETS)
```

The target should be run before committing changes that affect Python code,
tests, or lint configuration. When diagnosing failures, fix Ruff findings
first, then rerun `make lint` so the Pylint tier sees the post-Ruff state.

Use the standard log pattern when capturing lint output for review:

```bash
make lint 2>&1 | tee /tmp/lint-falcon-correlate-$(git branch --show-current).out
```

## Makefile variables

The lint target is configured by these Makefile variables:

| Variable               | Default                                                                                       | Purpose                                                        |
| ---------------------- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| `UV`                   | First `uv` on `PATH`, falling back to `$(HOME)/.local/bin/uv`                                 | Selects the `uv` launcher used by all Python tool commands.    |
| `UV_ENV`               | `UV_CACHE_DIR=.uv-cache UV_TOOL_DIR=.uv-tools`                                                | Keeps project-local `uv` cache and tool directories.           |
| `PYLINT_PYTHON`        | `pypy`                                                                                        | Selects the Python runtime used for the Pylint tool execution. |
| `PYLINT_TARGETS`       | `src tests examples`                                                                          | Defines the source trees checked by the Pylint tier.           |
| `PYLINT_PYPY_SHIM_REF` | `726d09f968b4d729ee4b29c71fc732e744854f3b`                                                    | Pins the `pylint-pypy-shim` repository revision.               |
| `PYLINT_PYPY_SHIM`     | `git+https://github.com/leynos/pylint-pypy-shim.git@$(PYLINT_PYPY_SHIM_REF)`                  | Identifies the shim package installed by `uv tool run`.        |
| `PYLINT`               | `$(UV_ENV) $(UV) tool run --python $(PYLINT_PYTHON) --from '$(PYLINT_PYPY_SHIM)' pylint-pypy` | Expands to the full PyPy-backed Pylint command.                |
| `INTERROGATE_TARGETS`  | `src/falcon_correlate`                                                                        | Defines the repo-root-relative tree checked by Interrogate.    |

Override variables at the command line for targeted investigation. For example:

```bash
make lint PYLINT_TARGETS=src/falcon_correlate/middleware.py
```

Do not change `PYLINT_PYPY_SHIM_REF` casually. Updating the shim changes the
lint execution environment and should be reviewed as a tooling change.

## Episodic lint policy

The lint policy is imported from `leynos/episodic` and adapted to this package.
The policy is:

- prefer Ruff for fast, broad, deterministic lint coverage;
- enable Ruff preview rules where they improve correctness or maintainability;
- ban deprecated `typing` generic aliases in favour of modern built-ins,
  `collections.abc`, `contextlib`, `collections`, or `re` equivalents;
- enforce consistent import conventions, including `typing as typ`,
  `collections.abc as cabc`, `datetime as dt`, and `unittest.mock as mock`;
- keep docstrings in NumPy style;
- use a focused Pylint allow-list rather than enabling every Pylint message;
- run Pylint under PyPy through the shim as a second tier after Ruff; and
- add narrow suppressions only when framework callbacks, tests, or existing
  module boundaries make a rule unsuitable for the current change.

New suppressions should explain why the rule is not useful at that location.
Broad suppressions should be treated as design debt and either documented in an
ADR, linked to a follow-up issue, or replaced with a refactor when the scope
allows it.

## `pyproject.toml` lint configuration

The lint configuration lives in `pyproject.toml`.

### Ruff

`[tool.ruff]` sets:

- `line-length = 88`;
- `preview = true`; and
- `target-version = "py312"`.

`[tool.ruff.lint]` selects the main Ruff rule families used by the project,
including Pyflakes (`F`), pycodestyle (`E`, `W`), import ordering (`I`),
pyupgrade (`UP`), comprehensions (`C4`), type-checking imports (`TC`), pathlib
usage (`PTH`), security (`S`), boolean traps (`FBT`), naming (`N`),
flake8-bugbear (`B`), Ruff-native rules (`RUF`), logging (`LOG`), pytest style (
`PT`), exceptions (`TRY`), docstrings (`D`), annotations (`ANN`), McCabe
complexity (`C90`), and selected Pylint-compatible rules (`PLR`, `PLE`, and
`PLW`).

The configuration extends the imported policy with explicit preview rules such
as `PLR6301`, `RUF053`, and `RUF066`. It ignores only the pydocstyle conflicts
`D203` and `D213`.

`[tool.ruff.lint.per-file-ignores]` carries targeted exceptions for tests and
workflow tests. These keep test assertions, framework callback shapes, and
workflow subprocess checks practical without weakening the production source
policy.

`[tool.ruff.lint.flake8-import-conventions]` bans selected `from` imports so
call sites make type and module provenance explicit. The alias table defines
the canonical aliases for common modules.

`[tool.ruff.lint.flake8-tidy-imports.banned-api]` rejects deprecated `typing`
aliases and points contributors to the preferred replacements.

`[tool.ruff.lint.pydocstyle]`, `[tool.ruff.lint.mccabe]`, and
`[tool.ruff.lint.pylint]` configure NumPy docstrings, a maximum McCabe
complexity of 8, and Ruff's Pylint-compatible argument, boolean expression, and
local-variable thresholds.

### Pylint

`[tool.pylint.main]` enables recursive directory checking and sets
`max-module-lines = 400`.

`[tool.pylint.design]` keeps Pylint's design thresholds aligned with the Ruff
policy where possible:

- `max-args = 4`;
- `max-locals = 20`;
- `max-statements = 70`; and
- `max-positional-arguments = 4`.

`[tool.pylint."messages control"]` disables all messages by default, disables
`syntax-error` for the managed PyPy runtime boundary, and then enables the
focused Pylint message set. This makes the second tier deliberate: it checks
specific classes of problems rather than duplicating Ruff wholesale.
