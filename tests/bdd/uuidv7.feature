Feature: Default UUIDv7 generator
  As a developer using falcon-correlate
  I want a default UUIDv7 generator
  So that correlation IDs are RFC 9562 compliant

  Scenario: Default generator returns a UUIDv7 hex string
    Given the default UUIDv7 generator
    When I generate a correlation ID
    Then the correlation ID should be a UUIDv7 hex string

  Scenario: Default generator returns unique values
    Given the default UUIDv7 generator
    When I generate two correlation IDs
    Then the correlation IDs should be different
