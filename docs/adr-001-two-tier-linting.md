# Architectural decision record (ADR) 001: two-tier linting with Ruff and PyPy-backed Pylint

## Status

Accepted on 2026-05-15. The project uses Ruff as the first lint tier and a
focused Pylint pass, executed through `pylint-pypy-shim` on PyPy, as the second
lint tier.

## Date

2026-05-15.

## Context and Problem Statement

`falcon-correlate` already used Ruff for linting and formatting checks. The
project needed to import the stricter lint policy from `leynos/episodic`,
including the practice of running Pylint as a second lint tier through the
`pylint-pypy-shim` repository.

The decision needed to preserve a fast default lint path, keep lint behaviour
reproducible across local and CI environments, and avoid enabling an unbounded
Pylint rule set that would duplicate Ruff or force broad refactors unrelated to
the lint integration.

## Decision Drivers

- Keep `make lint` as the single local lint command.
- Run fast, broad lint checks before slower or deeper checks.
- Reuse the lint policy already established in `leynos/episodic`.
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

| Topic              | Ruff only           | Unrestricted Pylint     | Focused PyPy-backed Pylint          |
| ------------------ | ------------------- | ----------------------- | ----------------------------------- |
| Speed              | Fastest             | Slowest                 | Fast first tier, deeper second tier |
| Signal             | Good but incomplete | Noisy                   | Focused                             |
| Episodic alignment | Partial             | Partial                 | Full                                |
| Reproducibility    | Good                | Depends on local Pylint | Pinned shim and `uv` tool execution |

_Table 1: Comparison of linting options._

## Goals and Non-Goals

Goals:

- Provide fast local feedback by keeping Ruff as the first lint tier.
- Add deeper checks through a focused PyPy-backed Pylint tier.
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
- Linting must allow configurable targets so maintainers can scope checks when
  needed.

### Technical requirements

- Pylint must run through `pylint-pypy-shim` under PyPy.
- The shim package must be pinned to a known revision for reproducibility.
- The lint workflow must keep Ruff first so common failures return quickly.
- The Makefile must expose variables for the PyPy runtime, shim reference, and
  Pylint targets.

## Decision Outcome / Proposed Direction

Choose option C. `make lint` runs `uv run ruff check` first, then runs Pylint
through the pinned `pylint-pypy-shim` package with `PYLINT_TARGETS` defaulting
to `src tests`.

Ruff owns the broad lint policy, import policy, docstring style, type-checking
import rules, security checks, and most complexity checks. Pylint owns the
focused second tier for logging, pattern matching, refactoring suggestions,
resource handling, and selected design limits.

## Known Risks and Limitations

- PyPy may lag the project's target Python syntax. The Pylint configuration
  disables `syntax-error` so the second tier remains useful when this runtime
  boundary appears.
- The Pylint tier may be slower than Ruff. Running Ruff first keeps most
  high-volume feedback fast.
- Some existing module and test shapes need targeted suppressions. These
  suppressions should remain narrow and should not become a substitute for
  future refactoring.

## Architectural Rationale

The two-tier approach separates fast feedback from deeper static analysis. It
keeps the normal contributor workflow simple through `make lint`, while the
Makefile variables make the runtime, shim revision, and lint targets explicit
for maintenance.

The project treats lint configuration as architecture because it shapes public
API design, import boundaries, logging correctness, and module size pressure.
Recording the decision makes future changes to the lint stack reviewable rather
than incidental.
