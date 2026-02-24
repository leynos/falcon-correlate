Feature: Contextual log filter
  As a developer using falcon-correlate
  a logging filter is needed that injects correlation ID and user ID
    into log records
  so that application logs include request context automatically

  Scenario: Filter injects correlation ID into log record
    Given a contextual log filter
    And the correlation ID is set to "abc-123"
    When the filter processes a log record
    Then the log record should have correlation_id "abc-123"

  Scenario: Filter injects user ID into log record
    Given a contextual log filter
    And the user ID is set to "user-456"
    When the filter processes a log record
    Then the log record should have user_id "user-456"

  Scenario: Filter uses placeholder when context is empty
    Given a contextual log filter
    And no context variables are set
    When the filter processes a log record
    Then the log record should have correlation_id "-"
    And the log record should have user_id "-"

  Scenario: Filter integrates with standard logging
    Given a logger configured with the contextual log filter
    And the correlation ID is set to "req-789"
    And the user ID is set to "admin"
    When a log message "test entry" is emitted
    Then the formatted output should contain "req-789"
    And the formatted output should contain "admin"
