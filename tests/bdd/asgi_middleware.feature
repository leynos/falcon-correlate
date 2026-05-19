Feature: ASGI Correlation ID Middleware
  As a developer using Falcon ASGI
  I want to use the CorrelationIDMiddlewareASGI
  So that I can manage correlation IDs in an ASGI application

  Scenario: ASGI application exposes and echoes a trusted correlation ID
    Given a Falcon ASGI application with CorrelationIDMiddlewareASGI trusting "127.0.0.1"
    And an ASGI correlation echo resource at "/correlation"
    When I make an ASGI GET request to "/correlation" with header "X-Correlation-ID" value "trusted-asgi"
    Then the ASGI response should complete successfully
    And the ASGI resource should observe correlation id "trusted-asgi"
    And the ASGI response header "X-Correlation-ID" should be "trusted-asgi"

  Scenario: ASGI application rejects an untrusted incoming correlation ID
    Given a Falcon ASGI application with CorrelationIDMiddlewareASGI trusting "10.0.0.1" and generator "generated-asgi"
    And an ASGI correlation echo resource at "/correlation"
    When I make an ASGI GET request to "/correlation" with header "X-Correlation-ID" value "untrusted-asgi"
    Then the ASGI response should complete successfully
    And the ASGI resource should observe correlation id "generated-asgi"
    And the ASGI response header "X-Correlation-ID" should be "generated-asgi"

  Scenario: ASGI application regenerates when validation rejects an incoming correlation ID
    Given a Falcon ASGI application with CorrelationIDMiddlewareASGI trusting "127.0.0.1", generator "generated-asgi", and a rejecting validator
    And an ASGI correlation echo resource at "/correlation"
    When I make an ASGI GET request to "/correlation" with header "X-Correlation-ID" value "invalid-asgi"
    Then the ASGI response should complete successfully
    And the ASGI resource should observe correlation id "generated-asgi"
    And the ASGI response header "X-Correlation-ID" should be "generated-asgi"

  Scenario: ASGI application generates a correlation ID when the request header is missing
    Given a Falcon ASGI application with CorrelationIDMiddlewareASGI trusting "127.0.0.1" and generator "generated-asgi"
    And an ASGI correlation echo resource at "/correlation"
    When I make an ASGI GET request to "/correlation"
    Then the ASGI response should complete successfully
    And the ASGI resource should observe correlation id "generated-asgi"
    And the ASGI response header "X-Correlation-ID" should be "generated-asgi"

  Scenario: ASGI application can disable response header echoing
    Given a Falcon ASGI application with CorrelationIDMiddlewareASGI generator "generated-asgi" and response echo disabled
    And an ASGI correlation echo resource at "/correlation"
    When I make an ASGI GET request to "/correlation"
    Then the ASGI response should complete successfully
    And the ASGI resource should observe correlation id "generated-asgi"
    And the ASGI response header "X-Correlation-ID" should be absent
