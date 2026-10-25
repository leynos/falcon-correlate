Feature: HTTPX transport propagation through Falcon middleware
  As a developer using falcon-correlate
  I want reusable HTTPX transports to use the inbound correlation ID
  So that shared clients send the ID selected by Falcon middleware

  Scenario Outline: A trusted inbound ID reaches the <mode> recording transport
    Given a <mode> Falcon app with a trusted source and HTTPX recording transport
    When I dispatch an inbound Falcon request with correlation ID "<correlation_id>"
    Then the recording transport should receive header "X-Correlation-ID" with value "<correlation_id>"

    Examples:
      | mode  | correlation_id        |
      | sync  | trusted-transport-sync |
      | async | trusted-transport-async |
