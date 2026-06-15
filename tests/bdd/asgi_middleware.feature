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
    And the ASGI ambient correlation ID context should be cleared

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
    And the ASGI ambient correlation ID context should be cleared

  Scenario: Concurrent ASGI requests keep context variables isolated
    Given a Falcon ASGI application with CorrelationIDMiddlewareASGI trusting "127.0.0.1"
    And an interleaved ASGI correlation resource expecting 2 requests at "/correlation"
    When I make concurrent ASGI GET requests to "/correlation" with correlation IDs "cid-a" and "cid-b"
    Then each ASGI concurrent response should observe its own correlation id
    And each ASGI concurrent response header should match its own correlation id
    And the ASGI ambient correlation ID context should be cleared
