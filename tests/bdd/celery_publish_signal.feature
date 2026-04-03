Feature: Celery publish correlation ID propagation
  As a developer using falcon-correlate
  I want Celery task publishes to carry the current correlation ID
  So that background task traces stay linked to the originating request

  Scenario: Publishing a Celery task injects the current correlation ID
    Given the correlation ID is set to "bdd-celery-cid-001"
    When I publish a Celery task
    Then the outgoing task message should use correlation ID "bdd-celery-cid-001"

  Scenario: Publishing without a correlation ID leaves Celery's generated value intact
    Given no correlation ID is set
    When I publish a Celery task
    Then the outgoing task message should keep the generated task ID as correlation ID

  Scenario: Publishing with an explicit task correlation ID uses the ambient request value
    Given the correlation ID is set to "bdd-celery-cid-002"
    When I publish a Celery task with explicit correlation ID "explicit-cid"
    Then the outgoing task message should use correlation ID "bdd-celery-cid-002"

  Scenario: Publishing without an ambient correlation ID preserves an explicit Celery correlation ID
    Given no correlation ID is set
    When I publish a Celery task with explicit correlation ID "explicit-correlation-id"
    Then the outgoing task message should use correlation ID "explicit-correlation-id"
