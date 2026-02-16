Feature: Context variable definitions
  As a developer using falcon-correlate
  I want context variables for correlation ID and user ID
  So that request-scoped data is available throughout the application

  Scenario: Correlation ID context variable exists with None default
    Given the correlation ID context variable
    When I retrieve its default value
    Then the value should be None

  Scenario: User ID context variable exists with None default
    Given the user ID context variable
    When I retrieve its default value
    Then the value should be None

  Scenario: Correlation ID context variable can be set and retrieved
    Given the correlation ID context variable
    When I set the value to "test-correlation-id"
    Then the retrieved value should be "test-correlation-id"

  Scenario: User ID context variable can be set and retrieved
    Given the user ID context variable
    When I set the value to "test-user-id"
    Then the retrieved value should be "test-user-id"
