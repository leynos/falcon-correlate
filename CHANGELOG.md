# Changelog

## 0.2.0 - 2026-08-27

### Breaking changes

- Remove `falcon_correlate.hello` and its optional `_falcon_correlate_rs`
  shim. The function was template residue with no supported replacement; remove
  any calls to it ([#53](https://github.com/leynos/falcon-correlate/issues/53)).
- Remove import-time Celery signal registration. Applications must call
  `configure_celery_correlation(app)` during publisher and worker setup to
  enable correlation propagation; explicit setup reports bounded activation
  outcomes at `INFO` or `WARNING`
  ([#158](https://github.com/leynos/falcon-correlate/issues/158)).
