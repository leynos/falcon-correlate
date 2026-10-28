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

  Scenario Outline: A transport injects a custom correlation header
    Given a <mode> Falcon app with a trusted source and HTTPX recording transport configured with header "X-Alt-CID"
    When I dispatch an inbound Falcon request with correlation ID "bdd-custom-cid"
    Then the recording transport should receive header "X-Alt-CID" with value "bdd-custom-cid"
    And the recording transport should not receive header "X-Correlation-ID"

    Examples:
      | mode  |
      | sync  |
      | async |

  Scenario Outline: A transport preserves an existing correlation header
    Given a <mode> Falcon app with a trusted source and HTTPX recording transport configured with header "<configured_header>" and existing header "<caller_header>" set to "<caller_value>"
    When I dispatch an inbound Falcon request with correlation ID "context-cid"
    Then the recording transport should receive header "<configured_header>" with value "<caller_value>"

    Examples:
      | mode  | configured_header | caller_header    | caller_value |
      | sync  | X-Correlation-ID  | X-Correlation-ID | caller-cid   |
      | async | X-Correlation-ID  | X-Correlation-ID | caller-cid   |
      | sync  | X-Alt-CID         | X-Alt-CID        | caller-cid   |
      | async | X-Alt-CID         | X-Alt-CID        | caller-cid   |
      | sync  | X-Alt-CID         | x-alt-cid        | caller-cid   |
      | async | X-Alt-CID         | x-alt-cid        | caller-cid   |
