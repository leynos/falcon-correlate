Feature: httpx correlation ID propagation
  As a developer using falcon-correlate
  I want wrapper functions for httpx that propagate the correlation ID
  So that downstream services receive the correlation ID automatically

  Scenario: Wrapper injects correlation ID header
    Given the correlation ID is set to "bdd-cid-001"
    When I send a request using the correlation ID wrapper
    Then the outgoing request should contain header "X-Correlation-ID" with value "bdd-cid-001"

  Scenario: Wrapper preserves existing caller headers
    Given the correlation ID is set to "bdd-cid-002"
    When I send a request with existing header "Authorization" set to "Bearer token"
    Then the outgoing request should contain header "X-Correlation-ID" with value "bdd-cid-002"
    And the outgoing request should contain header "Authorization" with value "Bearer token"

  Scenario: Wrapper does not add header when context is empty
    Given no correlation ID is set
    When I send a request using the correlation ID wrapper
    Then the outgoing request should not contain header "X-Correlation-ID"

  Scenario: Async wrapper injects correlation ID header
    Given the correlation ID is set to "bdd-cid-003"
    When I send an async request using the correlation ID wrapper
    Then the outgoing request should contain header "X-Correlation-ID" with value "bdd-cid-003"
