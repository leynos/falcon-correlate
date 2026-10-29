# Changelog

## Unreleased

### Documentation

- Document the Celery worker helpers as supported lower-level API and recommend
  `configure_celery_correlation(app)` for standard activation. There is no
  behaviour change.

## 0.2.0 - 2026-10-26

### Added

- Publish an sdist and pure-Python wheel with Sigstore build provenance through
  an idempotent Trusted Publishing pipeline. PyPI is the source of truth, and
  the GitHub Release is reconciled with the same distribution bytes.
- Version 0.2.0 is the first release with distribution artefacts. The `v0.1.0`
  GitHub Release has no assets because its former download path did not match
  the uploaded artefact name; it will not be manually back-filled.

### Breaking changes

- Remove `falcon_correlate.hello` and its optional `_falcon_correlate_rs`
  shim. The function was template residue with no supported replacement; remove
  any calls to it ([#53](https://github.com/leynos/falcon-correlate/issues/53)).
- Remove import-time Celery signal registration. Applications must call
  `configure_celery_correlation(app)` during publisher and worker setup to
  enable correlation propagation; explicit setup reports bounded activation
  outcomes at `INFO` or `WARNING`
  ([#158](https://github.com/leynos/falcon-correlate/issues/158)).
