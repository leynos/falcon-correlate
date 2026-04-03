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

## Accessing the correlation ID

The middleware provides two ways to access the current request's correlation
ID. Both methods always return the same value for the duration of a request,
because the middleware sets them from the same source in `process_request`.

### Via `req.context.correlation_id`

Within Falcon responders, hooks, and any code that has access to the `req`
object, the correlation ID is available directly on the request context:

```python
class MyResource:
    def on_get(self, req, resp):
        cid = req.context.correlation_id
        resp.media = {"correlation_id": cid}
```

This is the simplest approach when `req` is already in scope.

### Via `correlation_id_var.get()`

In code that does not have access to the Falcon `req` object — such as logging
filters, utility functions, and downstream service clients — use the context
variable instead:

```python
from falcon_correlate import correlation_id_var


def build_downstream_headers():
    cid = correlation_id_var.get()
    if cid is not None:
        return {"X-Correlation-ID": cid}
    return {}
```

### When to use each method

| Method                       | Use when                                                                                                                    |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `req.context.correlation_id` | Code already has access to the Falcon `req` object (responders, hooks, middleware). Simpler and more explicit.              |
| `correlation_id_var.get()`   | Code does not have access to `req` (logging filters, utility functions, service clients, Celery tasks). Framework-agnostic. |

Both methods are kept in sync by the middleware. There is no need to choose one
exclusively — use whichever is most convenient for the call site.

### echo_header_in_response

Whether to include the correlation ID in response headers.

- **Type**: `bool`
- **Default**: `True`

```python
# Disable echoing correlation ID in responses
middleware = CorrelationIDMiddleware(echo_header_in_response=False)
```

## Logging integration

The library provides `ContextualLogFilter`, a `logging.Filter` subclass that
automatically injects the current correlation ID and user ID into log records.
This allows standard `logging.Formatter` format strings to include
`%(correlation_id)s` and `%(user_id)s` without any manual per-call effort.

When a context variable is not set (for example, outside a request), the
placeholder string `"-"` is used instead.  If the record already carries the
attribute (e.g. attached via `extra=` or a `LoggerAdapter`), the existing value
is preserved and the filter does not overwrite it.

### Basic usage

Attach the filter to a handler or logger:

```python
import logging
from falcon_correlate import ContextualLogFilter

handler = logging.StreamHandler()
handler.addFilter(ContextualLogFilter())
handler.setFormatter(
    logging.Formatter(
        "%(asctime)s [%(correlation_id)s] [%(user_id)s] "
        "%(name)s - %(message)s"
    )
)

logger = logging.getLogger("myapp")
logger.addHandler(handler)
logger.setLevel(logging.INFO)
```

### Recommended format string

The library exports `RECOMMENDED_LOG_FORMAT`, a ready-made format string that
includes a timestamp, log level, correlation ID, user ID, logger name, and
message:

```python
from falcon_correlate import RECOMMENDED_LOG_FORMAT

# Value:
# "%(asctime)s - [%(levelname)s] - [%(correlation_id)s] - "
# "[%(user_id)s] - %(name)s - %(message)s"
```

This produces output like:

```plaintext
2026-02-25 14:30:00,123 - [INFO] - [abc123] - [user42] - myapp - Handling request
```

Use it with a handler:

```python
import logging
from falcon_correlate import ContextualLogFilter, RECOMMENDED_LOG_FORMAT

handler = logging.StreamHandler()
handler.addFilter(ContextualLogFilter())
handler.setFormatter(logging.Formatter(RECOMMENDED_LOG_FORMAT))

logger = logging.getLogger("myapp")
logger.addHandler(handler)
logger.setLevel(logging.INFO)
```

The constant is provided as a convenience; callers may supply a custom format
string if the recommended layout does not suit their needs.

### Using `dictConfig`

For applications that configure logging via `logging.config.dictConfig`, the
filter can be referenced by its dotted path:

```python
import logging.config

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "contextual": {
            "()": "falcon_correlate.ContextualLogFilter",
        },
    },
    "formatters": {
        "standard": {
            "format": (
                "%(asctime)s [%(levelname)s] [%(correlation_id)s] "
                "[%(user_id)s] %(name)s: %(message)s"
            ),
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "filters": ["contextual"],
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}

logging.config.dictConfig(LOGGING_CONFIG)
```

### Placeholder behaviour

When the correlation ID or user ID context variable is not set, the filter
substitutes the string `"-"` on the log record. This ensures that format
strings referencing `%(correlation_id)s` or `%(user_id)s` never raise a
`KeyError` and produce clean output even outside request handling:

```plaintext
2026-02-23 12:00:00 [INFO] [-] [-] myapp: Application started
2026-02-23 12:00:01 [INFO] [abc123] [user42] myapp: Handling request
```

### Preserving explicit metadata

The filter only fills in attributes that are **missing** from the record. If a
caller already attached `correlation_id` or `user_id` via `extra=` or a
`LoggerAdapter`, the filter preserves those values.  This is useful for
background jobs or other non-request code paths that want to supply their own
traceability IDs:

```python
logger.info(
    "Running background job",
    extra={"correlation_id": "job-abc-123"},
)
# The filter will NOT overwrite "job-abc-123" with the contextvar
# value (or the "-" placeholder).
```

## Structlog integration

For applications using [structlog](https://www.structlog.org/) for structured
logging, the correlation ID and user ID context variables can be included in
structured log output without any additional library code.

### How it works

The `falcon-correlate` middleware stores the correlation ID and user ID in
standard `contextvars.ContextVar` instances (`correlation_id_var` and
`user_id_var`). Structlog provides a `merge_contextvars` processor that merges
context variables into the log event dictionary, but this processor only picks
up variables bound via `structlog.contextvars.bind_contextvars()` — it does not
automatically read arbitrary `ContextVar` instances such as
`correlation_id_var` and `user_id_var`.

To bridge this gap, a small custom processor can be added to the structlog
configuration that reads directly from `falcon-correlate`'s context variables.

### Custom processor (recommended)

Define a processor function that reads from the library's context variables and
adds them to the structlog event dictionary:

```python
from falcon_correlate import correlation_id_var, user_id_var


def inject_correlation_context(
    logger: object,
    method_name: str,
    event_dict: dict[str, object],
) -> dict[str, object]:
    """Inject correlation ID and user ID into structlog event dict."""
    event_dict.setdefault("correlation_id", correlation_id_var.get() or "-")
    event_dict.setdefault("user_id", user_id_var.get() or "-")
    return event_dict
```

Then include it in the structlog processor chain at application startup:

```python
import structlog

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,  # optional, see note below
        inject_correlation_context,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    logger_factory=structlog.PrintLoggerFactory(),
)
```

`merge_contextvars` is not required by `inject_correlation_context` — the
custom processor reads directly from `falcon-correlate`'s context variables.
However, including `merge_contextvars` allows any additional values bound via
`structlog.contextvars.bind_contextvars()` elsewhere in the application to
appear in the log output as well. It can safely be omitted if that capability
is not needed.

This produces structured output like:

```plaintext
2026-02-27T12:00:00Z [info     ] Handling request    correlation_id=abc123 user_id=user42
```

The processor uses `setdefault` so that values explicitly bound via
`structlog.contextvars.bind_contextvars()` or passed as keyword arguments to
the logger are preserved, matching the "fill, don't overwrite" behaviour of
`ContextualLogFilter`.

### Alternative: `bind_contextvars` in middleware

As an alternative to the custom processor, the context variables can be bridged
by calling `structlog.contextvars.bind_contextvars()` in a second Falcon
middleware that runs after `CorrelationIDMiddleware`:

```python
import structlog
from falcon_correlate import correlation_id_var, user_id_var


class StructlogContextMiddleware:
    """Bridge falcon-correlate context variables into structlog."""

    def process_request(self, req, resp):
        cid = correlation_id_var.get()
        uid = user_id_var.get()
        structlog.contextvars.bind_contextvars(
            correlation_id=cid or "-",
            user_id=uid or "-",
        )

    def process_response(self, req, resp, resource, req_succeeded):
        structlog.contextvars.clear_contextvars()
```

This approach works with `structlog.contextvars.merge_contextvars()` in the
processor chain without needing a custom processor. However, the custom
processor approach above is preferred because it requires no additional
middleware and no per-request bridging calls.

### Note on `merge_contextvars`

`structlog.contextvars.merge_contextvars()` only merges context variables bound
via `structlog.contextvars.bind_contextvars()`. It does not automatically pick
up arbitrary `contextvars.ContextVar` instances such as `correlation_id_var`
and `user_id_var`. This is why a bridging step — either the custom processor or
the middleware approach above — is required.

## httpx propagation

When making outgoing HTTP calls to downstream services, the correlation ID
should be propagated so that the entire request chain can be traced. The
library provides both wrapper functions and reusable transports for `httpx`
that handle this automatically.

**Note**: `httpx` is an optional dependency. Install it separately:

```bash
pip install httpx
```

### Choosing an approach

Use the wrapper functions when requests are made ad hoc and the call site
already controls the `httpx.request(...)` invocation. Use the transport classes
when the application relies on shared `httpx.Client` or `httpx.AsyncClient`
instances and wants correlation header injection to happen transparently for
every request sent through that client.

### Synchronous wrapper usage

Use `request_with_correlation_id` as a drop-in replacement for `httpx.request`:

```python
from falcon_correlate import request_with_correlation_id

# The correlation ID header is injected automatically
# when correlation_id_var is set (e.g. during a Falcon request).
response = request_with_correlation_id(
    "GET", "https://api.example.com/data"
)
```

All keyword arguments are passed through to `httpx.request`:

```python
response = request_with_correlation_id(
    "POST",
    "https://api.example.com/submit",
    json={"key": "value"},
    headers={"Authorization": "Bearer token"},
    timeout=10,
)
```

### Asynchronous wrapper usage

Use `async_request_with_correlation_id` for async code:

```python
from falcon_correlate import async_request_with_correlation_id

response = await async_request_with_correlation_id(
    "GET", "https://api.example.com/data"
)
```

The async variant creates a temporary `httpx.AsyncClient` for each call.

### Transport usage with shared clients

Use `CorrelationIDTransport` for a reusable synchronous client:

```python
import httpx
from falcon_correlate import CorrelationIDTransport

base_transport = httpx.HTTPTransport()

with httpx.Client(
    transport=CorrelationIDTransport(base_transport)
) as client:
    response = client.get("https://api.example.com/data")
```

Use `AsyncCorrelationIDTransport` for a reusable async client:

```python
import httpx
from falcon_correlate import AsyncCorrelationIDTransport

base_transport = httpx.AsyncHTTPTransport()

async with httpx.AsyncClient(
    transport=AsyncCorrelationIDTransport(base_transport)
) as client:
    response = await client.get("https://api.example.com/data")
```

The transport classes preserve an explicitly supplied correlation header on the
outgoing request. If the caller already set `X-Correlation-ID`,
`falcon-correlate` leaves that value unchanged.

### HTTP client behaviour

- When `correlation_id_var` is set (i.e. during a Falcon request handled
  by `CorrelationIDMiddleware`), the `X-Correlation-ID` header is added to the
  outgoing request.
- When `correlation_id_var` is not set (e.g. outside request handling),
  no header is added.
- Existing headers passed by the caller are always preserved. The correlation
  ID header is added alongside them, never replacing them.
- If the caller explicitly sets the correlation header itself, both the wrapper
  functions and the transport classes keep the caller's value.

## Celery propagation

When Falcon request-handling code publishes Celery tasks, the current
correlation ID can be copied into the outgoing task message's Advanced Message
Queuing Protocol (AMQP) `correlation_id` property.

**Note**: Celery is an optional dependency. Install the package with the Celery
extra in any process that publishes tasks:

```bash
pip install "falcon-correlate[celery]"
```

### Enabling the publish signal handler

Importing `falcon_correlate` registers the Celery `before_task_publish` handler
automatically when Celery is installed. If the publisher process already
imports anything from the package root, no extra registration call is needed.

```python
from celery import Celery
from falcon_correlate import CorrelationIDMiddleware

celery_app = Celery("myapp", broker="redis://localhost:6379/0")
middleware = CorrelationIDMiddleware()
```

Once the package is imported in the publisher process, normal task publishing
APIs such as `delay()` and `apply_async()` propagate the request correlation ID
automatically.

```python
from falcon_correlate import correlation_id_var


def enqueue_invoice_email(user_id: str) -> None:
    # During request handling, CorrelationIDMiddleware has already populated
    # correlation_id_var for the current context.
    send_invoice_email.delay(user_id)
    assert correlation_id_var.get() is not None
```

### Behaviour

- When `correlation_id_var` is set and the active Celery result backend is not
  `rpc://`, the outgoing Celery message uses that value as its publish-time
  `correlation_id`.
- When `correlation_id_var` is not set, `falcon-correlate` leaves Celery's
  generated publish value unchanged.
- If the caller passes `apply_async(correlation_id=...)` while a request
  correlation ID is present, the ambient request value wins. Celery already
  fills `correlation_id` by default, so overwriting the publish value is the
  only way to guarantee request-to-task propagation through
  `before_task_publish`.
- If the active Celery result backend is `rpc://`, `falcon-correlate`
  preserves Celery's task-id correlation contract and does not overwrite the
  publish `correlation_id`.
- This release covers only the publish path. Worker-side setup and cleanup of
  `correlation_id_var` inside Celery tasks will be added separately.

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
- Dual access to the correlation ID via `req.context.correlation_id` and
  `correlation_id_var.get()`, both always in sync during request handling.
- `ContextualLogFilter` for injecting correlation ID and user ID into standard
  library log records, with `"-"` placeholder when context is not set.
  Pre-existing record attributes (e.g. from `extra=`) are preserved.
- `RECOMMENDED_LOG_FORMAT` constant providing a ready-made format string for
  use with `logging.Formatter` or `dictConfig`.
- Structlog integration documentation with custom processor and
  `bind_contextvars` bridging approaches (task 3.2).
- httpx propagation wrapper functions (`request_with_correlation_id` and
  `async_request_with_correlation_id`) for injecting the correlation ID into
  outgoing HTTP requests (task 4.1.1).
- httpx transport classes (`CorrelationIDTransport` and
  `AsyncCorrelationIDTransport`) for shared client configuration that injects
  the correlation ID into outgoing HTTP requests (task 4.1.2).
- Celery publish propagation via `propagate_correlation_id_to_celery`, which
  injects the ambient request correlation ID into outgoing task message
  properties (task 4.2.1).

See the [roadmap](roadmap.md) for the full implementation plan.
