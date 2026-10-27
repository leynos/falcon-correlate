Feature: HTTPX wrapper propagation through Falcon middleware
  As a developer using falcon-correlate
  I want outbound HTTPX wrapper calls to use the inbound correlation ID
  So that downstream services receive the ID selected by Falcon middleware

  Scenario Outline: A trusted inbound ID reaches the <mode> wrapper call
    Given a <mode> Falcon app with a trusted source and HTTPX wrapper
    When I dispatch an inbound Falcon request with correlation ID "<correlation_id>"
    Then the outgoing request should contain header "X-Correlation-ID" with value "<correlation_id>"

    Examples:
      | mode  | correlation_id       |
      | sync  | trusted-wrapper-sync  |
      | async | trusted-wrapper-async |

  Scenario Outline: A generated ID reaches the <mode> wrapper call and response
    Given a <mode> Falcon app with a generated ID "<correlation_id>" and HTTPX wrapper
    When I dispatch an inbound Falcon request without a correlation ID
    Then the outgoing request should contain header "X-Correlation-ID" with value "<correlation_id>"
    And the outbound correlation ID should match the echoed response header

    Examples:
      | mode  | correlation_id        |
      | sync  | generated-wrapper-sync |
      | async | generated-wrapper-async |
