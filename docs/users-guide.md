# falcon-correlate User's Guide

This guide provides instructions for using `falcon-correlate`, a correlation ID
middleware for the Falcon web framework.

## Installation

```bash
pip install falcon-correlate
```

## Quick Start

### Basic Usage

Add the `CorrelationIDMiddleware` to your Falcon application:

```python
import falcon
from falcon_correlate import CorrelationIDMiddleware

# Create the middleware instance
middleware = CorrelationIDMiddleware()

# Create your Falcon app with the middleware
app = falcon.App(middleware=[middleware])


# Define your resources
class HelloResource:
    def on_get(self, req, resp):
        resp.media = {"message": "Hello, World!"}


# Add routes
app.add_route("/hello", HelloResource())
```

### How It Works

The middleware provides two hook points in the request/response lifecycle:

1. **`process_request(req, resp)`**: Called before routing the request to a
   resource. This is where the correlation ID will be retrieved from incoming
   headers or generated.

2. **`process_response(req, resp, resource, req_succeeded)`**: Called after the
   resource responder has been invoked. This is where the correlation ID will
   be added to response headers and any cleanup will be performed.

## Configuration Options

The middleware accepts several configuration options as keyword-only arguments:

### header_name

The HTTP header name used for incoming and outgoing correlation IDs.

- **Type**: `str`
- **Default**: `"X-Correlation-ID"`

```python
middleware = CorrelationIDMiddleware(header_name="X-Request-ID")
```

### trusted_sources

A sequence of IP addresses considered trusted. Correlation IDs will only be
accepted from requests originating from these addresses. Requests from
untrusted sources will have new IDs generated regardless of any incoming header
value.

- **Type**: `Iterable[str] | None`
- **Default**: `None` (no sources trusted, all IDs are generated)

```python
middleware = CorrelationIDMiddleware(
    trusted_sources=["127.0.0.1", "10.0.0.1", "192.168.1.0/24"]
)
```

**Security note**: Only add IP addresses you fully trust to propagate
correlation IDs. Misconfiguration could allow malicious actors to inject
arbitrary IDs.

### generator

A callable that generates new correlation IDs. Must take no arguments and
return a string.

- **Type**: `Callable[[], str] | None`
- **Default**: `default_uuid7_generator` (generates UUIDv7 identifiers)

```python
import uuid

def custom_generator() -> str:
    return f"req-{uuid.uuid4().hex[:8]}"

middleware = CorrelationIDMiddleware(generator=custom_generator)
```

### validator

An optional callable that validates incoming correlation IDs. Takes a string
and returns `True` if the ID is valid, `False` otherwise. Invalid IDs are
discarded and new ones are generated.

- **Type**: `Callable[[str], bool] | None`
- **Default**: `None` (no validation beyond trust checking)

```python
import re

UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

def uuid_validator(value: str) -> bool:
    return bool(UUID_PATTERN.match(value))

middleware = CorrelationIDMiddleware(validator=uuid_validator)
```

### echo_header_in_response

Whether to include the correlation ID in response headers.

- **Type**: `bool`
- **Default**: `True`

```python
# Disable echoing correlation ID in responses
middleware = CorrelationIDMiddleware(echo_header_in_response=False)
```

## Full Configuration Example

```python
import falcon
from falcon_correlate import CorrelationIDMiddleware

def custom_generator() -> str:
    import uuid
    return str(uuid.uuid4())

def custom_validator(value: str) -> bool:
    # Accept any non-empty string up to 64 characters
    return bool(value) and len(value) <= 64

middleware = CorrelationIDMiddleware(
    header_name="X-Request-ID",
    trusted_sources=["10.0.0.0/8", "192.168.0.0/16"],
    generator=custom_generator,
    validator=custom_validator,
    echo_header_in_response=True,
)

app = falcon.App(middleware=[middleware])
```

## Current Status

The middleware configuration options are now implemented. The following
functionality will be added in future releases:

- Correlation ID retrieval from request headers (task 2.1)
- UUIDv7 generation for new correlation IDs (task 2.2)
- Trusted source IP matching including CIDR notation (task 2.1.2)
- Context variable storage (task 2.4)
- Logging integration (task 3.1)

See the [roadmap](roadmap.md) for the full implementation plan.
