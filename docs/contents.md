# Documentation contents

- [Documentation contents](contents.md) is this index for the repository's
  documentation set.
- [User's guide](users-guide.md) explains how application developers use
  `falcon-correlate` in Falcon Web Server Gateway Interface (WSGI) and
  Asynchronous Server Gateway Interface (ASGI) applications.
- [Quickstart](quickstart.md) gives the shortest tested path to a Falcon WSGI
  app with correlation ID response headers and logging.
- [Developers' guide](developers-guide.md) records maintainer workflows,
  quality gates, linting policy, and implementation conventions for
  contributors.
- [Repository layout](repository-layout.md) explains where source code, tests,
  documentation, plans, and project configuration live.

## Architecture and decisions

- [Falcon correlation ID middleware design](falcon-correlation-id-middleware-design.md)
  explains the middleware architecture, request lifecycle, configuration model,
  and correlation ID propagation rules.
- [ADR-001: three-tier linting](adr-001-three-tier-linting.md) records the accepted
  linting architecture that combines Ruff, Interrogate, and PyPy-backed Pylint.
- [ADR-002: tested documentation examples](adr-002-tested-documentation-examples.md)
  records the convention for runnable examples and AST-guarded guide snippets.
- [Documentation style guide](documentation-style-guide.md) defines spelling,
  Markdown, document-structure, roadmap, Architecture Decision Record (ADR),
  and Request for Comments (RFC) conventions for this repository.

## Reference material

- [Complexity antipatterns and refactoring strategies](complexity-antipatterns-and-refactoring-strategies.md)
  provides maintainers with refactoring guidance for identifying and reducing
  implementation complexity.
- [Local validation of GitHub Actions with act and pytest](local-validation-of-github-actions-with-act-and-pytest.md)
  explains how to reproduce selected workflow checks locally.
- [Scripting standards](scripting-standards.md) describes secure helper-script
  conventions, including `Cyclopts`, `cuprum`, `pathlib`, and `cmd-mox` usage.

## Planning documents

- [Roadmap](roadmap.md) tracks the structured delivery plan for the middleware.
- [Execution plans](execplans/) hold task-level implementation plans:
  - [2.1.1 Header retrieval](execplans/2-1-1-header-retrieval.md).
  - [2.1.2 Trusted source checking](execplans/2-1-2-implement-trusted-source-checking.md).
  - [2.2.1 Default UUIDv7 generator](execplans/2-2-1-default-uuidv7-generator.md).
  - [2.2.2 Custom generator injection](execplans/2-2-2-custom-generator-injection.md).
  - [2.3.1 Default UUID validator](execplans/2-3-1-implement-default-uuid-validator.md).
  - [2.3.2 Request validation integration](execplans/2-3-2-integrate-validation-into-request-processing.md).
  - [2.4.1 Context variables](execplans/2-4-1-define-contextvars.md).
  - [2.4.2 Context variable lifecycle](execplans/2-4-2-contextvar-lifecycle.md).
  - [2.4.3 Request context integration](execplans/2-4-3-integrate-with-req-context.md).
  - [3.1.1 Contextual log filter](execplans/3-1-1-contextual-log-filter.md).
  - [3.1.2 Example logging configuration](execplans/3-1-2-example-logging-configuration.md).
  - [3.2.1 Structlog integration pattern](execplans/3-2-1-document-structlog-integration-pattern.md).
  - [4.1.1 HTTPX wrapper function](execplans/4-1-1-httpx-wrapper-function.md).
  - [4.1.2 Custom HTTPX transport](execplans/4-1-2-custom-httpx-transport.md).
  - [4.2.1 Celery task publish signal handler](execplans/4-2-1-celery-task-publish-signal-handler.md).
  - [4.2.2 Celery worker signal handlers](execplans/4-2-2-celery-worker-signal-handlers.md).
  - [4.2.3 Celery configuration utilities](execplans/4-2-3-celery-configuration-utilities.md).
  - [4.2.4 Optional Celery integration validation](execplans/4-2-4-validate-optional-celery-integration.md).
  - [5.1.1 Async middleware methods](execplans/5-1-1-implement-async-middleware-methods.md).
  - [5.1.2 Async context variable compatibility](execplans/5-1-2-ensure-context-variable-compatibility-with-async.md).
  - [6.2.1 Write quickstart guide](execplans/6-2-1-write-quickstart-guide.md).
