Feature: Quickstart guide examples

  Scenario: A generated correlation ID is attached to the response
    Given a Falcon app built from the quickstart minimal example
    When I request "/hello" without a correlation ID header
    Then the response status should be 200
    And the response should include a valid correlation ID header

  Scenario: A trusted incoming correlation ID is echoed
    Given a Falcon app built from the quickstart configured example
    When I request "/hello" with header "X-Correlation-ID" value "cid-quickstart-1"
    Then the response correlation ID header should be "cid-quickstart-1"

  Scenario: An untrusted incoming correlation ID is replaced
    Given a Falcon app from the configured example with no trusted sources
    When I request "/hello" with header "X-Correlation-ID" value "cid-untrusted"
    Then the response correlation ID header should not be "cid-untrusted"
    And the response should include a valid correlation ID header

  Scenario: The correlation ID appears in a log line
    Given the quickstart logging configuration
    And the correlation ID is set to "cid-log-1"
    When the example emits a log message "hello from quickstart"
    Then the log output should contain "cid-log-1"
    And the log output should contain "hello from quickstart"
