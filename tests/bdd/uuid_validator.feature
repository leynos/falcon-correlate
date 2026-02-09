Feature: Default UUID validator
  As a developer using falcon-correlate
  I want a default UUID validator
  So that malformed correlation IDs are rejected

  Scenario: Valid hyphenated UUID is accepted
    Given the default UUID validator
    When I validate "550e8400-e29b-41d4-a716-446655440000"
    Then the validation result should be True

  Scenario: Valid hex-only UUID is accepted
    Given the default UUID validator
    When I validate "550e8400e29b41d4a716446655440000"
    Then the validation result should be True

  Scenario: Empty string is rejected
    Given the default UUID validator
    When I validate an empty string
    Then the validation result should be False

  Scenario: Malformed string is rejected
    Given the default UUID validator
    When I validate "not-a-valid-uuid"
    Then the validation result should be False

  Scenario: Excessively long string is rejected
    Given the default UUID validator
    When I validate a string of 100 characters
    Then the validation result should be False
