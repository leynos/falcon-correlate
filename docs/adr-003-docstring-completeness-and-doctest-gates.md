# Architectural decision record (ADR) 003: docstring completeness and doctest gates

## Status

Accepted on 2026-07-20. The project uses NumPy-style docstrings, inline
attribute docstrings for exported module-level values, repo-wide Ruff `DOC`
checks, and selective doctest execution for offline examples.

## Date

2026-07-20.

## Context and problem statement

[ADR-001](adr-001-three-tier-linting.md) established Ruff, Interrogate, and
PyPy-backed Pylint as the lint architecture. Interrogate enforces 100 percent
docstring coverage, while Ruff's pydocstyle (`D`) rules enforce presence and
style. Neither mechanism proves that `Parameters`, `Returns`, `Yields`, and
`Raises` sections agree with Python signatures. They also do not validate
module-level attribute docstrings or execute examples.

The public API therefore needed a documentation convention and deterministic
gates that detect signature drift, undocumented exported values, and stale
examples without making network services or optional dependencies part of the
documentation test environment.

## Decision drivers

- Keep public API documentation accurate as signatures evolve.
- Preserve NumPy docstring style across runtime and test modules.
- Document exported context variables and constants in a form compatible with
  future Sphinx `autodata` generation.
- Execute examples that can run deterministically without external services.
- Keep local and Continuous Integration (CI) validation behind Makefile
  targets.
- Avoid new runtime dependencies.

## Requirements

### Functional requirements

- Every Python object under `src/falcon_correlate` must have a docstring.
- Docstring sections must agree with callable signatures and raised
  exceptions.
- Every name exported from `falcon_correlate.__all__` must be documented.
- Exported module-level values must have inline attribute docstrings.
- Executable examples must run as part of the committed test gate.

### Technical requirements

- Docstrings must follow the NumPy convention configured in
  `pyproject.toml`.
- Ruff `DOC` rules must apply repo-wide under `src/falcon_correlate`.
- Ruff must remain pinned; this decision was implemented with Ruff `0.14.10`
  because `DOC` rules are preview rules.
- Doctests must use `--import-mode=importlib` and exclude package-local unit
  tests.
- Executable `>>>` examples must be offline, deterministic, and independent
  of optional dependencies.

## Options considered

### Option A: Coverage and style checks only

Interrogate and Ruff `D` would continue to enforce docstring presence and
style. This has the lowest maintenance cost, but parameter and exception
sections could drift from signatures, exported values could remain
undocumented, and examples could become stale.

### Option B: Execute every documented example

All examples would use doctest prompts. This maximizes executable coverage, but
examples involving Falcon applications, HTTPX, Celery, networks, or
asynchronous resources would make documentation tests slow and environment
dependent.

### Option C: Layered completeness checks and selective doctests

Ruff `DOC` checks signature correspondence, Interrogate checks coverage, an
Abstract Syntax Tree (AST) test checks inline attribute docstrings, and pytest
executes only offline `>>>` examples. Integration examples remain
non-executable literal blocks and are covered by ordinary unit or behavioural
tests.

| Topic                    | Coverage and style only | Execute every example | Layered selective approach   |
| ------------------------ | ----------------------- | --------------------- | ---------------------------- |
| Signature accuracy       | Not enforced            | Not enforced          | Ruff `DOC`                   |
| Exported value docs      | Not enforced            | Not enforced          | AST regression test          |
| Example freshness        | Not enforced            | Broadly enforced      | Enforced where deterministic |
| Environment independence | High                    | Low                   | High                         |

_Table 1: Comparison of docstring validation approaches._

## Decision outcome / proposed direction

Choose option C. Public and internal package docstrings use NumPy sections that
match their signatures. Exported module-level variables and constants use a
bare string literal immediately after assignment. The test suite parses the
defining module to ensure those attribute docstrings remain present.

`make lint` runs Ruff `DOC` and Interrogate at 100 percent coverage.
`make test` runs a dedicated doctest target before the ordinary suite. Only
examples that are deterministic and dependency-free use `>>>`; integration
examples use non-executable Python blocks and remain validated by their
corresponding unit, behavioural, or integration tests.

## Goals and non-goals

Goals:

- Keep public API documentation complete and mechanically verifiable.
- Make future generated API reference material reliable.
- Keep documentation checks reproducible locally and in CI.

Non-goals:

- Generate or publish the API reference; roadmap item 6.1.2 owns that work.
- Execute networked, Celery, HTTPX, or full Falcon application examples as
  doctests.
- Change runtime behaviour or the public API surface.

## Migration plan

No runtime or public API migration is required because this decision formalizes
the documentation validation gates introduced by this change. Contributors
must use `make lint` and `make test` to adopt and validate the gates.

## Outstanding decisions

No outstanding decisions remain.

## Known risks and limitations

- Ruff `DOC` rules are preview rules. The pinned Ruff version keeps results
  stable, and a Ruff upgrade must review any changed diagnostics.
- Interrogate measures coverage rather than quality. Ruff `DOC`, public export
  tests, and review remain necessary complements.
- Python does not expose attribute docstrings through runtime `__doc__`.
  Source-level AST checks verify placement instead.
- Non-executable integration examples can still drift. Their observable
  behaviour must remain covered by ordinary tests.

## Architectural rationale

The layered checks assign one clear responsibility to each tool: Interrogate
measures coverage, Ruff validates style and signature correspondence, the AST
test protects exported values, and pytest executes safe examples. This extends
the separation of concerns established by ADR-001 while keeping the canonical
developer entry points unchanged: `make lint` and `make test`.
