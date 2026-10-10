# Architectural decision record (ADR) 001: three-tier linting with Ruff, Interrogate, and PyPy-backed Pylint

## Status

Accepted on 2026-05-15 and amended on 2026-06-21, 2026-07-31, 2026-09-25, and
2026-09-30. The current six-check `make lint` pipeline runs pinned Ruff,
Interrogate, classic Pylint on checksum-verified PyPy 8.0.0/Python 3.12, DF12
Pylint on CPython 3.14, Ambrleaks, and Skylos production dead-code detection.
See the
[2026-09-30 amendment](#amendment-2026-09-30-verified-pylint-on-pypy-312) for
the current toolchain.

## Date

2026-07-31.

## Context and Problem Statement

`falcon-correlate` already used Ruff for linting and formatting checks. The
project needed to import the stricter lint policy from `leynos/episodic`,
including a focused Pylint tier, and an explicit docstring coverage gate so new
public and internal package code cannot reduce coverage while still satisfying
style-only docstring checks. The original PyPy workaround has since been
removed; the current execution model is recorded in the latest amendment.

The decision needed to preserve a fast default lint path, keep lint behaviour
reproducible across local and CI environments, and avoid enabling an unbounded
Pylint rule set that would duplicate Ruff or force broad refactors unrelated to
the lint integration.

## Decision Drivers

- Keep `make lint` as the single local lint command.
- Run fast, broad lint checks before slower or deeper checks.
- Reuse the lint policy already established in `leynos/episodic`.
- Enforce 100 percent docstring coverage for the package.
- Pin the classic Pylint runtime and package versions so the PyPy-backed
  execution path is reproducible.
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

### Option C: Ruff followed by focused PyPy-backed Pylint

This preserves Ruff as the fast first tier and adds a deliberate Pylint
allow-list as the second tier. The initial implementation used a wrapper to
work around a PyPy/Astroid inspection failure; the 2026-09-30 amendment records
the tested vanilla-Pylint replacement.

### Option D: Ruff followed by Interrogate and focused PyPy-backed Pylint

This keeps Ruff as the fast first tier, adds Interrogate as an explicit
docstring coverage gate, and then runs the focused PyPy-backed Pylint tier.
Interrogate complements Ruff because Ruff validates docstring style and
presence rule-by-rule, while Interrogate reports package-level coverage and
fails the lint target below the configured threshold.

| Topic              | Ruff only           | Unrestricted Pylint     | Focused PyPy-backed Pylint                 | Ruff + Interrogate + focused Pylint   |
| ------------------ | ------------------- | ----------------------- | ------------------------------------------ | ------------------------------------- |
| Speed              | Fastest             | Slowest                 | Fast first tier, deeper second tier        | Fast style tier, explicit coverage    |
| Signal             | Good but incomplete | Noisy                   | Focused                                    | Focused plus coverage threshold       |
| Episodic alignment | Partial             | Partial                 | Full                                       | Full plus package coverage            |
| Reproducibility    | Good                | Depends on local Pylint | Pinned interpreter and `uv` tool execution | Pinned interpreter and `uv` execution |

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

- Classic Pylint must run without a monkey-patch under the verified PyPy 3.12
  runtime.
- The PyPy archive, Pylint, and Astroid must be pinned for reproducibility.
- `df12-python-lints` must be pinned to `v0.3.0` and run under CPython 3.14.
- `ambrleaks` must scan the repository's Syrupy snapshots.
- The lint workflow must keep Ruff first so common failures return quickly.
- The Makefile must expose variables for the Interrogate targets, PyPy runtime,
  Pylint toolchain, and Pylint targets.

## Decision Outcome / Proposed Direction

Choose option D. `make lint` runs Ruff, Interrogate, one-worker classic Pylint
on checksum-verified PyPy 8.0.0/Python 3.12, the separate df12 Pylint pass on
CPython 3.14, and `ambrleaks`. The classic and df12 passes cover
`src tests examples`; their isolated environments and fatal diagnostics are
described in the
[2026-09-30 amendment](#amendment-2026-09-30-verified-pylint-on-pypy-312).

Ruff owns the broad lint policy, import policy, docstring style, type-checking
import rules, security checks, and most complexity checks. Interrogate owns the
package docstring coverage threshold. Pylint owns the focused third tier for
logging, pattern matching, refactoring suggestions, resource handling, and
selected design limits. The df12 plug-in owns house-style structural checks,
suppression explanations, and snapshot-assertion guidance. `ambrleaks` owns
snapshot redaction checks.

## Known Risks and Limitations

- PyPy 8.0.0's Python 3.12 build is beta quality and this lint binary is
  currently provisioned only for Linux x86_64. The classic pass explicitly
  enables syntax and fatal analysis diagnostics so parse failures cannot pass
  unnoticed.
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

The original three-tier decision separated fast feedback, docstring coverage,
and deeper static analysis. Later amendments extended that decision; the current
`make lint` pipeline has six checks, documented in the 2026-09-30 amendment.
The single Makefile entry point keeps the contributor workflow simple while
making runtimes, package versions, isolated Pylint caches, and source targets
explicit for maintenance.

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
The dated addendum below records the lint sequence before the verified PyPy
runtime and separate DF12 pass were added. Its four-stage sequence is
historical; the current six checks are listed in the 2026-09-30 amendment.

## Historical addendum (2026-09-29): Skylos production dead-code check

At that point, the original Ruff, Interrogate, and PyPy-backed Pylint decision
had been extended with a blocking Skylos scan. Skylos scanned
`src/falcon_correlate`, excluded the in-package `unittests` directory, and used
the strict gate configuration in `pyproject.toml`. The standalone command was
pinned to Python 3.14 because Skylos parses source with its own runtime
Abstract Syntax Tree (AST); the pin prevents phantom findings when the project
uses newer supported Python syntax.

Framework lifecycle callbacks and required protocol parameters use precise,
typed entry-point rules with verified reasons. A named Skylos allow-list entry
is permitted only when an entry-point rule cannot model the runtime boundary,
and it must include the verified caller-specific reason.

## Amendment (2026-09-30): verified Pylint on PyPy 3.12

The classic pass uses vanilla Pylint 4.1.1 with Astroid 4.3.3 in an isolated
`uv tool run` environment on the official PyPy 8.0.0/Python 3.12 Linux x86_64
archive. PyPy identifies this build as beta quality. The Makefile downloads the
pinned archive into `.lint-tools`, checks its published SHA-256 digest, and
verifies the executable's implementation, Python version, PyPy version, and
installed Pylint/Astroid versions before analysis. Caller overrides pass
through the same identity checks. This leaves the project's `.venv` and
supported Python baseline unchanged.

Pylint 4.1.1 declares Astroid `>=4.3.2,<=4.4`, so Astroid 4.3.3 falls within
its supported range. See the
[Pylint 4.1.1 metadata](https://pypi.org/project/pylint/4.1.1/) and
[Astroid 4.3.3 release](https://pypi.org/project/astroid/4.3.3/). The separate
DF12 pass uses the same explicit Pylint/Astroid pins in its own isolated
environment on CPython 3.14, loads only `df12_python_lints`, and has a distinct
`PYLINTHOME`. `ambrleaks` remains a separate CPython 3.14 invocation. The
GitHub repository for `df12-python-lints` is owned by the df12 Productions
organization, which also owns `falcon-correlate`; the dependency is pinned to
release `v0.3.0`.

Both Pylint passes set the source `py-version` to 3.12; the host interpreter
does not redefine the library baseline. Each invocation uses one worker and
enables syntax and fatal analysis diagnostics after `--disable=all`. Regression
contracts exercise interpreter identity, PEP 695 AST nodes, actual PyPy live-
object inspection, invalid syntax, lint failure propagation, plugin isolation,
and preservation of `.venv`. `make lint` and the CI lint lane remain the
complete entry points.

The effective `make lint` order is:

1. Pinned Ruff checks.
2. Interrogate package docstring coverage.
3. Classic Pylint on checksum-verified PyPy 8.0.0/Python 3.12.
4. DF12 Pylint on CPython 3.14 with `df12-python-lints` v0.3.0.
5. Ambrleaks snapshot checks on CPython 3.14.
6. Skylos strict production dead-code detection on Python 3.14.

The classic and DF12 source sets are `src tests examples`. This checkout has no
separately versioned `scripts/` tree; if newer-language tooling is added, it
must receive equivalent built-in Pylint coverage in an explicit
host-appropriate pass rather than relying only on DF12 checks. The CI lint lane
and `make lint` remain the complete entry points.

The pinned artefact is listed on the
[official PyPy downloads page](https://downloads.python.org/pypy/) and its
digest is published in the
[PyPy checksums](https://www.pypy.org/checksums.html).
