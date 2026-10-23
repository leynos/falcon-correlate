# Architectural decision record (ADR) 004: explicit Celery signal registration

## Status

Accepted on 2026-08-27. Version 0.2.0 removes Celery signal registration from
module import and makes `configure_celery_correlation(app)` the required
activation seam.

## Date

2026-08-27.

## Context and problem statement

The package root re-exports the Celery integration. As a result, importing an
unrelated package submodule first executed `falcon_correlate.__init__`, which
imported the Celery integration, loaded Celery, and connected three handlers to
Celery's process-global signal registry. This imposed an import cost and a
hidden global mutation in processes that did not publish or execute tasks.

The library already exposed `configure_celery_correlation(app)`, but
import-time registration meant it was not the observable configuration seam.
Consumers could not use it to test whether registration was enabled or disabled
without manually disconnecting receivers by their private dispatch identifiers.

## Decision drivers

- Keep non-Celery package imports independent of the optional dependency.
- Make global signal mutation visible at application configuration time.
- Preserve the existing handlers, dispatch identifiers, and idempotent setup.
- Provide an isolated regression test for the package import boundary.

## Options considered

### Keep import-time registration

This preserves existing startup behaviour, but continues to load Celery and
mutate its global signal registry for every package import.

### Move Celery exports out of the package root

This would make the integration import more explicit, but it changes the
package's public import surface and leaves the configuration helper less useful
than it already is.

### Make registration explicit

This keeps the current public exports and handler implementation while making
`configure_celery_correlation(app)` the only operation that imports Celery
signals and connects receivers.

## Decision outcome

Choose explicit registration. Importing `falcon_correlate` and
`falcon_correlate.celery` defines names only: neither import loads Celery nor
connects its signals. Publisher and worker bootstrap code must call
`configure_celery_correlation(app)` before relying on correlation propagation.

Stable dispatch identifiers keep repeated configuration calls idempotent. A
subprocess test proves that the package import leaves Celery absent from
`sys.modules`, that no integration receiver is connected initially, and that
the helper connects every supported receiver. Each explicit configuration
outcome is also reported once per app and outcome through the
`falcon_correlate.celery` logger: active setup at `INFO`, incomplete setup at
`WARNING`. The structured record uses bounded connection and publisher-context
statuses plus the backend RPC verdict. The activation record reports the
backend as `unknown` because inspection is deferred. An eligible publish caches
a definite verdict internally when inspection succeeds; this does not update
the activation record. `unknown` is not itself a registration failure.
Weak-reference state deduplicates records without retaining configured apps.

## Compatibility and migration

This is a breaking change in version 0.2.0. Applications that previously relied
on importing `falcon_correlate` must call `configure_celery_correlation(app)`
during setup in every publisher and worker process.

## Consequences

Non-Celery consumers can import the package and read `correlation_id_var`
without paying the Celery import cost or mutating Celery process state.
Applications that use Celery gain an explicit, testable configuration seam and
bounded diagnostics for calls made through that seam. No diagnostic is emitted
on package or module import, and the records cannot detect an omitted
configuration call. Applications control whether `INFO` records are visible.
Records do not include app representations, backend URIs, credentials,
payloads, correlation IDs, or user IDs. The public configuration signature and
same-app return value remain unchanged; no health API is added.
