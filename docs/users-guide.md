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

### Header retrieval and trusted source behaviour

During `process_request`, the middleware reads the configured header name and
checks whether the request originates from a trusted source. The correlation ID
stored on `req.context.correlation_id` is determined as follows:

1. If a valid header value is present, the request source is trusted, and the
   value passes validation (when a validator is configured), the incoming ID is
   accepted after trimming leading and trailing whitespace.

2. If a valid header value is present and the request source is trusted, but
   the value fails validation, the incoming ID is rejected and a new ID is
   generated. The validation failure is logged at `DEBUG` level.

3. If a valid header value is present but the request source is not trusted,
   the incoming ID is rejected and a new ID is generated using the configured
   generator. The validator is not called in this case.

4. If the header is missing, empty, or contains only whitespace, a new ID is
   generated using the configured generator.

When no validator is configured (the default), incoming IDs from trusted
sources are accepted without format checking, preserving backwards
compatibility.

This design ensures that every request receives a correlation ID for complete
traceability, while preventing untrusted clients from injecting arbitrary IDs
into the system.

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

A collection of IP addresses or Classless Inter-Domain Routing (CIDR) subnets
considered trusted. Correlation IDs will only be accepted from requests
originating from these addresses.

- **Type**: `Iterable[str] | None`
- **Default**: `None` (no sources trusted)

Both exact IP addresses and CIDR subnet notation are supported:

```python
middleware = CorrelationIDMiddleware(
    trusted_sources=[
        "127.0.0.1",           # Exact IPv4 address
        "10.0.0.0/8",          # IPv4 CIDR subnet
        "192.168.1.0/24",      # Another IPv4 subnet
        "::1",                 # Exact IPv6 address
        "2001:db8::/32",       # IPv6 CIDR subnet
    ]
)
```

**Important notes:**

- IP addresses and CIDR notations are validated at configuration time. Invalid
  formats will raise `ValueError`.
- CIDR notation must specify network addresses, not host addresses. For example,
  `10.0.0.0/24` is valid, but `10.0.0.5/24` will raise an error because it has
  host bits set.
- An empty or unspecified `trusted_sources` means no sources are trusted, and
  all incoming IDs are rejected. New IDs will be generated for every request.

**Security note**: Only add IP addresses that are fully trusted to propagate
correlation IDs. Misconfiguration could allow malicious actors to inject
arbitrary IDs.

### generator

A callable that generates new correlation IDs. Must take no arguments and
return a string.

- **Type**: `Callable[[], str] | None`
- **Default**: `default_uuid7_generator` (returns UUIDv7 hex strings via
  `uuid.uuid7()` when available, otherwise `uuid-utils`)

```python
import uuid

def custom_generator() -> str:
    return f"req-{uuid.uuid4().hex[:8]}"

middleware = CorrelationIDMiddleware(generator=custom_generator)
```

### validator

An optional callable that validates incoming correlation IDs during request
processing. Takes a string and returns `True` if the ID is valid, `False`
otherwise. When a validator is configured, incoming IDs from trusted sources
are checked before acceptance. Invalid IDs are discarded, a new ID is
generated, and the failure is logged at `DEBUG` level.

- **Type**: `Callable[[str], bool] | None`
- **Default**: `None` (no validation beyond trust checking)

When no validator is configured, incoming IDs from trusted sources are accepted
without format checking. This maintains backwards compatibility.

The library provides `default_uuid_validator` as a ready-to-use validator that
accepts any standard UUID format (versions 1-8), both hyphenated
(`xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`) and hex-only (32 characters). It is
case-insensitive and rejects empty, malformed, or excessively long strings.

```python
from falcon_correlate import CorrelationIDMiddleware, default_uuid_validator

# Use the built-in UUID validator
middleware = CorrelationIDMiddleware(validator=default_uuid_validator)
```

For custom validation requirements, a custom validator function can be provided:

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

**Logging note**: When an incoming ID fails validation, the middleware logs a
`DEBUG`-level message. The rejected value is not included in the log to avoid
log injection and privacy risks. To see these messages, configure logging to
capture `DEBUG` output from the `falcon_correlate.middleware` logger.

## Context Variables

The middleware provides two `contextvars.ContextVar` instances for
request-scoped storage. These variables make the correlation ID and user ID
available throughout the application — including code that does not have access
to Falcon's `req` object, such as logging filters, utility functions, and
downstream service clients.

### correlation_id_var

A context variable for the current request's correlation ID.

- **Type**: `contextvars.ContextVar[str | None]`
- **Default**: `None`

```python
from falcon_correlate import correlation_id_var

# Retrieve the current correlation ID (None if not set)
cid = correlation_id_var.get()
```

### user_id_var

A context variable for the current request's authenticated user ID.

- **Type**: `contextvars.ContextVar[str | None]`
- **Default**: `None`

```python
from falcon_correlate import user_id_var

# Retrieve the current user ID (None if not set)
uid = user_id_var.get()
```

**Note**: `correlation_id_var` lifecycle is managed automatically by the
middleware. It is set during `process_request` and reset during
`process_response`, including request-failure paths. The `user_id_var` is
intended for use by authentication middleware or application code that
identifies the current user.

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

The following functionality is now implemented:

- Middleware configuration options (header name, generator, validator, etc.).
- Header retrieval and whitespace normalization.
- Trusted source IP/CIDR matching.
- Default UUIDv7 generator implementation.
- Automatic correlation ID generation for requests without valid incoming IDs.
- Custom generator injection support.
- Default UUID validator for incoming ID format validation.
- Validation integration into request processing: incoming IDs from trusted
  sources are validated (when a validator is configured) before acceptance,
  with `DEBUG`-level logging of failures.
- Context variables (`correlation_id_var` and `user_id_var`) for
  request-scoped storage via `contextvars`.
- Correlation ID context variable lifecycle management: `correlation_id_var` is
  set during request processing and reset during response cleanup.

The following functionality will be added in future releases:

- `req.context` and `contextvars` parity guidance (task 2.4.3).
- Logging integration (task 3.1).

See the [roadmap](roadmap.md) for the full implementation plan.
