Feature: Correlation ID access via req.context
  As a developer using falcon-correlate middleware
  I want to access the correlation ID via req.context.correlation_id
  So that I have a convenient alternative to correlation_id_var.get()
  and both methods always return the same value

  Scenario: req.context and contextvar return the same generated ID
    Given a Falcon application with req.context parity support
    When I request "/req-context" without a correlation ID header
    Then req.context.correlation_id and contextvar should match
    And both values should be non-empty

  Scenario: req.context and contextvar return the same trusted incoming ID
    Given a Falcon application with req.context parity support
    When I request "/req-context" with correlation ID "incoming-456"
    Then req.context.correlation_id should be "incoming-456"
    And the contextvar value should be "incoming-456"

  Scenario: Dual access parity with concurrent requests
    Given a Falcon application with concurrent req.context parity support
    When I send concurrent req-context requests with IDs "rc-a" and "rc-b"
    Then each req-context response should confirm parity
