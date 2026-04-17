Feature: Celery worker correlation ID propagation
  As a developer using falcon-correlate in Celery workers
  I want task execution to expose the incoming correlation ID
  So that task logs and downstream calls stay linked to the originating request

  Scenario: Running a task exposes and then clears the propagated correlation ID
    Given a Celery worker task request with correlation ID "bdd-worker-cid-001"
    When the Celery worker lifecycle runs the task
    Then the task body should observe correlation ID "bdd-worker-cid-001"
    And the ambient correlation ID should be cleared after the task finishes

  Scenario: Running a task restores a pre-existing ambient correlation ID
    Given the ambient correlation ID is set to "ambient-worker-cid-001"
    And a Celery worker task request with correlation ID "bdd-worker-cid-002"
    When the Celery worker lifecycle runs the task
    Then the task body should observe correlation ID "bdd-worker-cid-002"
    And the ambient correlation ID should be restored to "ambient-worker-cid-001" after the task finishes
