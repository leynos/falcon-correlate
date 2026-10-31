# Investigation: Celery backend mutation survivors

- **Date**: 2026-10-31
- **Issue**: [#277](https://github.com/leynos/falcon-correlate/issues/277)
- **Branch**: `issue-277-investigate-celery-backend-mutation-survivors`
- **Base revision**: `f0d96e2c61f1069d0f7b09b8bb8a4d1d63a8b74f`
- **Historical mutation run**: [40876764226][run]
- **Historical artifact**: [12898890551][artifact]

## Problem statement

The mutation workflow for `main` at `8fe6e33aa4b2681574ec6dd593e8bb794f3d177e`
reported 30 surviving mutants in three result-backend helpers in
`src/falcon_correlate/celery.py`:

- `_app_backend_uses_rpc`, which classifies a backend URI as RPC or non-RPC;
- `_cache_app_backend_rpc_verdict`, which caches only definite verdicts;
- `_current_result_backend_uses_rpc`, the active-app fallback.

Those helpers decide whether a publish may replace Celery's task ID with the
request correlation ID. An RPC or unknown verdict **must** preserve the task
ID; only a definite non-RPC verdict may replace it. A survivor in this code is
therefore a potential contract gap, not merely a style concern.

This record reproduces the survivors at the reported revision, identifies
whether each one is a test gap or an equivalent mutant, and records the
evidence from the rerun.

## Context summary

| Aspect                  | Details                                                     |
| ----------------------- | ----------------------------------------------------------- |
| Historical workflow run | [40876764226][run]                                          |
| Historical artifact     | [12898890551][artifact]                                     |
| Historical revision     | `8fe6e33aa4b2681574ec6dd593e8bb794f3d177e`                  |
| Mutmut version          | 3.6.0                                                       |
| Historical counts       | 210 killed, 40 survived, 587 not checked                    |
| Scoped survivors        | 30, across the three helpers above                          |
| Local rerun revision    | `f0d96e2c61f1069d0f7b09b8bb8a4d1d63a8b74f` plus this change |
| Local rerun result      | 26 killed, 4 justified equivalents, 0 unchecked in scope    |

_Table 1: Revisions, tooling, and scoped counts._

## Recorded evidence

The historical artifact and workflow logs show Celery installed in the mutation
environment. The Celery-dependent tests executed rather than skipping: the
mutants in `_app_backend_uses_rpc` that another test did cover were reported
killed, and the recorded durations were non-zero. The "Celery was missing, so
the tests were skipped" hypothesis is therefore rejected.

The historical run did not identify which assertion should have noticed each
survivor. The scoped rerun below does.

## Sandbox execution checks

Every manual reproduction must run with the mutmut sandbox as the working
directory. Running the tests from the repository root makes pytest prepend the
repository `src` directory to `sys.path`, so the **unmutated** production
module is imported even when `MUTANT_UNDER_TEST` is set. An earlier attempt
used that arrangement and appeared to prove that equivalent mutants were
killed; that result was invalid.

The trustworthy checks were:

```sh
uv run --with mutmut==3.6.0 mutmut run <30 mutant names>
```

and, for one mutant at a time, a harness that changes into `mutants/` before
calling `pytest.main` with mutmut's own arguments.

The unmodified sandbox passed the three focused Celery test modules:

```text
32 passed in 0.48s
```

No test was skipped, which confirms that Celery was importable inside the
sandbox. The focused assertions also pass in the repository checkout before
mutation is applied.

## Findings

### Test-isolation defect found during reproduction

The first clean-test run in the sandbox failed: a fallback test observed an RPC
verdict left behind by another test. The new publisher tests constructed
`Celery` applications without `set_as_current=False`, so the last application
became Celery's process-global current app and leaked into later tests. The
defect was invisible in the default alphabetical order but appeared under
mutmut's duration-sorted order.

All publisher test applications now pass `set_as_current=False`. The combined
modules pass in one session, and the sandbox clean test no longer fails.

### Assertion strengthened for traceback retention

`logging` stores the literal value passed as `exc_info` on the record in this
Python version. A mutation that changed `exc_info=True` to `exc_info=False`
therefore produced a record whose `exc_info` attribute was `False`, which
`is not None` accepted. The assertion now requires the captured traceback tuple
itself, so both the `None` and `False` mutations are killed.

## Mutant dispositions

Each mutation below was reproduced with `mutmut show <name>` at the historical
revision and re-run locally against the focused tests. `Killed` means the
selected tests fail under the mutant. `Equivalent` means the mutation cannot
change observable behaviour.

| Mutant                                       | Mutation                                    | Disposition | Witness test                                                      |
| -------------------------------------------- | ------------------------------------------- | ----------- | ----------------------------------------------------------------- |
| `app_backend_uses_rpc__mutmut_16`            | Remove `None` default from `getattr`        | Killed      | `test_backend_without_as_uri_is_a_non_rpc_verdict`                |
| `app_backend_uses_rpc__mutmut_21`            | `return True` when `as_uri` is not callable | Killed      | `test_backend_with_non_callable_as_uri_is_a_non_rpc_verdict`      |
| `app_backend_uses_rpc__mutmut_27`            | Wrap diagnostic prefix in `XX`              | Killed      | `test_backend_uri_failure_is_unknown_and_logged`                  |
| `app_backend_uses_rpc__mutmut_30`            | Replace `+=` with `=` for task context      | Killed      | `test_backend_uri_failure_with_task_name_logs_publishing_context` |
| `app_backend_uses_rpc__mutmut_31`            | Replace `+=` with `-=` for task context     | Killed      | `test_backend_uri_failure_with_task_name_logs_publishing_context` |
| `app_backend_uses_rpc__mutmut_34`            | `exc_info=None`                             | Killed      | `test_backend_uri_failure_is_unknown_and_logged`                  |
| `app_backend_uses_rpc__mutmut_35`            | Pass `message` instead of `"%s"` format     | Killed      | `test_backend_uri_failure_is_unknown_and_logged`                  |
| `app_backend_uses_rpc__mutmut_37`            | Drop `exc_info` keyword                     | Killed      | `test_backend_uri_failure_is_unknown_and_logged`                  |
| `app_backend_uses_rpc__mutmut_38`            | Wrap diagnostic format string in `XX`       | Killed      | `test_backend_uri_failure_is_unknown_and_logged`                  |
| `app_backend_uses_rpc__mutmut_39`            | Lower-case `ID` in the diagnostic           | Killed      | `test_backend_uri_failure_is_unknown_and_logged`                  |
| `app_backend_uses_rpc__mutmut_41`            | `exc_info=False`                            | Killed      | `test_backend_uri_failure_is_unknown_and_logged`                  |
| `cache_app_backend_rpc_verdict__mutmut_6`    | Forward `task_name=None`                    | Killed      | `test_cache_forwards_task_name_and_retries_unknown_verdict`       |
| `cache_app_backend_rpc_verdict__mutmut_8`    | Drop `task_name` argument                   | Killed      | `test_cache_forwards_task_name_and_retries_unknown_verdict`       |
| `current_result_backend_uses_rpc__mutmut_1`  | Replace imported module with `None`         | Killed      | `test_current_result_backend_uses_rpc_for_rpc_current_app`        |
| `current_result_backend_uses_rpc__mutmut_3`  | Import `"XXceleryXX"`                       | Killed      | `test_current_result_backend_uses_rpc_for_rpc_current_app`        |
| `current_result_backend_uses_rpc__mutmut_4`  | Import `"CELERY"`                           | Killed      | `test_current_result_backend_uses_rpc_for_rpc_current_app`        |
| `current_result_backend_uses_rpc__mutmut_5`  | Return `True` on import failure             | Killed      | `test_current_result_backend_uses_rpc_when_celery_is_unavailable` |
| `current_result_backend_uses_rpc__mutmut_6`  | Replace `current_app` lookup with `None`    | Killed      | `test_current_result_backend_uses_rpc_for_rpc_current_app`        |
| `current_result_backend_uses_rpc__mutmut_7`  | Look up `current_app` on `None`             | Killed      | `test_current_result_backend_uses_rpc_for_rpc_current_app`        |
| `current_result_backend_uses_rpc__mutmut_11` | Remove `None` default from `getattr`        | Killed      | `test_current_result_backend_uses_rpc_without_current_app`        |
| `current_result_backend_uses_rpc__mutmut_12` | Look up `"XXcurrent_appXX"`                 | Killed      | `test_current_result_backend_uses_rpc_for_rpc_current_app`        |
| `current_result_backend_uses_rpc__mutmut_13` | Look up `"CURRENT_APP"`                     | Killed      | `test_current_result_backend_uses_rpc_for_rpc_current_app`        |
| `current_result_backend_uses_rpc__mutmut_14` | Invert the `current_app is None` guard      | Killed      | `test_current_result_backend_uses_rpc_for_rpc_current_app`        |
| `current_result_backend_uses_rpc__mutmut_15` | Return `True` when `current_app` is `None`  | Killed      | `test_current_result_backend_uses_rpc_with_none_current_app`      |
| `current_result_backend_uses_rpc__mutmut_16` | Pass `None` to the backend helper           | Killed      | `test_current_result_backend_uses_rpc_for_rpc_current_app`        |
| `current_result_backend_uses_rpc__mutmut_17` | `typ.cast(None, current_app)`               | Equivalent  | `typ.cast` returns its second argument unchanged at runtime       |
| `current_result_backend_uses_rpc__mutmut_18` | `typ.cast(..., None)`                       | Killed      | `test_current_result_backend_uses_rpc_for_rpc_current_app`        |
| `current_result_backend_uses_rpc__mutmut_21` | Change cast type string to `XX...XX`        | Equivalent  | Cast type strings are not inspected at runtime                    |
| `current_result_backend_uses_rpc__mutmut_22` | Lower-case the cast type string             | Equivalent  | Cast type strings are not inspected at runtime                    |
| `current_result_backend_uses_rpc__mutmut_23` | Upper-case the cast type string             | Equivalent  | Cast type strings are not inspected at runtime                    |

_Table 2: Disposition of the 30 scoped survivors._

No production-code suppression was added. The four remaining survivors are true
equivalent mutants, so a suppression would hide a future change to the cast
argument without improving coverage.

## Verification rerun

The 30 names were passed to one scoped `mutmut run` against a freshly
regenerated sandbox, after the focused tests were split across three modules.
The recorded statuses are 26 killed and 4 survived; the four survivors are the
equivalent cast mutants listed above. Every killed mutant has at least one
focused assertion that fails without the production change and passes when the
mutant is not active.

The focused tests are in:

- `src/falcon_correlate/unittests/test_celery_app_resolution.py`;
- `src/falcon_correlate/unittests/test_celery_backend_verdicts.py`;
- `src/falcon_correlate/unittests/test_celery_publisher_context.py`.

Shared doubles for the backend inspection tests live in
`src/falcon_correlate/unittests/celery_backend_test_doubles.py`.

## Remaining survivors and unchecked mutants

- Remaining scoped survivors: the four equivalent cast mutants above.
- Scoped mutants not checked locally: none.
- Historical run: 587 mutants were not checked. This investigation did not
  re-check mutants outside the 30 scoped survivors, and the historical
  survivors outside these three helpers remain out of scope.

## Not verified

- The exact wall-clock ordering of the historical mutation workers.
- Whether the external mutation workflow used the same Python patch release as
  the local rerun.
- The ten historical survivors outside the three scoped helpers.

## References

- [Issue #277](https://github.com/leynos/falcon-correlate/issues/277).
- [Mutation run 40876764226][run].
- [Mutation artifact 12898890551][artifact].
- [Python `typing.cast` documentation][cast].
- [Mutmut documentation][mutmut].

[run]: https://github.com/leynos/falcon-correlate/actions/runs/40876764226
[artifact]: https://github.com/leynos/falcon-correlate/actions/runs/40876764226/artifacts/12898890551
[cast]: https://docs.python.org/3/library/typing.html#typing.cast
[mutmut]: https://mutmut.readthedocs.io/
