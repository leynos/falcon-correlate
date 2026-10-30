# Debugging plan: worker cleanup mutation survivors

**Generated**: 2026-10-30 **Issue ID**: #279 **Severity**: Low **Status**:
Resolved

## Problem statement

The scheduled mutation run reported three surviving mutants in
`clear_correlation_id_in_worker`:

- `x_clear_correlation_id_in_worker__mutmut_6`
- `x_clear_correlation_id_in_worker__mutmut_8`
- `x_clear_correlation_id_in_worker__mutmut_14`

Each survivor must be shown to be either a real gap in behavioural coverage or
a provably equivalent mutation. An equivalent mutation is one where the mutated
program is observationally identical to the original, so no test can
distinguish them.

## Reproduction

The survivors were reproduced at the revision under investigation,
`8fe6e33aa4b2681574ec6dd593e8bb794f3d177e`, in an isolated worktree so the
scheduled-result baseline was not disturbed:

```plaintext
Worktree: /home/leynos/.cache/fc-279/baseline (detached HEAD at 8fe6e33)
Command:  uv run --with mutmut==3.6.0 mutmut run \
            'falcon_correlate._celery_worker_signals.x_clear_correlation_id_in_worker*'
Result:   16 mutants, 13 killed, 3 survived (mutmut_6, mutmut_8, mutmut_14)
```

Mutant numbers were mapped by inspecting each diff with `mutmut show`; the
issue text's numbering was not assumed to identify the mutations.

### Scheduled artefact cross-check

The GitHub Actions mutation artefact for run `40876764226` (artefact
`12898890551`) reports the same cleanup function results:

| Scope                            | Killed | Survived | Not checked |
| -------------------------------- | ------ | -------- | ----------- |
| Whole repository                 | 210    | 40       | 587         |
| `clear_correlation_id_in_worker` | 13     | 3        | 0           |

The local isolated run reproduced the per-function numbers exactly, so the
survivors were not an artefact of a different revision or sandbox state.

## Exact mutant diffs

| Mutant    | Source line | Mutation                                                                            | Baseline |
| --------- | ----------- | ----------------------------------------------------------------------------------- | -------- |
| mutmut_6  | 105         | `.get(_CORRELATION_ID_CONTEXT_KEY, [])` → `.get(_CORRELATION_ID_CONTEXT_KEY, None)` | survived |
| mutmut_8  | 105         | `.get(_CORRELATION_ID_CONTEXT_KEY, [])` → `.get(_CORRELATION_ID_CONTEXT_KEY)`       | survived |
| mutmut_14 | 113         | `.pop(_CORRELATION_ID_CONTEXT_KEY, None)` → `.pop(_CORRELATION_ID_CONTEXT_KEY)`     | survived |

`mutmut show` prints an extracted image of the function, so its hunk headers
refer to lines 34 and 42 of that image. The equivalent lines in
`src/falcon_correlate/_celery_worker_signals.py` are 105 and 113.

### mutmut_6

```diff
-    correlation_id_tokens = list(stored_tokens.get(_CORRELATION_ID_CONTEXT_KEY, []))
+    correlation_id_tokens = list(stored_tokens.get(_CORRELATION_ID_CONTEXT_KEY, None))
```

### mutmut_8

```diff
-    correlation_id_tokens = list(stored_tokens.get(_CORRELATION_ID_CONTEXT_KEY, []))
+    correlation_id_tokens = list(stored_tokens.get(_CORRELATION_ID_CONTEXT_KEY, ))
```

### mutmut_14

```diff
-        stored_tokens.pop(_CORRELATION_ID_CONTEXT_KEY, None)
+        stored_tokens.pop(_CORRELATION_ID_CONTEXT_KEY, )
```

## Analysis

### Why mutmut_6 and mutmut_8 survived

Both mutants replace the defensive empty-list default on line 105 with a
default that is `None`. Line 105 is reached only when the context-local store
is non-empty (line 102 returns for an empty store). From there the original
behaviour differs only when the store does **not** contain
`_CORRELATION_ID_CONTEXT_KEY`:

- A store containing the key with an empty list passes line 105 and returns at
  line 106, before the value matters.
- A store containing only unrelated keys makes both mutants evaluate
  `list(None)`, which raises `TypeError`.

No existing test handed cleanup a non-empty store without the correlation key,
so the mutated `TypeError` path was never executed. The defect is therefore a
genuine coverage gap, not an equivalent mutation.

### Why mutmut_14 is equivalent

To reach line 113, execution must first pass line 106 with a non-empty
`correlation_id_tokens` list. That list is a copy produced by `list(...)` on
line 105, so it can be non-empty only when `stored_tokens` contains
`_CORRELATION_ID_CONTEXT_KEY` with a non-empty value.

Between line 105 and line 113:

- line 109 pops from the copy, not from `stored_tokens`;
- line 110 selects line 113 only because the copy is now empty, so line 111 does
  not run;
- no other statement removes the key from `stored_tokens`.

The key is therefore always present when line 113 executes, and
`dict.pop(key, None)` returns the stored value rather than the default.
Omitting the default leaves the observable result unchanged. Within the declared
`_CeleryContextTokens` contract (`dict[str, list[Token]]`), the mutant is
observationally equivalent.

### Configured Celery signals add no distinct evidence

The planned investigation allowed configured `task_prerun`/`task_postrun`
dispatch as an alternative evidence source. It cannot reach the gap: setup
writes only `_CORRELATION_ID_CONTEXT_KEY`, and cleanup normalizes an exhausted
store to `None`. Dispatch therefore never presents cleanup with a non-empty
store that lacks the correlation key. Direct helper calls are the only route
that constructs the relevant store state, so no configured-signal test was
added.

### Sandbox Celery-skip hypothesis

A plausible alternative was that the mutants survived because Celery-guarded
tests were skipped inside mutmut's sandbox. This is falsified:

- the scheduled artefact's `tests_by_mangled_function_name` entry maps
  Celery-guarded tests, including
  `tests/bdd/test_celery_worker_signal_steps.py` and
  `test_configure_celery_correlation_isolates_nested_task_context`, to the
  cleanup function;
- the local isolated baseline run reproduced the same three survivors, so
  sandbox skip behaviour is not the differentiator.

## Changes made

### Tests that kill mutmut_6 and mutmut_8

`src/falcon_correlate/unittests/test_celery_worker_cleanup.py` adds
`test_clear_handler_is_noop_for_stores_without_reset_tokens`, parameterized
over:

- `{}` (empty store, returns at line 102);
- `{_CORRELATION_ID_CONTEXT_KEY: []}` (returns at line 106);
- `{"unrelated": []}` (reaches `list(...)` on line 105 without the key).

The unrelated-key-only case is the killer: cleanup must not raise, must
preserve the ambient correlation ID, and must leave the store object unchanged.

### Other cleanup assertions

The same module now also covers:

- a second cleanup after the last token is popped (no-op, store remains
  exhausted);
- retained outer tokens and unrelated store entries while unwinding nested
  setups, including identity preservation of the unrelated entry;
- LIFO restoration from an inner task to the outer task and then to the ambient
  value;
- removal of the exhausted stack state once the last token is consumed.

`tests/property/test_celery_worker_lifecycle.py` strengthens the generated
lifecycle model: for every intermediate operation it now asserts that a zero
depth leaves exactly `None`, and a non-zero depth retains only the
`"correlation_id"` key with a list length equal to the modelled depth. It also
unwinds any outstanding setups at the end and asserts the ambient value and an
empty store are restored. The property test carries no Celery skip guard.

### Test module placement

The cleanup tests are direct helper calls and need no Celery import, so they
were split into their own module. `test_celery_worker_cleanup.py` is listed in
`_CELERY_INDEPENDENT_TEST_MODULES` so the optional-Celery blocked-child harness
does not expect it to skip. This keeps the missing-Celery skip-count contract
accurate while letting the cleanup tests run in dependency-free environments.
`test_celery_worker_signal.py` shares the task builder through the new
`celery_worker_helpers.py` module and remains within the 400-line file limit.

### Production code

No production change was made. No user-facing behaviour or contract changed, so
the users' guide and design documents are unchanged.

## Verification

A fresh scoped mutation run was executed against the final test state:

```plaintext
uv run --with mutmut==3.6.0 mutmut run \
  'falcon_correlate._celery_worker_signals.x_clear_correlation_id_in_worker*'
```

Result: 16 mutants evaluated, 15 killed, 1 survived.

| Mutant    | Final status | Disposition                                                          |
| --------- | ------------ | -------------------------------------------------------------------- |
| mutmut_6  | killed       | Real gap; killed by `[unrelated-key-only]` cleanup no-op test.       |
| mutmut_8  | killed       | Real gap; killed by the same test.                                   |
| mutmut_14 | survived     | Justified equivalent; default is unreachable when line 113 executes. |

### Why no `# pragma: no mutate` was used

In mutmut 3.6.0, `# pragma: no mutate` suppresses every mutation on its line.
Line 113 also hosts mutmut_15 and mutmut_16, which are killable. Adding the
pragma reduced the scoped mutant count from 16 to 13, removing live coverage of
those mutants as well. Because the line has other killable mutations, the
project rule permits only documenting this survivor, not suppressing it.

## Remaining survivors and unchecked mutants

Within `clear_correlation_id_in_worker`, the only remaining survivor is
mutmut_14, which is justified equivalent and requires no test change.

The scheduled artefact reported 40 surviving mutants and 587 not-checked
mutants across the repository. This investigation classified only the 16
mutants in the cleanup function; the other 37 survivors and all 587 unchecked
mutants were not examined here and remain outside its scope.

## Relationship to #264

Issue #264 proposes preserving worker tokens for nested tasks that lack IDs.
Its branch, `issue-264-preserve-worker-tokens-for-nested-tasks-without-ids`,
points at `f0d96e2c61f1069d0f7b09b8bb8a4d1d63a8b74f`, the same commit as the
base of this work, with no commits ahead of it and no matching remote branch.
No #264 implementation has landed.

The survivors are independent of #264:

- mutmut_6 and mutmut_8 are killed by seeding a store directly, with no nested
  missing-ID sequence;
- mutmut_14's equivalence proof depends only on the current token-stack
  invariant, which any #264 change would have to preserve or explicitly
  redefine;
- the missing-ID limitation test,
  `test_nested_missing_id_setup_allows_cleanup_to_consume_outer_token`, is
  deliberately unchanged.

## References

- [Issue #279](https://github.com/leynos/falcon-correlate/issues/279)
- [Issue #264](https://github.com/leynos/falcon-correlate/issues/264)
