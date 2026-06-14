# Developers' guide

This guide records day-to-day development practices for `falcon-correlate`. The
project keeps local and Continuous Integration (CI) checks behind Makefile
targets so contributors can run the same gates before opening or updating a
pull request.

## Linting architecture

The Python lint target uses a two-tier linting approach:

- **Tier 1: Ruff.** Ruff runs first through `uv run ruff check`. It is the
  fast linting gate and owns formatting-adjacent checks, import rules, common
  correctness rules, docstring rules, security checks, complexity thresholds,
  and Ruff's Pylint-compatible rule families.
- **Tier 2: Pylint through PyPy.** Pylint runs second through the
  `pylint-pypy-shim` wrapper. This tier focuses on rules that complement Ruff,
  especially logging format correctness, pattern matching safety, refactoring
  suggestions, resource-handling checks, and selected design limits.

Ruff must pass before Pylint runs. This keeps the slow, deeper lint tier
focused on code that has already passed the high-volume checks.

The decision to use this architecture is recorded in
[ADR-001: two-tier linting with Ruff and PyPy-backed Pylint](adr-001-two-tier-linting.md).

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
provide. `middleware.py` exposes the WSGI middleware hooks, while
`middleware_asgi.py` exposes the public ASGI class with `async`
`process_request` and `process_response` hooks that delegate to the shared base.

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
`CorrelationIDMiddlewareASGI` hooks with those doubles. `_HeaderFailingResponse`
subclasses `_Response` and raises `RuntimeError` from `set_header()`, enabling
failure-path tests around response-header echo and cleanup. This module is
owned by the unit-test package and must not be imported by production code.

## Property-based testing

Property-based tests live under `tests/property/` and use Hypothesis for input
generation and repeated execution. Keep this suite focused on behavioural
properties that benefit from broad input coverage rather than example-specific
cases.

Shared fixtures for the property suite live in `tests/property/conftest.py`.
The `isolated_context` fixture runs each generated example inside
`contextvars.copy_context().run()` so `ContextVar` state does not leak between
examples. Use it whenever a property test mutates request-scoped context.

Follow the existing pattern in `tests/property/test_header_injection.py`:

- generate inputs with Hypothesis strategies;
- use `@given` with a conservative `@settings` cap for stable runs;
- suppress `HealthCheck.function_scoped_fixture` when a fixture is required
  per example; and
- assert on the external behaviour of the property rather than the generated
  example itself.

## Roadmap notes

The two-tier linting work described in
[ADR-001: two-tier linting with Ruff and PyPy-backed Pylint](adr-001-two-tier-linting.md)
 is complete. Keep future linting changes aligned with that ADR unless a new
ADR supersedes it.

## Running lint checks

Run the full lint gate with:

```bash
make lint
```

`make lint` executes these commands in order:

```bash
$(UV_ENV) $(UV) run ruff check
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
| `PYLINT_TARGETS`       | `src tests`                                                                                   | Defines the source trees checked by the Pylint tier.           |
| `PYLINT_PYPY_SHIM_REF` | `726d09f968b4d729ee4b29c71fc732e744854f3b`                                                    | Pins the `pylint-pypy-shim` repository revision.               |
| `PYLINT_PYPY_SHIM`     | `git+https://github.com/leynos/pylint-pypy-shim.git@$(PYLINT_PYPY_SHIM_REF)`                  | Identifies the shim package installed by `uv tool run`.        |
| `PYLINT`               | `$(UV_ENV) $(UV) tool run --python $(PYLINT_PYTHON) --from '$(PYLINT_PYPY_SHIM)' pylint-pypy` | Expands to the full PyPy-backed Pylint command.                |

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
