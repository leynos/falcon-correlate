# Development roadmap

This roadmap outlines the implementation plan for `falcon-correlate`, a
correlation ID middleware for the Falcon web framework. The roadmap is derived
from the design specification in
[falcon-correlation-id-middleware-design.md](falcon-correlation-id-middleware-design.md).

## 1. Project foundation

Establish the project structure, build tooling, and core middleware skeleton.

### 1.1. Project structure and tooling

- [x] 1.1.1. Initialise package structure
  - [x] Create `falcon_correlate/` package directory.
  - [x] Add `__init__.py` with version and public API exports.
  - [x] Configure `pyproject.toml` with package metadata and dependencies.
- [x] 1.1.2. Configure development tooling
  - [x] Add pytest configuration with coverage requirements (target: 90%).
  - [x] Configure ruff for linting and formatting.
  - [x] Configure ty for type checking.
  - [x] Update Makefile with test, lint, and typecheck targets.
- [x] 1.1.3. Set up continuous integration
  - [x] Add GitHub Actions workflow for test, lint, and typecheck.
  - [x] Configure matrix testing for Python 3.12, 3.13 and 3.14.

### 1.2. Core middleware class (WSGI)

- [x] 1.2.1. Implement middleware skeleton. See design-doc §3.1.1.
  - [x] Create `CorrelationIDMiddleware` class.
  - [x] Implement `process_request(self, req, resp)` method stub.
  - [x] Implement `process_response(self, req, resp, resource, req_succeeded)`
        method stub.
  - [x] Add type hints for all public methods.
- [x] 1.2.2. Implement configurable options. See design-doc §4.5.
  - [x] Add `header_name` parameter (default: `X-Correlation-ID`).
  - [x] Add `trusted_sources` parameter for IP allowlist.
  - [x] Add `generator` parameter for custom ID generation.
  - [x] Add `validator` parameter for incoming ID validation.
  - [x] Add `echo_header_in_response` parameter (default: `True`).
  - [x] Test default parameter values.
  - [x] Test custom parameter configuration.
  - [x] Test parameter validation and error handling.

## 2. Correlation ID lifecycle

Implement ID retrieval, generation, validation, and contextual storage.

### 2.1. Header retrieval and trusted source logic

- [x] 2.1.1. Implement header retrieval. See design-doc §3.2.1.
  - [x] Read correlation ID from configured header name.
  - [x] Handle missing or empty header values.
  - [x] Test missing header handling.
- [x] 2.1.2. Implement trusted source checking. See design-doc §3.2.2.
  - [x] Check `req.remote_addr` against trusted sources set.
  - [x] Support both exact IP matching and CIDR subnet notation.
  - [x] Accept incoming ID only if source is trusted.
  - [x] Test ID acceptance from trusted source.
  - [x] Test ID rejection from untrusted source.
  - [x] Test CIDR matching behaviour.

### 2.2. UUIDv7 generation

- [ ] 2.2.1. Implement default UUIDv7 generator. See design-doc §3.2.3.
  - [ ] Select and add UUIDv7 library dependency (prefer `uuid-utils` or
        standard library for Python 3.13+).
  - [ ] Create `default_uuid7_generator()` function returning hex string.
  - [ ] Ensure RFC 4122 compliance with millisecond precision.
  - [ ] Test default generator produces valid UUIDv7 format.
  - [ ] Test generated IDs are unique across calls.
- [ ] 2.2.2. Support custom generator injection
  - [ ] Accept `Callable[[], str]` as generator parameter.
  - [ ] Fall back to default generator if not provided.
  - [ ] Test custom generator is called when provided.

### 2.3. Incoming ID validation

- [ ] 2.3.1. Implement default UUID validator. See design-doc §3.2.4.
  - [ ] Create `default_uuid_validator(id: str) -> bool` function.
  - [ ] Validate standard UUID format (any version).
  - [ ] Return `False` for malformed or excessively long IDs.
  - [ ] Test valid UUID formats are accepted.
  - [ ] Test invalid formats are rejected.
- [ ] 2.3.2. Integrate validation into request processing
  - [ ] Validate incoming ID before acceptance.
  - [ ] Generate new ID if validation fails.
  - [ ] Log validation failures at DEBUG level.
  - [ ] Test invalid formats trigger new ID generation.
  - [ ] Test custom validator is called when provided.

### 2.4. Contextual storage with contextvars

- [ ] 2.4.1. Define context variables. See design-doc §3.3.1.
  - [ ] Create `correlation_id_var: ContextVar[str | None]`.
  - [ ] Create `user_id_var: ContextVar[str | None]`.
  - [ ] Export context variables in public API.
- [ ] 2.4.2. Implement context variable lifecycle. See design-doc §3.3.4.
  - [ ] Set correlation ID in `process_request`.
  - [ ] Store reset token for cleanup.
  - [ ] Reset context variable in `process_response`.
  - [ ] Ensure cleanup occurs even if request processing fails.
  - [ ] Test context variable is set during request.
  - [ ] Test context variable is cleared after response.
  - [ ] Test context isolation between concurrent requests.
- [ ] 2.4.3. Integrate with Falcon's req.context. See design-doc §3.3.3.
  - [ ] Copy correlation ID to `req.context.correlation_id`.
  - [ ] Provide both access methods in documentation.

## 3. Logging integration

Provide utilities for injecting correlation IDs into log records.

### 3.1. Standard logging filter

- [ ] 3.1.1. Implement ContextualLogFilter. See design-doc §3.4.1.
  - [ ] Create `ContextualLogFilter(logging.Filter)` class.
  - [ ] Inject `correlation_id` attribute into log records.
  - [ ] Inject `user_id` attribute into log records.
  - [ ] Use placeholder value (e.g., `-`) when context is not set.
  - [ ] Test filter adds attributes to log records.
  - [ ] Test placeholder values when context is empty.
  - [ ] Test filter integrates with standard logging configuration.
- [ ] 3.1.2. Provide example logging configuration. See design-doc §3.4.2.
  - [ ] Document recommended format string.
  - [ ] Provide dictConfig example in docstrings.

### 3.2. Structlog integration (optional)

- [ ] 3.2.1. Document structlog integration pattern. See design-doc §3.4.3.
  - [ ] Explain `merge_contextvars` processor usage.
  - [ ] Provide configuration example.
  - [ ] Note that no additional code is required if contextvars are used.
- [ ] 3.2.2. Validate structlog integration
  - [ ] Test correlation ID appears in structured log output.
  - [ ] Mark test as skipped if structlog is not installed.

## 4. Downstream propagation

Enable correlation ID propagation to downstream HTTP services and Celery tasks.

### 4.1. httpx propagation utilities

- [ ] 4.1.1. Implement wrapper function. See design-doc §3.5.1.4.
  - [ ] Create `request_with_correlation_id(method, url, **kwargs)` function.
  - [ ] Create async variant `async_request_with_correlation_id`.
  - [ ] Inject correlation ID header if context variable is set.
  - [ ] Preserve existing headers passed by caller.
  - [ ] Test wrapper function adds header.
  - [ ] Test existing headers are preserved.
- [ ] 4.1.2. Implement custom transport. See design-doc §3.5.1.3.
  - [ ] Create `CorrelationIDTransport(httpx.BaseTransport)` class.
  - [ ] Create async variant `AsyncCorrelationIDTransport`.
  - [ ] Inject header in `handle_request` method.
  - [ ] Test custom transport adds header.
  - [ ] Test header is not added when context is empty.

### 4.2. Celery propagation utilities

- [ ] 4.2.1. Implement task publish signal handler. See design-doc §3.5.2.2.
  - [ ] Create `propagate_correlation_id_to_celery` signal handler.
  - [ ] Connect to `before_task_publish` signal.
  - [ ] Inject correlation ID into message properties.
  - [ ] Test correlation ID is injected into task message.
- [ ] 4.2.2. Implement worker signal handlers. See design-doc §3.5.2.4.
  - [ ] Create `setup_correlation_id_in_worker` for `task_prerun`.
  - [ ] Create `clear_correlation_id_in_worker` for `task_postrun`.
  - [ ] Store reset tokens for cleanup.
  - [ ] Test correlation ID is available in worker context.
  - [ ] Test context is cleared after task execution.
- [ ] 4.2.3. Provide Celery configuration utilities
  - [ ] Create `configure_celery_correlation(app)` helper function.
  - [ ] Connect all signal handlers in one call.
- [ ] 4.2.4. Validate optional Celery integration
  - [ ] Mark tests as skipped if Celery is not installed.

## 5. ASGI support

Extend the middleware to support Falcon's ASGI mode.

### 5.1. ASGI middleware variant

- [ ] 5.1.1. Implement async middleware methods. See design-doc §3.1.1.
  - [ ] Create `CorrelationIDMiddlewareASGI` class.
  - [ ] Implement `async process_request(self, req, resp)`.
  - [ ] Implement `async process_response(self, req, resp, resource,
        req_succeeded)`.
  - [ ] Share configuration logic with WSGI variant.
  - [ ] Test middleware functions in an ASGI application.
- [ ] 5.1.2. Ensure context variable compatibility with async
  - [ ] Verify `contextvars` behaviour in async context.
  - [ ] Test with concurrent async requests.
  - [ ] Test context isolation with concurrent async requests.
  - [ ] Test cleanup on async request completion.

## 6. Documentation and release

Complete documentation, examples, and prepare for initial release.

### 6.1. API documentation

- [ ] 6.1.1. Write docstrings for all public APIs
  - [ ] Document `CorrelationIDMiddleware` class and parameters.
  - [ ] Document context variables and access patterns.
  - [ ] Document logging filter and configuration.
  - [ ] Document propagation utilities.
- [ ] 6.1.2. Generate API reference documentation
  - [ ] Configure Sphinx or MkDocs.
  - [ ] Generate autodoc from docstrings.
  - [ ] Publish to Read the Docs or GitHub Pages.

### 6.2. User guide and examples

- [ ] 6.2.1. Write quickstart guide
  - [ ] Provide minimal working example.
  - [ ] Explain basic configuration options.
  - [ ] Show logging integration.
- [ ] 6.2.2. Write advanced usage guide
  - [ ] Document trusted source configuration.
  - [ ] Document custom generator and validator usage.
  - [ ] Document httpx and Celery integration.
- [ ] 6.2.3. Create example applications
  - [ ] Create minimal Falcon WSGI example.
  - [ ] Create Falcon ASGI example.
  - [ ] Create example with Celery integration.

### 6.3. Release preparation

- [ ] 6.3.1. Prepare package for PyPI
  - [ ] Finalise `pyproject.toml` metadata.
  - [ ] Add LICENSE file.
  - [ ] Add CHANGELOG.md.
  - [ ] Configure build and publish workflow.
- [ ] 6.3.2. Perform pre-release validation
  - [ ] Run full test suite across Python versions.
  - [ ] Verify package installs correctly from test PyPI.
  - [ ] Review documentation for completeness.
- [ ] 6.3.3. Publish initial release
  - [ ] Tag release version (0.1.0).
  - [ ] Publish to PyPI.
  - [ ] Announce release.

## 7. Future enhancements

Post-1.0 features for consideration based on user feedback.

### 7.1. OpenTelemetry integration

- [ ] 7.1.1. Investigate OpenTelemetry trace context propagation.
        See design-doc §5.3.
  - [ ] Research W3C Trace Context header format.
  - [ ] Evaluate linking correlation ID to trace ID.
- [ ] 7.1.2. Implement optional OpenTelemetry integration
  - [ ] Add optional dependency on `opentelemetry-api`.
  - [ ] Extract trace ID from OpenTelemetry context if available.

### 7.2. Advanced validation and transformation

- [ ] 7.2.1. Implement ID transformer support. See design-doc §5.3.
  - [ ] Add `transformer` parameter to middleware.
  - [ ] Allow normalisation of incoming IDs.
- [ ] 7.2.2. Implement format-specific validators
  - [ ] Add UUIDv7-specific validator.
  - [ ] Add configurable length limits.

### 7.3. Dynamic configuration

- [ ] 7.3.1. Support runtime trusted source updates. See design-doc §5.3.
  - [ ] Add callback mechanism for trusted source list.
  - [ ] Document integration with configuration management systems.
