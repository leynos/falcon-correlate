Feature: Structlog integration
  As a developer using falcon-correlate with structlog
  structured log output should include correlation ID and user ID
  so that application logs are traceable in structured format

  Scenario: Custom processor injects correlation ID and user ID
    Given structlog is configured with the correlation context processor
    And the correlation ID is set to "struct-cid-001"
    And the user ID is set to "struct-uid-001"
    When a structlog message "structlog test" is emitted
    Then the structlog event should contain "correlation_id" with value "struct-cid-001"
    And the structlog event should contain "user_id" with value "struct-uid-001"

  Scenario: Custom processor uses placeholder when context is empty
    Given structlog is configured with the correlation context processor
    And no context variables are set
    When a structlog message "placeholder test" is emitted
    Then the structlog event should contain "correlation_id" with value "-"
    And the structlog event should contain "user_id" with value "-"
