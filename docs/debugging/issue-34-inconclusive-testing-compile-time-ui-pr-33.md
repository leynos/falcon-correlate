# Investigation: inconclusive Testing check on PR #33

- **Date**: 2026-10-12
- **Issue**: [#34](https://github.com/leynos/falcon-correlate/issues/34)
- **Pull request**: [#33](https://github.com/leynos/falcon-correlate/pull/33)
- **Head SHA**: `b33f1f16504dae1ec6984c5127c17e4e61cf18cf`

## Problem statement

Issue #34 reports that the external **Testing (Compile-Time / UI)** check on
pull request 33 returned no final result and was marked INCONCLUSIVE. This
record reruns the repository gates at the reported pull-request head and on the
`main` baseline, then separates those results from evidence about the external
review runner. It does not infer a cause for the external label from repository
test failures.

## Context summary

| Aspect                           | Details                                                    |
| -------------------------------- | ---------------------------------------------------------- |
| Pull-request head                | `b33f1f16504dae1ec6984c5127c17e4e61cf18cf`                 |
| Main baseline                    | `2e59c89458843ce6e384ef5cc0adeedb8f6e2cbc`                 |
| Operating system                 | Rocky Linux 10.2                                           |
| Ambient Python                   | CPython 3.12.14                                            |
| Project Python                   | CPython 3.14.7                                             |
| `uv`                             | 0.11.19                                                    |
| Historical project configuration | The Makefile and workflow files checked out at the PR head |

_Table 1: Revisions and environment used for the gate reruns._

The historical checkout was a separate worktree. Gate commands used the
historical Makefile there; its `test` recipe ran `uv run pytest -v -n auto`.
The focused optional-Celery command was:

```sh
uv run pytest -v src/falcon_correlate/unittests/test_optional_celery_dependency.py
```

## Verified repository results

### PR #33 head

Exit status determines each gate result: zero is PASSED; every non-zero status
is FAILED.

| Gate                           | Result          | Observed summary                                                        |
| ------------------------------ | --------------- | ----------------------------------------------------------------------- |
| `make check-fmt`               | FAILED (exit 2) | 14 files would be reformatted.                                          |
| `make typecheck`               | PASSED (exit 0) | All checks passed.                                                      |
| `make lint`                    | FAILED (exit 2) | Two `RUF100` unused-`noqa` findings in `celery.py` and `middleware.py`. |
| `make test`                    | FAILED (exit 2) | 358 passed, 11 skipped, 3 errors in 37.22 seconds.                      |
| Focused optional-Celery pytest | FAILED (exit 1) | 7 passed, 3 errors in 30.86 seconds.                                    |

_Table 2: Gate outcomes at the PR #33 head._

The three optional-Celery child-run tests reached pytest's 30-second test
timeout. The captured traceback ended in `selectors.poll`; it did not identify
which child phase was active. The PR-head helper passed a 30-second timeout to
its child subprocess. The `main` baseline used a 120-second child budget and a
270-second parent budget; those main-branch budgets were preserved during the
later helper hardening.

### `main` baseline

| Gate                              | Result          | Observed summary                                             |
| --------------------------------- | --------------- | ------------------------------------------------------------ |
| `make test-optional-celery` run 1 | PASSED (exit 0) | 10 passed in 4.01 seconds.                                   |
| `make test-optional-celery` run 2 | PASSED (exit 0) | 10 passed in 3.08 seconds.                                   |
| `make test-optional-celery` run 3 | PASSED (exit 0) | 10 passed in 2.99 seconds.                                   |
| `make typecheck`                  | PASSED (exit 0) | All checks passed.                                           |
| `make test`                       | FAILED (exit 2) | 1 failed, 580 passed, 11 skipped, 8 errors in 12.61 seconds. |

_Table 3: Gate outcomes on the `main` baseline._

The full-test failure output recorded a shared PyPy tool-provisioning collision
at `.lint-tools/pypy3.12-v8.0.0-linux64.temporary`, a checksum mismatch, and
`ModuleNotFoundError: No module named 'encodings'` during the Pylint toolchain
tests.

At this baseline, the optional-Celery helper used a 120-second child timeout
and a 270-second parent timeout. The three repeated optional-Celery runs
completed within that budget.

These main-branch results are separate from the optional-Celery timeouts at the
PR head.

## External review evidence

The GitHub check-runs endpoint for the PR head was available when queried. It
returned six completed runs: `test (3.12)`, `test (3.13)`, `test (3.14)`,
`lint`, skipped `Sourcery review`, and `CodeScene Code Health Review`. None was
named **Testing (Compile-Time / UI)**. The commit-status endpoint returned
overall success with a `CodeRabbit` context saying `Review completed` and no
target URL.

The supplied comment ID, `2871428897`, returned HTTP 404 from both the issue
comment and pull-request review-comment API endpoints. This means the original
comment and its associated records were **not verified** through those
endpoints; it does not establish that they never existed. The visible PR
discussion includes later status updates, but they do not identify the original
runner or provide its prompt, rubric, logs, or check-run link.

## Not verified

- The name of the external review tool that emitted the label.
- The prompt or rubric for **Testing (Compile-Time / UI)**.
- The original runner logs and a direct link to its check run.
- The cause of the external INCONCLUSIVE result.
- Whether the external check's result was persisted outside the available
  check-runs, status, and comment endpoints.

No evidence links the optional-Celery timeouts, the 120-second child budget, or
the 270-second parent budget to the external INCONCLUSIVE result. Those
repository observations do not establish how the external runner reached its
label.

## Implementation follow-up

The optional-Celery helpers now fail closed when collection exits non-zero or
collects zero items. A child timeout reports its phase, command, timeout, and
captured partial stdout and stderr. Collection failures report the phase, exit
code, stdout, and stderr. Regression tests cover non-zero collection, empty
collection, and timeout output. The 120-second child and 270-second parent
budgets remain unchanged. These diagnostics improve repository-test failures;
they do not claim to explain the external review label.

The tool-neutral review rule in [`AGENTS.md`](../../AGENTS.md) maps the label to
`make typecheck` and `make test`. PASSED requires exit status 0. Every other
outcome is FAILED, including timeout and inability to execute a command. A
command that cannot be run is reported as `FAILED (not executed)` with its
reason. INCONCLUSIVE is forbidden for this mapping.

The shared coverage action has no input for selecting the pytest-xdist
distribution strategy, so both coverage lanes set `pytest-workers` to an empty
string and run the suite serially. Direct test lanes use `--dist=loadgroup` for
fixtures that share provisioned tools. The pinned action's manifest lists the
worker input and its empty-string setting:
[generate-coverage action manifest][coverage-action].

[coverage-action]: https://github.com/leynos/shared-actions/blob/d5fded1107ee6822fdbf9539d81ff18ce6ce073a/.github/actions/generate-coverage/action.yml

After these implementation changes, each listed gate exited with status 0:
`make check-fmt`, `make typecheck`, `make lint`, `make test`,
`make test-optional-celery`, `make markdownlint`, and `make nixie` all passed.
The full suite reported 591 passed and 11 skipped; the optional-Celery lane
reported 13 passed and 3 snapshots passed. CodeRabbit completed with no
findings.

## References

- [Issue #34](https://github.com/leynos/falcon-correlate/issues/34).
- [PR #33](https://github.com/leynos/falcon-correlate/pull/33).
- [PR #33 test (3.12)](https://github.com/leynos/falcon-correlate/actions/runs/25831109766/job/75896015925).
- [PR #33 test (3.13)](https://github.com/leynos/falcon-correlate/actions/runs/25831109766/job/75896015921).
- [PR #33 test (3.14)](https://github.com/leynos/falcon-correlate/actions/runs/25831109766/job/75896015918).
- [PR #33 lint](https://github.com/leynos/falcon-correlate/actions/runs/25831109766/job/75896015917).
- [PR #33 review comment](https://github.com/leynos/falcon-correlate/pull/33#issuecomment-4430912502).
- [PR #33 later review status](https://github.com/leynos/falcon-correlate/pull/33#issuecomment-4463024239).
- [Issue #34 optional-Celery timeout investigation](debugging-plan-2026-08-21-optional-celery-subprocess-timeout.md).
- [Python `TimeoutExpired` documentation](https://docs.python.org/3.13/library/subprocess.html#subprocess.TimeoutExpired).
