# Debugging plan: worker cleanup mutation survivors

**Generated**: 2026-10-30 **Updated**: 2026-11-11 **Issue ID**: #279
**Severity**: Low **Status**: Resolved

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

### Post-rebase reproduction

Issue #264 landed on `main` as commit `2cd9417` (PR #281) while this branch was
in review. Its paired-placeholder change altered
`clear_correlation_id_in_worker`, so the branch was rebased onto `1a65a08` and
the scoped run was repeated at the rebased head, `7082d20`:

```plaintext
Worktree: /home/leynos/.cache/fc-279/rebased (detached HEAD at 7082d20)
Command:  uv run --with mutmut==3.6.0 mutmut run \
            'falcon_correlate._celery_worker_signals.x_clear_correlation_id_in_worker*'
Result:   18 mutants, 17 killed, 1 survived (mutmut_16)
```

The first attempt at this run stopped before mutation testing. mutmut selects
tests as an unordered set, and that ordering exposed a test-isolation defect
added with #264: the token-stack tests disconnect the process-global worker
receivers by dispatch UID, while the BDD worker module connected them once per
session. A BDD scenario that ran after a token-stack test therefore had no
setup receiver and observed no correlation ID. Commit `9b99807` connects the
receivers before every BDD scenario; the rerun then completed. A later cleanup
commit, `7082d20`, removes an unused import and the blank lines the rebase
required in `test_celery_worker_signal.py`.

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

| Revision  | Mutant    | Source line | Mutation                                                                            | Status at revision |
| --------- | --------- | ----------- | ----------------------------------------------------------------------------------- | ------------------ |
| `8fe6e33` | mutmut_6  | 105         | `.get(_CORRELATION_ID_CONTEXT_KEY, [])` → `.get(_CORRELATION_ID_CONTEXT_KEY, None)` | survived           |
| `8fe6e33` | mutmut_8  | 105         | `.get(_CORRELATION_ID_CONTEXT_KEY, [])` → `.get(_CORRELATION_ID_CONTEXT_KEY)`       | survived           |
| `8fe6e33` | mutmut_14 | 113         | `.pop(_CORRELATION_ID_CONTEXT_KEY, None)` → `.pop(_CORRELATION_ID_CONTEXT_KEY)`     | survived           |
| `7082d20` | mutmut_6  | 108         | `.get(_CORRELATION_ID_CONTEXT_KEY, [])` → `.get(_CORRELATION_ID_CONTEXT_KEY, None)` | killed             |
| `7082d20` | mutmut_8  | 108         | `.get(_CORRELATION_ID_CONTEXT_KEY, [])` → `.get(_CORRELATION_ID_CONTEXT_KEY)`       | killed             |
| `7082d20` | mutmut_16 | 118         | `.pop(_CORRELATION_ID_CONTEXT_KEY, None)` → `.pop(_CORRELATION_ID_CONTEXT_KEY)`     | survived           |

The `7082d20` rows reflect the rebased branch's own test suite, so the two
`.get` mutants are killed there; the `8fe6e33` rows are the original baseline
reproduction that motivated the investigation.

`mutmut show` prints an extracted image of the function, so its hunk headers
refer to lines of that image rather than the module. The mapping above is to
`src/falcon_correlate/_celery_worker_signals.py` at each revision.

The `.get` mutants keep their numbers after #264. The `.pop` mutant was
`mutmut_14` before #264 and is `mutmut_16` after it: the placeholder branch adds
`mutmut_14` (`.pop(None, None)`) and `mutmut_15` (`.pop(None)`), both of which
the suite kills.

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

### mutmut_16 (formerly mutmut_14)

```diff
-        stored_tokens.pop(_CORRELATION_ID_CONTEXT_KEY, None)
+        stored_tokens.pop(_CORRELATION_ID_CONTEXT_KEY, )
```

## Analysis

### Why mutmut_6 and mutmut_8 survived

Both mutants replace the defensive empty-list default on line 108 with a
default that is `None`. Line 108 is reached only when the context-local store
is non-empty (line 104 returns for an empty store). From there the original
behaviour differs only when the store does **not** contain
`_CORRELATION_ID_CONTEXT_KEY`:

- A store containing the key with an empty list passes line 108 and returns at
  line 109, before the value matters.
- A store containing only unrelated keys makes both mutants evaluate
  `list(None)`, which raises `TypeError`.

No existing test handed cleanup a non-empty store without the correlation key,
so the mutated `TypeError` path was never executed. The defect is therefore a
genuine coverage gap, not an equivalent mutation.

### Why mutmut_16 (formerly mutmut_14) is equivalent

To reach line 118, execution must first pass line 109 with a non-empty
`correlation_id_tokens` list. That list is a copy produced by `list(...)` on
line 108, so it can be non-empty only when `stored_tokens` contains
`_CORRELATION_ID_CONTEXT_KEY` with a non-empty value.

Between line 108 and line 118:

- line 112 pops from the copy, not from `stored_tokens`;
- line 115 selects line 118 only because the copy is now empty, so line 116 does
  not run;
- the `None` placeholder branch on lines 113-114 leaves the store unchanged;
- no other statement removes the key from `stored_tokens`.

The key is therefore always present when line 118 executes, and
`dict.pop(key, None)` returns the stored value rather than the default.
Omitting the default leaves the observable result unchanged. Within the declared
`_CeleryContextTokens` contract (`dict[str, list[Token | None]]`), the mutant
is observationally equivalent.

### Configured Celery signals add no distinct evidence

The planned investigation allowed configured `task_prerun`/`task_postrun`
dispatch as an alternative evidence source. It cannot reach the gap: setup
writes only `_CORRELATION_ID_CONTEXT_KEY` (now with a `None` placeholder for an
unusable ID, which still creates that key), and cleanup normalizes an exhausted
store to `None`. Dispatch therefore never presents cleanup with a non-empty
store that lacks the correlation key. Direct helper calls are the only route
that constructs the relevant store state, so no configured-signal test was
added for this gap.

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

- `{}` (empty store, returns at line 104);
- `{_CORRELATION_ID_CONTEXT_KEY: []}` (returns at line 109);
- `{"unrelated": []}` (reaches `list(...)` on line 108 without the key).

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
empty store are restored. The property test carries no Celery skip guard. The
rebase keeps #264's paired-placeholder `_TokenStackModel` and layers these
stronger store-shape assertions on top of it, so the model still distinguishes
real reset tokens from `None` placeholders.

### Test module placement

The cleanup tests are direct helper calls and need no Celery import, so they
were split into their own module. `test_celery_worker_cleanup.py` is listed in
`_CELERY_INDEPENDENT_TEST_MODULES` so the optional-Celery blocked-child harness
does not expect it to skip. This keeps the missing-Celery skip-count contract
accurate while letting the cleanup tests run in dependency-free environments.
`test_celery_worker_signal.py` shares the task builder through the new
`celery_worker_helpers.py` module and remains within the 400-line file limit.
The rebase extends that shared builder with #264's sentinel semantics so the
signal tests still model a request that omits `correlation_id` entirely.

### BDD signal connection isolation

`tests/bdd/test_celery_worker_signal_steps.py` now connects the worker
receivers before every scenario instead of once per session. The #264
token-stack tests disconnect the same process-global receivers by dispatch UID,
so a session-scoped connection does not survive arbitrary test ordering. mutmut
selects tests as an unordered set, which made the failure reproducible during
verification. Reconnecting per scenario is cheap because the stable dispatch
UID makes the call idempotent.

### Production code

This branch makes no production change of its own. The rebased production code
comes from #264, including its users' guide and design-document updates. The
cleanup handler's observable contract is unchanged by this branch.

## Verification

A fresh scoped mutation run was executed against the final test state before
the rebase, at `d3a7318`:

```plaintext
uv run --with mutmut==3.6.0 mutmut run \
  'falcon_correlate._celery_worker_signals.x_clear_correlation_id_in_worker*'
```

Result: 16 mutants evaluated, 15 killed, 1 survived (mutmut_14).

After the rebase onto #264, the same command was run in a fresh isolated
worktree at `7082d20`:

```plaintext
Worktree: /home/leynos/.cache/fc-279/rebased (detached HEAD at 7082d20)
Result:   18 mutants evaluated, 17 killed, 1 survived (mutmut_16)
```

`7082d20` is the final code commit; commits after it change documentation only.
The extra two mutants target the new `None` placeholder branch and are both
killed. Current dispositions:

| Mutant    | Final status | Disposition                                                          |
| --------- | ------------ | -------------------------------------------------------------------- |
| mutmut_6  | killed       | Real gap; killed by `[unrelated-key-only]` cleanup no-op test.       |
| mutmut_8  | killed       | Real gap; killed by the same test.                                   |
| mutmut_16 | survived     | Justified equivalent; default is unreachable when line 118 executes. |

### Why no `# pragma: no mutate` was used

In mutmut 3.6.0, `# pragma: no mutate` suppresses every mutation on its line.
Line 118 also hosts mutmut_14 (`.pop(None, None)`) and mutmut_15
(`.pop(None)`), which are killable. Adding the pragma reduced the scoped mutant
count from 18 to 15, removing live coverage of those mutants as well. Because
the line has other killable mutations, the project rule permits only
documenting this survivor, not suppressing it.

## Remaining survivors and unchecked mutants

Within `clear_correlation_id_in_worker`, the only remaining survivor is
mutmut_16, which is justified equivalent and requires no test change.

The scheduled artefact reported 40 surviving mutants and 587 not-checked
mutants across the repository. This investigation classified only the cleanup
function's mutants (16 at the original revision, 18 after the rebase); the
other survivors and all 587 unchecked mutants were not examined here and remain
outside its scope.

## Relationship to #264

Issue #264 (preserving worker tokens for nested tasks that lack IDs) landed on
`main` as commit `2cd9417` (PR #281) while this branch was in review. The
rebase adopts its paired-placeholder contract:

- setup pushes exactly one stack entry per call, using a `None` placeholder
  when the request has no usable correlation ID;
- cleanup pops exactly one entry and resets the context only for a real token;
- the old missing-ID limitation test,
  `test_nested_missing_id_setup_allows_cleanup_to_consume_outer_token`, is
  removed because #264 deliberately replaced that behaviour. `main` had already
  deleted it, and the rebase does not resurrect it;
- the property test keeps #264's `_TokenStackModel` and this branch's stronger
  store-shape and unwinding assertions;
- the shared `build_task` helper keeps #264's sentinel semantics for a request
  that omits `correlation_id` entirely.

The cleanup survivors remain independent of #264:

- mutmut_6 and mutmut_8 are still killed by seeding a store directly, with no
  nested missing-ID sequence; placeholders do not change the unrelated-key-only
  store state that exposes the gap;
- mutmut_16's equivalence proof depends only on the token-stack invariant:
  reaching the pop line requires the key to be present. #264 preserves that
  invariant, and the rebased run confirms the same single survivor.

## References

- [Issue #279](https://github.com/leynos/falcon-correlate/issues/279)
- [Issue #264](https://github.com/leynos/falcon-correlate/issues/264)
- [PR #281](https://github.com/leynos/falcon-correlate/pull/281) landed #264 as
  `2cd9417`.
