# Debugging Plan: optional-Celery subprocess timeout

**Generated**: 2026-08-21 20:43 CEST
**Issue ID**: full test gate
**Severity**: High
**Falsification sub-agent**: alchemist
**Planning agent boundary**: This document was prepared by the planning agent.
Falsification must be executed by the named sub-agent, not by the planning
agent.

## Problem statement

`make test-optional-celery` exceeded the 120-second timeout in the
optional-Celery test module's child-pytest fixture. The expected behaviour is
for the isolated Celery-blocked child suite to finish within that timeout. This
repeated during a serial target run, so the earlier xdist-contention hypothesis
is now falsified and the issue is in one of the child pytest operations or its
environment.

## Context summary

| Aspect              | Details                                                       |
| ------------------- | ------------------------------------------------------------- |
| First observed      | 2026-08-21 full gate run                                      |
| Reproduction rate   | 2/3: xdist and serial target runs                             |
| Affected components | Optional-Celery child-pytest fixture                          |
| Recent changes      | Skylos work; no Celery helper or test changes                 |

### Error artefacts

```plaintext
Failed: Timeout (>120.0s) from pytest-timeout.
src/falcon_correlate/unittests/optional_celery_dependency_helpers.py:180
subprocess.run(..., timeout=120)
7 passed, 3 fixture errors in 120.76s during `make test-optional-celery`
```

### Information gaps

- The parent fixture launches one normal child test run, then a separate
  `--collect-only` child run to calculate the expected skip count.
- Neither child result is captured when the parent times out, so the slow child
  operation remains unknown.

______________________________________________________________________

## Hypotheses

### H1: concurrent xdist workers starve the nested child pytest process

**Claim**: The parent `make test` invocation's `-n auto` workers contend with
the optional-Celery fixture's child pytest process, causing the child to exceed
120 seconds without a product-code fault.

**Plausibility**: Falsified — a 2026-08-21 serial `make test-optional-celery`
run produced the same 120-second timeout.

**Prediction**: The optional-Celery module would complete within 120 seconds
when run directly without xdist.

#### H1 falsification result

| Step | Action                                                               | Observed result                                        |
| ---- | -------------------------------------------------------------------- | ------------------------------------------------------ |
| 1    | Run `make test-optional-celery`.                                     | Timed out in 120.76 seconds (three fixture errors).    |

**Tooling**: The existing project virtual environment, pytest, and Make target.

**Confidence on falsification**: High. A serial failure demonstrates the
timeout is independent of the parent xdist worker pool.

______________________________________________________________________

### H2: the child collection pass exceeds the parent timeout

**Claim**: `_count_collected_test_items` runs `pytest --collect-only` over the
discovered Celery modules slowly enough to exceed 120 seconds in the blocked
Celery environment.

**Plausibility**: Falsified — on 2026-08-21 the isolated helper returned 36
collected items in 2.766 seconds, well below its 120-second timeout.

**Prediction**: Directly invoking the collection helper will exceed 120
seconds or raise `subprocess.TimeoutExpired`.

#### H2 falsification result

| Step | Action | Observed result |
| ---- | ------ | --------------- |
| 1 | Run a temporary-directory Python snippet that creates the import blocker, discovers Celery paths, and calls `_count_collected_test_items`. | Returned 36 items in 2.766 seconds. |

**Tooling**: `uv run python`, the existing helper functions, and a temporary
directory only.

**Confidence on falsification**: High. The helper executes exactly the
collection child operation that is otherwise hidden by the shared fixture.

______________________________________________________________________

### H3: the normal blocked-Celery child test run exceeds the parent timeout

**Claim**: The normal `pytest -q` child operation in
`_run_celery_tests_with_celery_blocked` is the operation that exceeds 120
seconds, independently of the collection pass.

**Plausibility**: Falsified — on 2026-08-21 the isolated helper completed in
about 28.3 seconds, well below its 120-second timeout.

**Prediction**: If H2 is falsified, a direct invocation of the normal child
operation will exceed 120 seconds or raise `subprocess.TimeoutExpired`.

#### H3 falsification result

| Step | Action | Observed result |
| ---- | ------ | --------------- |
| 1 | Run a temporary-directory Python snippet that creates the import blocker and sentinel, discovers Celery paths, and calls `_run_celery_tests_with_celery_blocked`. | Completed in about 28.3 seconds. |

**Tooling**: `uv run python`, the existing helper functions, and a temporary
directory only.

**Confidence on falsification**: Medium. The isolated operation completed, but
the execution harness did not retain the inner child result for inspection.

______________________________________________________________________

## Recommended execution order

1. Rerun `make test-optional-celery` after a change that affects the failed
   gate. Both deterministic child operations have been falsified, so changing
   the timeout would conceal an unreproduced transient condition.

## Termination criteria

- **Root cause identified**: A child operation reproduces the timeout under a
  dedicated falsification experiment.
- **Escalation trigger**: The rerun fails while both isolated child operations
  remain falsified. Revise hypotheses to examine transient process or resource
  effects before changing code.

## Notes for executing agent

Do not change the child-process timeout without a reproducible child-operation
failure. The documented evidence currently supports a transient condition, not
a timeout-configuration change.
