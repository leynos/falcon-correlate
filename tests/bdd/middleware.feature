Feature: Correlation ID Middleware
  As a developer using Falcon
  I want to use the CorrelationIDMiddleware
  So that I can manage correlation IDs in my application

  Scenario: Middleware can be added to a Falcon application
    Given a new CorrelationIDMiddleware instance
    When I create a Falcon application with the middleware
    Then the application should be created successfully

  Scenario: Request processing completes without error
    Given a Falcon application with CorrelationIDMiddleware
    And a simple resource at "/hello"
    When I make a GET request to "/hello"
    Then the request should complete successfully

  Scenario: Response processing completes without error
    Given a Falcon application with CorrelationIDMiddleware
    And a simple resource at "/hello"
    When I make a GET request to "/hello"
    Then the response should be returned
    And process_response should have been called

  Scenario: Correlation ID header is captured
    Given a Falcon application with CorrelationIDMiddleware
    And a correlation echo resource at "/correlation"
    When I request "/correlation" with header "X-Correlation-ID" value "cid-123"
    Then the response correlation id should be "cid-123"

  Scenario: Missing correlation ID header triggers generation
    Given a Falcon application with CorrelationIDMiddleware
    And a correlation echo resource at "/correlation"
    When I make a GET request to "/correlation"
    Then a correlation ID should be generated

  # Configuration scenarios

  Scenario: Middleware accepts custom header name
    Given a CorrelationIDMiddleware with header_name "X-Request-ID"
    Then the middleware should use "X-Request-ID" as the header name

  Scenario: Middleware accepts trusted sources configuration
    Given a CorrelationIDMiddleware with trusted_sources "127.0.0.1,10.0.0.1"
    Then the middleware should have 2 trusted sources

  Scenario: Middleware accepts custom generator
    Given a custom ID generator that returns "custom-id-123"
    And a CorrelationIDMiddleware with that generator
    Then the middleware should use the custom generator

  Scenario: Middleware accepts custom validator
    Given a custom validator that accepts any string
    And a CorrelationIDMiddleware with that validator
    Then the middleware should use the custom validator

  Scenario: Middleware can disable response header echoing
    Given a CorrelationIDMiddleware with echo_header_in_response disabled
    Then the middleware should have echo_header_in_response set to False

  # Trusted source scenarios

  Scenario: Incoming ID accepted from trusted source
    Given a Falcon application with CorrelationIDMiddleware trusting "127.0.0.1"
    And a correlation echo resource at "/correlation"
    When I request "/correlation" with header "X-Correlation-ID" value "trusted-id"
    Then the response correlation id should be "trusted-id"

  Scenario: Incoming ID rejected from untrusted source triggers generation
    Given a Falcon application with CorrelationIDMiddleware trusting "10.0.0.1"
    And a correlation echo resource at "/correlation"
    When I request "/correlation" with header "X-Correlation-ID" value "untrusted-id"
    Then a correlation ID should be generated
    And the correlation ID should not be "untrusted-id"

  Scenario: CIDR subnet matching accepts incoming ID
    Given a Falcon application with CorrelationIDMiddleware trusting "127.0.0.0/8"
    And a correlation echo resource at "/correlation"
    When I request "/correlation" with header "X-Correlation-ID" value "cidr-id"
    Then the response correlation id should be "cidr-id"

  Scenario: Missing header triggers generation even from trusted source
    Given a Falcon application with CorrelationIDMiddleware trusting "127.0.0.1"
    And a correlation echo resource at "/correlation"
    When I make a GET request to "/correlation"
    Then a correlation ID should be generated

  # Generator invocation scenarios

  Scenario: Custom generator output is used for request
    Given a custom ID generator that returns "custom-generated-id"
    And a Falcon application with that custom generator
    And a correlation echo resource at "/correlation"
    When I make a GET request to "/correlation"
    Then the response correlation id should be "custom-generated-id"

  Scenario: Default generator produces valid UUIDv7
    Given a Falcon application with CorrelationIDMiddleware
    And a correlation echo resource at "/correlation"
    When I make a GET request to "/correlation"
    Then the correlation ID should be a valid UUIDv7

  # Validation scenarios

  Scenario: Invalid ID from trusted source triggers new generation
    Given a Falcon application with CorrelationIDMiddleware trusting "127.0.0.1" and a rejecting validator
    And a correlation echo resource at "/correlation"
    When I request "/correlation" with header "X-Correlation-ID" value "bad-format"
    Then a correlation ID should be generated
    And the correlation ID should not be "bad-format"

  Scenario: Valid ID from trusted source is accepted after validation
    Given a Falcon application with CorrelationIDMiddleware trusting "127.0.0.1" and an accepting validator
    And a correlation echo resource at "/correlation"
    When I request "/correlation" with header "X-Correlation-ID" value "valid-id"
    Then the response correlation id should be "valid-id"

  Scenario: No validator configured accepts any ID from trusted source
    Given a Falcon application with CorrelationIDMiddleware trusting "127.0.0.1"
    And a correlation echo resource at "/correlation"
    When I request "/correlation" with header "X-Correlation-ID" value "any-string-no-validation"
    Then the response correlation id should be "any-string-no-validation"

  Scenario: Custom validator is called for incoming IDs
    Given a custom validator that rejects IDs starting with "bad"
    And a Falcon application with that validator trusting "127.0.0.1"
    And a correlation echo resource at "/correlation"
    When I request "/correlation" with header "X-Correlation-ID" value "bad-id"
    Then a correlation ID should be generated
    And the correlation ID should not be "bad-id"
