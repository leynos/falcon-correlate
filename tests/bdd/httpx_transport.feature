Feature: httpx transport correlation ID propagation
  As a developer using falcon-correlate
  I want reusable httpx transports that propagate the correlation ID
  So that shared clients send the current correlation header automatically

  Scenario: Sync client transport injects correlation ID header
    Given the correlation ID is set to "bdd-transport-cid-001"
    When I send a request using an httpx client with the correlation transport
    Then the outgoing request should contain header "X-Correlation-ID" with value "bdd-transport-cid-001"

  Scenario: Async client transport injects correlation ID header
    Given the correlation ID is set to "bdd-transport-cid-002"
    When I send an async request using an httpx client with the correlation transport
    Then the outgoing request should contain header "X-Correlation-ID" with value "bdd-transport-cid-002"

  Scenario: Transport leaves request unchanged when context is empty
    Given no correlation ID is set
    When I send a request using an httpx client with the correlation transport
    Then the outgoing request should not contain header "X-Correlation-ID"
