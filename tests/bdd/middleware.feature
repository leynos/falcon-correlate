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

  Scenario: Missing correlation ID header yields no context
    Given a Falcon application with CorrelationIDMiddleware
    And a correlation echo resource at "/correlation"
    When I make a GET request to "/correlation"
    Then the response should not include a correlation ID

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

  Scenario: Incoming ID rejected from untrusted source
    Given a Falcon application with CorrelationIDMiddleware trusting "10.0.0.1"
    And a correlation echo resource at "/correlation"
    When I request "/correlation" with header "X-Correlation-ID" value "untrusted-id"
    Then the response should not include a correlation ID

  Scenario: CIDR subnet matching accepts incoming ID
    Given a Falcon application with CorrelationIDMiddleware trusting "127.0.0.0/8"
    And a correlation echo resource at "/correlation"
    When I request "/correlation" with header "X-Correlation-ID" value "cidr-id"
    Then the response correlation id should be "cidr-id"

  Scenario: Missing header has no correlation ID even from trusted source
    Given a Falcon application with CorrelationIDMiddleware trusting "127.0.0.1"
    And a correlation echo resource at "/correlation"
    When I make a GET request to "/correlation"
    Then the response should not include a correlation ID
