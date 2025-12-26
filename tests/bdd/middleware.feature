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
