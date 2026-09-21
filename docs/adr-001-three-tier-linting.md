# Architectural decision record (ADR) 001: three-tier linting with Ruff, Interrogate, and vanilla Pylint

## Status

Accepted on 2026-05-15 and amended on 2026-07-31 and 2026-09-21. The project
uses Ruff as the first lint tier, Interrogate as the second lint tier, a
focused vanilla Pylint pass on the official PyPy 8.0.0 Python 3.12 build, the
`df12-python-lints` plug-in under CPython 3.14, and `ambrleaks` snapshot
scanning.

## Date

2026-09-21.

## Context and Problem Statement

`falcon-correlate` already used Ruff for linting and formatting checks. The
project needed to import the stricter lint policy from `leynos/episodic`,
including the practice of running Pylint as a later lint tier under PyPy. The
project also needs an explicit docstring coverage gate so new public and
internal package code cannot reduce docstring coverage while still satisfying
style-only docstring checks.

The decision needed to preserve a fast default lint path, keep lint behaviour
reproducible across local and CI environments, and avoid enabling an unbounded
Pylint rule set that would duplicate Ruff or force broad refactors unrelated to
the lint integration.

## Decision Drivers

- Keep `make lint` as the single local lint command.
- Run fast, broad lint checks before slower or deeper checks.
- Reuse the lint policy already established in `leynos/episodic`.
- Enforce 100 percent docstring coverage for the package.
- Pin the Pylint and Astroid releases and verify the PyPy runtime so the
  classic execution path is reproducible.
- Keep Pylint focused on rules that add value beyond Ruff.
- Run the tagged df12 Pylint plug-in and snapshot scanner under CPython 3.14.
- Allow narrow suppressions for framework callback signatures, tests, and
  legacy module boundaries.

## Options Considered

### Option A: Ruff only

This would keep linting simple and fast, but it would not import the full
episodic lint policy. It would also miss Pylint checks for logging format
correctness, selected pattern matching checks, and some refactoring guidance.

### Option B: Ruff followed by unrestricted Pylint

This would add Pylint coverage, but it would produce high overlap with Ruff and
generate noisy findings that are not relevant to this package's current lint
goals.

### Option C: Ruff followed by focused vanilla Pylint on PyPy

This preserves Ruff as the fast first tier and adds a deliberate Pylint
allow-list as the second tier. `uv tool run --isolated` runs vanilla Pylint
4.0.8 with Astroid 4.0.4 on the checksum-verified PyPy 8.0.0 Python 3.12 Linux
x86_64 build, with one worker and no monkey-patch or shim.

### Option D: Ruff followed by Interrogate and focused vanilla Pylint

This keeps Ruff as the fast first tier, adds Interrogate as an explicit
docstring coverage gate, and then runs the focused vanilla Pylint tier on PyPy.
Interrogate complements Ruff because Ruff validates docstring style and
presence rule-by-rule, while Interrogate reports package-level coverage and
fails the lint target below the configured threshold.

| Topic              | Ruff only           | Unrestricted Pylint     | Focused vanilla Pylint              | Ruff + Interrogate + focused Pylint |
| ------------------ | ------------------- | ----------------------- | ----------------------------------- | ----------------------------------- |
| Speed              | Fastest             | Slowest                 | Fast first tier, deeper second tier | Fast style tier, explicit coverage  |
| Signal             | Good but incomplete | Noisy                   | Focused                             | Focused plus coverage threshold     |
| Episodic alignment | Partial             | Partial                 | Full                                | Full plus package coverage          |
| Reproducibility    | Good                | Depends on local Pylint | Pinned runtime and tool releases    | Pinned runtimes and tool releases   |

_Table 1: Comparison of linting options._

## Goals and Non-Goals

Goals:

- Provide fast local feedback by keeping Ruff as the first lint tier.
- Add deeper checks through a focused vanilla Pylint tier on PyPy.
- Enforce 100 percent package docstring coverage through Interrogate.
- Preserve a maintainable contributor workflow through a single `make lint`
  command.
- Keep lint behaviour reproducible across local development and CI.

Non-goals:

- Define the project's formatting policy; Ruff format and existing Markdown
  tooling cover that separately.
- Replace type checking, unit tests, behavioural tests, or security review.
- Enable the full upstream Pylint rule set without project-specific curation.
- Redesign existing modules solely to satisfy new lint rules in this ADR.

## Requirements

### Functional requirements

- Linting must provide a fast first pass for common Python issues.
- Linting must enforce import policy, including import ordering and
  type-checking import placement.
- Linting must run targeted Pylint checks that add signal beyond Ruff.
- Linting must fail when package docstring coverage falls below 100 percent.
- Linting must allow configurable targets so maintainers can scope checks when
  needed.

### Technical requirements

- Pylint must run as the upstream package under the verified PyPy 8.0.0
  Python 3.12 Linux x86_64 build, with one worker.
- Pylint 4.0.8 and Astroid 4.0.4 must be pinned in the isolated tool
  environment.
- `df12-python-lints` must be pinned to `v0.3.0` and run under CPython 3.14.
- `ambrleaks` must scan the repository's Syrupy snapshots.
- The lint workflow must keep Ruff first so common failures return quickly.
- The Makefile must expose variables for the Interrogate targets, verified PyPy
  runtime, tool releases, isolated state, and Pylint targets.

## Decision Outcome / Proposed Direction

Choose option D and extend its focused Pylint stage. `make lint` runs
`uv run ruff check` first, then Interrogate with `--fail-under 100`, built-in
Pylint 4.0.8 with Astroid 4.0.4 on the checksum-verified PyPy 8.0.0 Python 3.12
build, all df12 Pylint messages under CPython 3.14, and finally `ambrleaks`,
with `PYLINT_TARGETS` defaulting to `src tests examples`.

The classic and df12 passes use isolated tool environments and separate Pylint
state directories. The classic interpreter is downloaded into `.lint-tools`
only on Linux x86_64 and is checked against its pinned SHA-256 digest. Both
Pylint passes use one worker. The df12 plug-in remains pinned to `v0.3.0` and
runs with CPython 3.14; this does not change the source language baseline,
which remains Python 3.12.

Ruff owns the broad lint policy, import policy, docstring style, type-checking
import rules, security checks, and most complexity checks. Interrogate owns the
package docstring coverage threshold. Pylint owns the focused third tier for
logging, pattern matching, refactoring suggestions, resource handling, and
selected design limits. The df12 plug-in owns house-style structural checks,
suppression explanations, and snapshot-assertion guidance. `ambrleaks` owns
snapshot redaction checks.

## Known Risks and Limitations

- PyPy 3.12 lint execution is beta quality and is currently supported only on
  Linux x86_64. The classic pass enables syntax and fatal analysis diagnostics
  so parse failures cannot be hidden by the runtime boundary.
- The Pylint tier may be slower than Ruff. Running Ruff first keeps most
  high-volume feedback fast.
- The df12 tools need a managed CPython 3.14 installation in addition to the
  project's supported interpreter and the PyPy runtime.
- Interrogate reports paths relative to its invocation directory. The Makefile
  runs it from the repository root and keeps `INTERROGATE_TARGETS`
  repo-root-relative for transparent overrides.
- Some existing module and test shapes need targeted suppressions. These
  suppressions should remain narrow and should not become a substitute for
  future refactoring.

## Architectural Rationale

The three-tier approach separates fast feedback, docstring coverage, and deeper
static analysis. It keeps the normal contributor workflow simple through
`make lint`, while the Makefile variables make the Interrogate target, runtime,
tool releases, isolated state, and lint targets explicit for maintenance.

The project treats lint configuration as architecture because it shapes public
API design, import boundaries, logging correctness, and module size pressure.
Recording the decision makes future changes to the lint stack reviewable rather
than incidental.

## Amendment — 2026-09-21

The former `pylint-pypy-shim` workaround has been removed. The classic pass now
invokes vanilla Pylint 4.0.8 with Astroid 4.0.4 in an isolated tool environment
on the official checksum-verified PyPy 8.0.0 Python 3.12 Linux x86_64 build. It
uses one worker and checks `src`, `tests`, and `examples`. The runtime
identity, Pylint version, and Astroid version are verified before the pass
runs. Its Pylint state is separate from the CPython 3.14 df12 state and from
the project's `.venv`.

The CPython 3.14 pass remains separate, loading only the pinned
`df12-python-lints` `v0.3.0` plug-in and running its `ambrleaks` companion. The
Pylint command now enables syntax and fatal analysis diagnostics, including
`syntax-error`, so a parse or tool failure cannot be reported as a successful
focused pass. Pylint's configured `py-version` remains `3.12` for both passes:
the execution interpreter and the source language baseline are separate
settings.

Astroid 4.3.1 remains deferred. The latest released Pylint 4.0.8 declares
Astroid `>=4.0.2,<=4.1.dev0`, which does not admit Astroid 4.3.1, while the
Pylint 4.1 documentation describes an unreleased compatibility target. The
project therefore keeps the released, mutually compatible Pylint 4.0.8 and
Astroid 4.0.4 pair until a supported released Pylint/Astroid combination is
available.
