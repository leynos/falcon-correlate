# Architectural decision record (ADR) 001: three-tier linting with Ruff, Interrogate, and PyPy-backed Pylint

## Status

Accepted on 2026-05-15 and amended on 2026-06-21 and on 2026-09-25. The project
uses Ruff as the first lint tier, Interrogate as the second lint tier, and a
focused Pylint pass, executed directly under a pinned PyPy interpreter, as the
third lint tier. See
[Amendment (2026-09-25): plain Pylint on PyPy 3.12](#amendment-2026-09-25-plain-pylint-on-pypy-312)
for the current execution mechanism.

## Date

2026-06-21.

## Context and Problem Statement

`falcon-correlate` already used Ruff for linting and formatting checks. The
project needed to import the stricter lint policy from `leynos/episodic`,
including the practice of running Pylint as a later lint tier through the
`pylint-pypy-shim` repository. The project also needs an explicit docstring
coverage gate so new public and internal package code cannot reduce docstring
coverage while still satisfying style-only docstring checks.

The decision needed to preserve a fast default lint path, keep lint behaviour
reproducible across local and CI environments, and avoid enabling an unbounded
Pylint rule set that would duplicate Ruff or force broad refactors unrelated to
the lint integration.

## Decision Drivers

- Keep `make lint` as the single local lint command.
- Run fast, broad lint checks before slower or deeper checks.
- Reuse the lint policy already established in `leynos/episodic`.
- Enforce 100 percent docstring coverage for the package.
- Pin the shim revision so the PyPy-backed Pylint execution path is
  reproducible.
- Keep Pylint focused on rules that add value beyond Ruff.
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

### Option C: Ruff followed by focused PyPy-backed Pylint

This preserves Ruff as the fast first tier and adds a deliberate Pylint
allow-list as the second tier. `uv tool run --python pypy` installs and runs
the pinned `pylint-pypy-shim`, keeping the execution model aligned with
episodic.

### Option D: Ruff followed by Interrogate and focused PyPy-backed Pylint

This keeps Ruff as the fast first tier, adds Interrogate as an explicit
docstring coverage gate, and then runs the focused PyPy-backed Pylint tier.
Interrogate complements Ruff because Ruff validates docstring style and
presence rule-by-rule, while Interrogate reports package-level coverage and
fails the lint target below the configured threshold.

| Topic              | Ruff only           | Unrestricted Pylint     | Focused PyPy-backed Pylint          | Ruff + Interrogate + focused Pylint |
| ------------------ | ------------------- | ----------------------- | ----------------------------------- | ----------------------------------- |
| Speed              | Fastest             | Slowest                 | Fast first tier, deeper second tier | Fast style tier, explicit coverage  |
| Signal             | Good but incomplete | Noisy                   | Focused                             | Focused plus coverage threshold     |
| Episodic alignment | Partial             | Partial                 | Full                                | Full plus package coverage          |
| Reproducibility    | Good                | Depends on local Pylint | Pinned shim and `uv` tool execution | Pinned shim and `uv` execution      |

_Table 1: Comparison of linting options._

## Goals and Non-Goals

Goals:

- Provide fast local feedback by keeping Ruff as the first lint tier.
- Add deeper checks through a focused PyPy-backed Pylint tier.
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

- Pylint must run through `pylint-pypy-shim` under PyPy.
- The shim package must be pinned to a known revision for reproducibility.
- The lint workflow must keep Ruff first so common failures return quickly.
- The Makefile must expose variables for the Interrogate targets, PyPy runtime,
  shim reference, and Pylint targets.

## Decision Outcome / Proposed Direction

Choose option D. `make lint` runs `uv run ruff check` first, then runs
Interrogate with `--fail-under 100`, then runs Pylint under the pinned
`pypy@3.12` interpreter with `PYLINT_TARGETS` defaulting to `src tests`. See the
[2026-09-25 amendment](#amendment-2026-09-25-plain-pylint-on-pypy-312) for the
current execution mechanism.

Ruff owns the broad lint policy, import policy, docstring style, type-checking
import rules, security checks, and most complexity checks. Interrogate owns the
package docstring coverage threshold. Pylint owns the focused third tier for
logging, pattern matching, refactoring suggestions, resource handling, and
selected design limits.

## Known Risks and Limitations

- PyPy may lag the project's target Python syntax. This was the original
  rationale for disabling `syntax-error` in the Pylint configuration; the
  [2026-09-25 amendment](#amendment-2026-09-25-plain-pylint-on-pypy-312)
  records why that disable was removed.
- The Pylint tier may be slower than Ruff. Running Ruff first keeps most
  high-volume feedback fast.
- Interrogate reports paths relative to its invocation directory. The Makefile
  runs it from the repository root and keeps `INTERROGATE_TARGETS`
  repo-root-relative for transparent overrides.
- Some existing module and test shapes need targeted suppressions. These
  suppressions should remain narrow and should not become a substitute for
  future refactoring.

## Architectural Rationale

The three-tier approach separates fast feedback, docstring coverage, and deeper
static analysis. It keeps the normal contributor workflow simple through
`make lint`, while the Makefile variables make the Interrogate target, Pylint
runtime, Pylint version, and lint targets explicit for maintenance.

The project treats lint configuration as architecture because it shapes public
API design, import boundaries, logging correctness, and module size pressure.
Recording the decision makes future changes to the lint stack reviewable rather
than incidental.

## Amendment (2026-09-25): plain Pylint on PyPy 3.12

The Makefile no longer installs Pylint through the `pylint-pypy-shim` wrapper.
It instead runs Pylint directly under the `pypy@3.12` interpreter, pinned via
`PYLINT_PYTHON ?= pypy@3.12`, and a pinned Pylint version,
`PYLINT_VERSION ?= 4.0.9`, both installed on demand by
`uv tool run --managed-python --python $(PYLINT_PYTHON)` with
`--from 'pylint==$(PYLINT_VERSION)' pylint`. The `PYLINT_PYPY_SHIM_REF` and
`PYLINT_PYPY_SHIM` variables are gone.

PyPy 8 implements Python 3.12, and uv 0.12.19 (2026-09-25) ships it as a
managed interpreter, so Pylint runs on it without the shim's object-build
patch. The interpreter is pinned to `pypy@3.12` rather than bare `pypy` so a
new PyPy release cannot change the parsed grammar without a commit.

The Pylint configuration no longer disables `syntax-error`. While that message
was disabled, any module the PyPy runtime could not parse produced no messages
at all, so the lint passed without linting it. In this repository four modules
were skipped that way under PyPy 3.11; PyPy 3.12 parses all of them, and they
lint clean. A parse failure now fails the lint.
