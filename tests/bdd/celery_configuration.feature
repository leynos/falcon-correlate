Feature: Celery configuration helper
  Consumers can explicitly configure all Celery correlation propagation
  handlers through one public application setup call.

  Scenario: Explicit configuration enables publish propagation
    Given Celery correlation handlers have been disconnected
    And a Celery app configured through the public helper
    And the correlation ID is set to "configured-request-id"
    When I publish a configured Celery task
    Then the configured outgoing task message should use correlation ID "configured-request-id"

  Scenario: Explicit configuration enables worker context exposure
    Given Celery correlation handlers have been disconnected
    And a Celery app configured through the public helper
    And a configured Celery worker task request with correlation ID "configured-worker-id"
    When the configured Celery worker lifecycle runs the task
    Then the configured task body should observe correlation ID "configured-worker-id"
    And the configured ambient correlation ID should be cleared after the task finishes
