Feature: Context variable lifecycle in middleware
  As a developer using falcon-correlate middleware
  I want correlation ID context state to be managed automatically
  So that request-scoped code can access it safely without leakage

  Scenario: Context variable is set during request handling
    Given a Falcon application with lifecycle middleware support
    When I request "/lifecycle" with correlation ID "cid-123"
    Then the resource should observe context variable value "cid-123"

  Scenario: Context variable is cleared after response
    Given a Falcon application with lifecycle middleware support
    When I request "/lifecycle" with correlation ID "cid-123"
    Then the correlation ID context variable should be cleared

  Scenario: Context isolation between concurrent requests
    Given a Falcon application with concurrent lifecycle middleware support
    When I send concurrent lifecycle requests with IDs "cid-a" and "cid-b"
    Then each lifecycle response should contain its own correlation ID
    And the correlation ID context variable should be cleared
