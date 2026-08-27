# Changelog

## 0.2.0 - 2026-08-27

### Breaking changes

- Remove import-time Celery signal registration. Applications must call
  `configure_celery_correlation(app)` during publisher and worker setup to
  enable correlation propagation.
