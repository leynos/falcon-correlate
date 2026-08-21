# Debugging Plan: optional-Celery subprocess timeout

**Generated**: 2026-08-21 20:43 CEST
**Issue ID**: full test gate
**Severity**: High
**Falsification sub-agent**: alchemist
**Planning agent boundary**: This document was prepared by the planning agent.
Falsification must be executed by the named sub-agent, not by the planning
agent.

## Problem statement

`make test` passed 445 tests and skipped 11, then exceeded the 120-second
timeout in the optional-Celery test module's child-pytest fixture. The expected
behaviour is for the isolated Celery-blocked child suite to finish within that
timeout. The Skylos change does not alter the affected helper or test module,
so the immediate risk is a concurrent test-environment interaction rather than
a demonstrated product regression.

## Context summary

| Aspect              | Details                                                       |
| ------------------- | ------------------------------------------------------------- |
| First observed      | 2026-08-21 during the full gate run                           |
| Reproduction rate   | One full, xdist-enabled run                                   |
| Affected components | Optional-Celery child-pytest test fixture                     |
| Recent changes      | Skylos lint gate and dead-code cleanup; no Celery-path change |

### Error artefacts

```plaintext
Failed: Timeout (>120.0s) from pytest-timeout.
src/falcon_correlate/unittests/optional_celery_dependency_helpers.py:180
subprocess.run(..., timeout=120)
445 passed, 11 skipped, 3 errors in 130.59s
```

### Information gaps

- The child pytest process did not emit a captured result before the parent
  timeout.
- The failure has not yet been repeated outside the xdist-enabled full suite.

______________________________________________________________________

## Hypotheses

### H1: concurrent xdist workers starve the nested child pytest process

**Claim**: The parent `make test` invocation's `-n auto` workers contend with
the optional-Celery fixture's child pytest process, causing the child to exceed
120 seconds without a product-code fault.

**Plausibility**: High — all unrelated tests passed, the timeout occurs while
waiting for a child process, and the affected test itself launches pytest.

**Prediction**: The optional-Celery module will complete within 120 seconds
when run directly without xdist.

#### H1 falsification plan

| Step | Action                                                                                    | Expected negative result                                    |
| ---- | ----------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| 1    | Run `uv run pytest -v src/falcon_correlate/unittests/test_optional_celery_dependency.py`. | A timeout or equivalent child-process failure falsifies H1. |

**Tooling**: The existing project virtual environment and pytest.

**Confidence on falsification**: High. A serial failure demonstrates the
timeout is independent of the parent xdist worker pool.

______________________________________________________________________

## Recommended execution order

1. **H1** — This is the smallest decisive experiment and makes no repository
   changes.

## Termination criteria

- **H1 falsified**: The focused serial test fails; revise the plan before any
  implementation change.
- **H1 not falsified**: The focused serial test passes; treat the full-gate
  failure as test-environment contention. The 2026-08-21 experiment passed all
  10 tests in 91.83 seconds, so `make test` now excludes the nested-pytest
  module and `make test-optional-celery` runs it serially.

## Notes for executing agent

Run exactly the one command in H1 from the repository root. Do not run full
repository gates, edit files, or change pytest configuration. Return only a
verdict of falsified, not-falsified, or inconclusive with the observed duration
and failure summary.
