# Design and implementation of a correlation ID middleware for the Falcon web framework

## 1. Introduction

### 1.1. Purpose and scope of the report

This report provides an expert-level design for a correlation ID middleware
specifically tailored for the Falcon web framework. The primary objective is to
establish a robust mechanism for generating, managing, and propagating
correlation IDs throughout the request lifecycle within a Falcon application
and across distributed services. The scope of this report encompasses:

- The retrieval of correlation IDs from incoming request headers or the
  generation of new identifiers if not present or if the source is untrusted.
- The integration of these correlation IDs into the application's logging
  infrastructure, alongside contextual information such as the currently
  authenticated user.
- Strategies for propagating the correlation ID to downstream HTTP services,
  with a focus on the `httpx` library, and to asynchronous task queues managed
  by Celery.
- A survey of existing literature and common practices in correlation ID
  management to inform the proposed design.

The design aims to be comprehensive, offering guidance on architecture,
implementation details, and operational considerations.

### 1.2. The imperative of correlation IDs in modern architectures

In contemporary software development, particularly with the prevalence of
microservice architectures and distributed systems, the complexity of tracing
individual requests or transactions has significantly increased. A single user
interaction may trigger a cascade of calls across numerous independent
services, each potentially generating its own logs and telemetry data. Without
a common identifier, diagnosing issues, understanding system behavior, or
performing end-to-end tracing becomes a formidable challenge.

Correlation IDs address this challenge by providing a unique identifier that is
attached to an initial request and then propagated consistently across all
services and components involved in processing that request. This "request
passport" creates a traceable thread through the distributed landscape. The
benefits are manifold:

- **Enhanced traceability:** Simplifies the tracking of a request's journey
  through multiple services.
- **Simplified debugging:** Allows developers and operators to quickly
  aggregate and filter logs from various sources pertinent to a specific
  transaction, dramatically reducing the mean time to resolution (MTTR) for
  issues.
- **Improved log analysis:** Facilitates more effective operational monitoring
  and analysis of request flows, performance bottlenecks, and error patterns.
- **Coherent operational view:** Provides a unified view of how different parts
  of a system interact to fulfil a request.

The transition from monolithic applications, where debugging paths were often
contained within a single codebase, to distributed systems has made correlation
IDs not merely a convenience but a foundational element for maintaining
observability and operational control.

### 1.3. Report structure overview

This report is structured to guide the reader from foundational concepts to a
detailed design and implementation strategy. Section 2 presents a literature
survey, examining the principles of correlation ID management and existing
solutions. Section 3 delves into the core design of the Falcon correlation ID
middleware, covering its architecture, ID lifecycle, contextual storage,
logging integration, and downstream propagation techniques. Section 4 provides
concrete implementation guidance and code examples for key components. Finally,
Section 5 offers a conclusion and recommendations for deployment and potential
future enhancements.

## 2. Literature survey: foundations of correlation ID management

A thorough understanding of existing practices and principles is essential
before designing a new correlation ID solution. This section surveys the
relevant literature and common approaches.

### 2.1. Core principles and benefits

A correlation ID is a unique identifier assigned to a request or a series of
related operations, allowing for the tracking and linking of activities across
different components or services in a distributed system. The fundamental
benefit is the ability to create a coherent narrative for a transaction as it
traverses various parts of an application. This is particularly crucial for log
correlation, which allows navigation to all logs belonging to a particular
trace, or vice-versa.[^1] By including the correlation ID in logs, it becomes
simple to retrieve all log entries generated from a single HTTP request or a
distributed transaction.[^2] This significantly aids in debugging, monitoring,
and understanding the flow of operations within complex systems.

### 2.2. Common header conventions for correlation IDs

For HTTP-based services, correlation IDs are typically transmitted via request
headers. While no single standard is universally mandated, several conventions
have emerged. The user query specifies `X-Correlation-ID`, which is a common
choice. Another widely used header is `X-Request-ID`.[^2] Organisations may
also define their own specific headers, such as `concur-correlationid` used by
SAP Concur[^4] or the `Kong-Request-ID` header added by the Kong API
gateway.[^5]

The existence of multiple common header names (e.g., `X-Correlation-ID`,
`X-Request-ID`) and organisation-specific headers suggests that while a de
facto standard around "X-Something-ID" has formed, the precise name can vary.
This implies that a robust middleware solution should ideally allow
configuration of the header name it inspects and propagates, even if it
defaults to a specific one like `X-Correlation-ID`. Consistency within a given
ecosystem of services is paramount for the effectiveness of correlation IDs.

### 2.3. UUIDv7 as a modern choice for identifiers

The choice of identifier format is crucial. Universally Unique Identifiers
(UUIDs) are commonly used. The user query specifies UUIDv7, a newer version of
the UUID standard. UUIDv7 is designed to be time-sortable, which is a
significant advantage.[^6] Its structure typically combines a Unix timestamp
(milliseconds since epoch) with random bits, ensuring both uniqueness and
chronological ordering when sorted lexicographically.[^6] This time-sortable
property is particularly beneficial for database indexing and querying logs
based on time ranges, potentially improving performance for such operations.[^6]

UUIDv7 offers precise timestamping, with the current draft RFC4122 specifying
millisecond precision by default.[^6] This contrasts with UUIDv4, which is
entirely random and thus offers no inherent time ordering. UUIDv1 is time-based
but has been criticised for potential privacy concerns due to the inclusion of
the MAC address of the generating machine[^6], and UUIDv7 aims to provide
better entropy characteristics than UUIDv1.[^7] The time-ordered nature of
UUIDv7, combined with its uniqueness properties, makes it an excellent
candidate for correlation IDs, especially in systems where IDs might be used as
database primary keys or frequently queried in a time-sensitive manner.

### 2.4. Survey of existing middleware and approaches in the Python ecosystem

Several libraries and patterns exist within the Python ecosystem for handling
correlation IDs. A notable example is `asgi-correlation-id`, a middleware
designed for ASGI frameworks like FastAPI and Starlette.[^2] Although Falcon
can operate in both WSGI and ASGI modes, the feature set of
`asgi-correlation-id` provides a valuable reference. Its capabilities include
reading correlation IDs from headers (configurable, defaulting to
`X-Request-ID`), generating new UUIDs if no ID is found, providing a logging
filter to inject the ID into log records, and offering support for propagating
IDs to Celery tasks.[^2]

Application Performance Monitoring (APM) tools, such as Elastic APM, also
employ similar concepts by injecting trace and transaction IDs into logs to
enable correlation between application logs and performance traces.[^1] These
IDs serve a purpose analogous to correlation IDs for observability.

The `asgi-correlation-id` library, despite its ASGI focus, serves as a strong
conceptual blueprint for the Falcon middleware. Its comprehensive feature
set—configurable header names, customisable ID generators and validators,
logging integration, and Celery support—aligns closely with the requirements
outlined in the user query. Therefore, its design patterns and capabilities can
inform the development of a similar middleware for Falcon, adapted to Falcon's
specific middleware API and operational modes.

### 2.5. Disambiguation: Falcon web framework vs. other "Falcon" tools

It is important to clarify that this report pertains exclusively to the Falcon
*web framework* (available at `falconframework.org`), a minimalist Python
framework for building web APIs. Searches for "Falcon correlation ID" may also
surface information related to other products or tools that share the "Falcon"
name, such as CrowdStrike Falcon, a cybersecurity platform. For instance,
`falconpy` is a Python SDK for interacting with the CrowdStrike Falcon API and
includes functionalities related to "correlation rules" within that security
context.[^9] Similarly, discussions around CrowdStrike's NG-SIEM might refer to
correlation of security events.[^10] These are distinct from the web framework
context of this report and are not directly relevant to the design of the
proposed middleware.

## 3. Design: Falcon correlation ID middleware

This section details the design of the correlation ID middleware for the Falcon
web framework, addressing its architecture, ID lifecycle management, contextual
data storage, logging integration, and downstream propagation strategies.

### 3.1. Middleware component architecture

#### 3.1.1. Falcon middleware class structure

Falcon middleware components are classes that implement specific methods to
hook into the request/response processing lifecycle.[^11] For a WSGI
application, these methods typically include:

- `process_request(self, req, resp)`: Processes the request before it is routed
  to a resource. This is the primary method for retrieving or generating the
  correlation ID.
- `process_resource(self, req, resp, resource, params)`: Processes the request
  after routing but before the resource's responder method is called. While
  optional for this specific use case, it's part of the Falcon middleware
  interface.
- `process_response(self, req, resp, resource, req_succeeded)`: Post-processes
  the response before it is sent back to the client. This can be used to add
  the correlation ID to response headers and for cleanup tasks.

If the Falcon application is running in ASGI mode, these methods will be
`async`.[^11] ASGI middleware can also include
`process_startup(self, scope, event)` and
`process_shutdown(self, scope, event)` to handle ASGI lifespan events, though
these are not directly involved in per-request correlation ID handling.[^11]

#### 3.1.2. Integrating with Falcon's request/response cycle

The correlation ID logic will primarily reside in the process_request and
process_response methods.

In process_request:

1. The middleware will inspect incoming request headers for an existing
   correlation ID.
2. Based on trusted source rules, it will either accept the incoming ID or
   generate a new one.
3. The determined correlation ID will be stored in a way that is accessible
   throughout the request's lifecycle.

Falcon middleware components are executed hierarchically. If multiple
middleware components are registered, their `process_request` methods are
called in order, followed by `process_resource` methods in the same order, then
the resource responder, and finally `process_response` methods in reverse
order.[^11] This execution model ensures that once the correlation ID
middleware sets the ID in `process_request`, it becomes available to subsequent
middleware layers and the target resource handler.

Falcon provides `req.context` and `resp.context` objects for passing
application-specific data through the request lifecycle.[^11] The correlation
ID can be stored in `req.context` to make it easily accessible within
Falcon-specific code.

In `process_response`:

1. The middleware can retrieve the correlation ID (e.g., from `req.context` or
   a more global context storage).
2. Optionally, it can add this ID to the outgoing response headers (e.g.,
   `X-Correlation-ID`), a feature seen in libraries like
   `asgi-correlation-id`.[^2]
3. Perform any necessary cleanup, such as resetting context-local variables.

A middleware method can short-circuit request processing by setting
`resp.complete = True`, causing Falcon to skip subsequent `process_request`,
`process_resource`, and responder methods, but still execute `process_response`
methods.[^11] This is generally not needed for correlation ID handling but is a
feature of Falcon's middleware system.

### 3.2. Correlation ID lifecycle management

#### 3.2.1. Retrieval from `X-Correlation-ID` header

Within the `process_request` method, the middleware will access `req.headers`
(a `dict`-like object) to look for the configured correlation ID header,
defaulting to `X-Correlation-ID`. If the header is present and non-empty, its
value will be considered as a candidate correlation ID.

#### 3.2.2. Defining and identifying "trusted sources"

A critical aspect is determining whether to trust an incoming correlation ID.
This trust should be granted only if the request originates from a known,
controlled upstream source, such as an API gateway, a load balancer, or another
internal service that is already part of the trusted correlation ID ecosystem.

The identification of trusted sources will typically be based on the IP address
of the direct peer connection, available via `req.remote_addr`. The middleware
will be configurable with a list of trusted IP addresses or subnets. If
`req.remote_addr` matches an entry in this list, an incoming `X-Correlation-ID`
header value can be accepted. Otherwise, or if the header is missing, a new ID
must be generated.

It is important to understand the implications of IP address headers when
services are behind proxies. `req.remote_addr` will provide the IP of the
immediate upstream client (e.g., the proxy itself). Headers like
`X-Forwarded-For` (XFF) may contain the original client's IP address.[^13]
However, XFF headers can be spoofed by a malicious client if the edge proxy or
load balancer does not properly sanitise or overwrite them.[^14] Therefore, for
the purpose of trusting an *incoming correlation ID*, the most secure approach
is to base the trust decision on `req.remote_addr` being a known, internal,
trusted proxy or load balancer. This component is then responsible for managing
the `X-Correlation-ID` header from external, untrusted clients (e.g., by
stripping it or generating a new one before forwarding the request internally).
The list of trusted IPs for the middleware should thus consist of the IP
addresses of these internal infrastructure components.

If an incoming ID is accepted, it may optionally be validated (see section
3.2.4).

#### 3.2.3. UUIDv7 generation and library choice

If no correlation ID is found in the header, if the source is not trusted, or
if an incoming ID fails validation, the middleware must generate a new UUIDv7.
UUIDv7 is chosen for its time-sortable properties and improved characteristics
over older UUID versions.[^6]

Several Python libraries are available for generating UUIDv7s. The standard
library uuid module includes uuid.uuid7() in Python 3.14 and later.[^15] For
applications using older Python versions, external libraries or backporting the
CPython implementation[^16] are necessary.

It is crucial to select a library that adheres to the latest UUIDv7
specification (RFC 9562, which obsoletes RFC 4122), particularly regarding
millisecond precision for the timestamp component.[^6] Some older libraries or
implementations might use outdated draft specifications with different
precision levels (e.g., nanosecond precision), which could lead to
compatibility issues or unexpected sorting behaviour.[^16]

The following table summarizes some available options for UUIDv7 generation:

| Library Name   | PyPI Link                      | Function for UUIDv7  | Key Features/Standard Compliance                  | Last Updated | Notes                                                                 |
| -------------- | ------------------------------ | -------------------- | ------------------------------------------------- | ------------ | --------------------------------------------------------------------- |
| `uuid6`        | `pypi.org/project/uuid6/`      | `uuid6.uuid7()`      | Implements draft RFC for v6, v7, v8; time-ordered | Mid-2023     | Provides `uuid7()`. Recommended for new systems over v1/v6.           |
| `uuid-v7`      | `pypi.org/project/uuid-v7/`    | `uuid_v7.generate()` | Aims for latest spec, simple API                  | Early 2024   | Appears viable and focused specifically on UUIDv7.                    |
| `uuid-utils`   | `pypi.org/project/uuid-utils/` | `uuid_utils.uuid7()` | General UUID utilities, includes v7 generation    | Recent       | Mentioned as a preferable option in community discussions.            |
| `uuid7` (old)  | `pypi.org/project/uuid7/`      | `uuid7.uuid7()`      | Based on an old draft (nanosecond precision)      | 2021         | **Should be avoided** due to outdated specification adherence.        |
| CPython `uuid` | N/A (Standard Library)         | `uuid.uuid7()`       | Official standard library implementation          | Python 3.14  | For older Python, consider copying source from CPython `Lib/uuid.py`. |

*Table 1: Available options for UUIDv7 generation in Python.*

The choice of library should be guided by its maintenance status, adherence to
the current UUIDv7 specification, and the Python versions targeted by the
application.

#### 3.2.4. Validation of incoming correlation IDs (optional but recommended)

It is advisable to include an optional validation step for correlation IDs
received from upstream services, even if those services are trusted. This
validation can check if the ID conforms to an expected format (e.g., is a valid
UUID string). The `asgi-correlation-id` library, for example, includes a
`validator` parameter for this purpose.[^2] If validation fails, the middleware
should generate a new ID to ensure that malformed or potentially problematic
identifiers do not propagate through the system. This helps maintain the
integrity and consistency of correlation IDs. A simple default validator could
check for standard UUID format (any version), while allowing for more specific
validation if needed.

### 3.3. Contextual storage with `contextvars`

To make the correlation ID (and other request-scoped data like the logged-in
user ID) available throughout the application code during the processing of a
single request, Python's `contextvars` module is the recommended
mechanism.[^17] `contextvars` provide a way to manage context-local state that
is correctly handled across threads and asynchronous tasks, which is essential
for web applications.

#### 3.3.1. Storing correlation ID and user ID

At the module level where the middleware is defined, `ContextVar` instances
will be created for the correlation ID and the user ID:

```python
import contextvars

correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)
user_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "user_id", default=None
)
```

In the `process_request` method of the middleware, after the correlation ID has
been retrieved or generated, its value will be set using
`correlation_id_var.set(value)`. The token returned by `set()` should be stored
if manual reset is planned.[^17]

The logged-in user's ID would typically be determined by an authentication
middleware. If the correlation ID middleware runs *after* authentication, it
can potentially access the user information from `req.context` (if the auth
middleware places it there) and set `user_id_var`. If it runs *before*
authentication, the authentication middleware itself should be responsible for
setting `user_id_var` once the user is identified.

#### 3.3.2. Accessing contextual data

Other parts of the application, such as logging filters, downstream service
clients, or business logic modules, can then retrieve these values using
`correlation_id_var.get()` and `user_id_var.get()`.[^17] If a default value was
provided during `ContextVar` creation, `get()` will return that if the variable
hasn't been set in the current context; otherwise, a `LookupError` will be
raised if no default is available and the variable is not set.

#### 3.3.3. Interaction with Falcon's `req.context`

Falcon's `req.context` object is designed for passing application-specific data
within the scope of a single request.[^11] While `contextvars` offer a more
general, library-agnostic solution for context propagation, especially useful
for helper functions or libraries that do not have access to Falcon's `req`
object, it can also be convenient to populate `req.context`.

A balanced approach is to use `contextvars` as the primary and authoritative
store for the correlation ID and user ID. This ensures broad accessibility. As
a convenience, the middleware can copy these values into `req.context` (for
example, `req.context.correlation_id = correlation_id_var.get()`), providing
handlers easy access via `req.context` while retaining broader availability
through `contextvars`.

#### 3.3.4. Clearing context variables

It is crucial to clear or reset context variables at the end of each request.
This prevents data from one request from "leaking" into another, which can
occur in persistent application server environments where threads or workers
might be reused. This cleanup should typically happen in the `process_response`
method of the middleware.

If the `token` from `var.set()` was stored, `var.reset(token)` can be used to
restore the `ContextVar` to its state before `set()` was called in the current
context.[^17] Alternatively, if using libraries like `structlog` that provide
context management utilities, functions like
`structlog.contextvars.clear_contextvars()` might be available to clear all
`structlog`-managed context variables.[^18] For manually managed `ContextVar`s,
explicit `reset` or setting them back to `None` (if a new `set` is done at the
start of each request) is necessary.

### 3.4. Logging integration

A primary use of correlation IDs is to enhance logging. The goal is to include
the correlation ID and the current user's ID in every log message generated
during the processing of a request.

#### 3.4.1. Injecting correlation ID and user ID via `logging.Filter`

The standard Python `logging` module can be extended using a custom
`logging.Filter`.[^19] This filter will be added to the relevant logger
configurations. Its `filter` method, called for each `LogRecord`, will:

1. Retrieve the correlation ID from `correlation_id_var.get()`.
2. Retrieve the user ID from `user_id_var.get()`.
3. Add these values as new attributes to the `LogRecord` object (e.g.,
   `record.correlation_id = ...`, `record.user_id = ...`). If the values are
   not set in the context, a default placeholder (e.g., `'-'` or `None`) can be
   used. The `asgi-correlation-id` library provides a similar
   `CorrelationIdFilter`.[^2]

Example structure for such a filter:

```python
import logging


class ContextualLogFilter(logging.Filter):
    def filter(self, record):
        record.correlation_id = correlation_id_var.get()
        record.user_id = user_id_var.get()
        # Potentially add other contextual data
        return True
```

This filter should then be added to the appropriate handlers in the logging
configuration.

#### 3.4.2. Configuring log formatters

Once the custom filter adds these attributes to `LogRecord` objects, the log
formatters need to be updated to include them in the output. This involves
modifying the format string used by `logging.Formatter`. For example:

```python
LOG_FORMAT = (
    "%(asctime)s - [%(levelname)s] - [%(correlation_id)s] - "
    "[%(user_id)s] - %(name)s - %(message)s"
)
formatter = logging.Formatter(LOG_FORMAT)
```

This will ensure that the correlation ID and user ID appear in the formatted
log messages.[^1]

#### 3.4.3. (Optional) Considerations for `structlog`

If the application uses `structlog` for structured logging, integrating context
variables is often more straightforward.[^18] `structlog` provides processors
like `structlog.contextvars.merge_contextvars()` which can be added to the
processor chain.[^18] This processor automatically merges any data bound using
`structlog.contextvars.bind_contextvars()` (or compatible `contextvars` set
elsewhere) into the log event dictionary.

For applications already employing or considering `structlog`, this approach
offers a more elegant and powerful way to include contextual data compared to
standard `logging` filters and manual format string manipulation. It aligns
well with `structlog`'s philosophy of structured, context-rich logging and can
simplify the overall logging setup. This should be presented as an advanced or
alternative option for users seeking sophisticated logging capabilities. Using
`structlog` would typically involve configuring it at application startup, and
then `contextvars` set by the middleware (like `correlation_id_var` and
`user_id_var`) would be automatically picked up if `merge_contextvars` is in
the processor chain.

### 3.5. Downstream propagation strategies

To maintain traceability across service boundaries, the correlation ID must be
propagated to any downstream services called during the request. This includes
HTTP requests to other microservices and tasks enqueued to Celery workers.

#### 3.5.1. Propagating to HTTP services with `httpx`

When making outgoing HTTP calls using the `httpx` library, the correlation ID
(retrieved from `correlation_id_var.get()`) should be added as a header (e.g.,
`X-Correlation-ID`) to the request. Several methods can achieve this:

##### 3.5.1.1. Injecting correlation ID into outgoing request headers

This is the core requirement for `httpx` propagation. The ID, once retrieved
from `contextvars`, needs to be included in the `headers` argument of `httpx`
request methods.

##### 3.5.1.2. Method 1: `httpx.Client` configuration

If a single `httpx.Client` instance is reused for multiple requests, its
`headers` attribute can be configured with default headers.[^22] However, since
the correlation ID is request-specific, setting it directly as a static default
header on a long-lived client is not suitable. Instead, `httpx.Client` event
hooks (`event_hooks={'request': [hook_func]}`) could be used. The `hook_func`
would retrieve the ID from `contextvars` and add it to `request.headers`. This
approach centralises the logic if client instances are managed.

##### 3.5.1.3. Method 2: Custom `httpx` transport

For more fine-grained control or when client instances are not centrally
managed, a custom `httpx.Transport` can be created.[^23] A class subclassing
`httpx.BaseTransport` (for synchronous clients) or `httpx.AsyncBaseTransport`
(for asynchronous clients) can override the `handle_request` (or
`handle_async_request`) method. Within this method, it would retrieve the
correlation ID from `contextvars` and add it to the `request.headers` before
forwarding the request to the underlying transport. This encapsulates the logic
cleanly.

```python
# Example concept for a custom transport
class CorrelationIDTransport(httpx.BaseTransport):
    def __init__(self, wrapped_transport: httpx.BaseTransport):
        self._wrapped_transport = wrapped_transport

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        cid = correlation_id_var.get()
        if cid:
            request.headers["X-Correlation-ID"] = cid
        return self._wrapped_transport.handle_request(request)
```

##### 3.5.1.4. Method 3: Manual header injection or wrapper function

The most straightforward method is to manually retrieve the ID from
`contextvars` and add it to the `headers` dictionary for each `httpx` call
(e.g., `httpx.get(url, headers={'X-Correlation-ID': cid, ...})`). While simple,
this is prone to being forgotten and adds boilerplate.

A more robust and practical approach is to create a small wrapper function
around `httpx.request` (or specific methods like `httpx.get`, `httpx.post`).
This wrapper would:

1. Accept the standard `httpx` arguments.
2. Retrieve the correlation ID from `correlation_id_var.get()`.
3. If the ID exists, add it to the `headers` dictionary (creating or updating
   it).
4. Call the underlying `httpx` function with the modified arguments. This
   approach balances encapsulation with ease of use and is less intrusive than
   a full custom transport if only header modification is needed.

The choice of method depends on the application's `httpx` usage patterns. For
applications with centrally managed `httpx.Client` instances, event hooks or a
custom transport applied to the client are good choices. For more ad-hoc usage
of `httpx` functions, a wrapper function provides a good combination of
convenience and reliability.

#### 3.5.2. Propagating to Celery tasks

Celery tasks operate asynchronously, often in separate processes or machines.
Propagating the correlation ID to Celery tasks is crucial for end-to-end
tracing.

##### 3.5.2.1. Leveraging Celery's native `correlation_id`

Celery's message protocol includes a dedicated `correlation_id` field in the
message properties.[^24] The objective is to populate this field with the
correlation ID from the current web request when a task is initiated.

##### 3.5.2.2. Method 1: Using `before_task_publish` signal

Celery provides a `before_task_publish` signal that is dispatched just before a
task message is sent to the broker.[^25] A handler can be connected to this
signal. Inside the handler:

1. Retrieve the correlation ID from `correlation_id_var.get()`.
2. If an ID is present, update the task message's properties to include it. The
   signal handler receives arguments like `body`, `exchange`, `routing_key`,
   `headers`, and `properties`. The `properties` dictionary can be modified to
   set `properties['correlation_id'] = cid`.[^25]

```python
from celery.signals import before_task_publish


@before_task_publish.connect
def propagate_correlation_id_to_celery(
    sender=None, headers=None, body=None, properties=None, **kwargs
):
    cid = correlation_id_var.get()
    if cid:
        if properties is None:  # Should not happen with recent Celery
            properties = {}
        properties["correlation_id"] = cid
        # Celery task headers can also be used, though properties is standard
        if headers is None:
            headers = {}
        # headers["X-Correlation-ID"] = cid  # If custom header propagation needed
```

This approach is generally clean and idiomatic for Celery, as it directly hooks
into the task publishing mechanism.

##### 3.5.2.3. Method 2: Custom Celery `Task` base class

Alternatively, a custom base class inheriting from `celery.Task` can be
created.[^27] This base class can override methods like `apply_async` or
`send_task` to automatically retrieve the correlation ID from `contextvars` and
inject it into the task options (specifically `correlation_id=cid`) before
calling the superclass method. All application tasks would then inherit from
this custom base class. This encapsulates the behaviour but requires modifying
task definitions.

##### 3.5.2.4. Accessing correlation ID within the Celery task worker

Once a task message with a correlation_id is received by a Celery worker, the
ID is available in the task's request context as `task.request.correlation_id`.

To make this ID available for logging within the task's execution (and for any
further downstream calls made by the task), a `task_prerun` signal handler
should be used.[^25] This signal is dispatched before a task is executed by a
worker. The handler would:

1. Retrieve `task.request.correlation_id`.
2. Set this ID into `correlation_id_var` (the same `ContextVar` used in the web
   application) using `correlation_id_var.set(task.request.correlation_id)`.
3. Optionally, if the user ID was also propagated (e.g., in task arguments or
   headers), set `user_id_var` as well.

A corresponding `task_postrun` signal handler should then be used to clear
these `contextvars` (e.g., using `correlation_id_var.reset(token)`) to ensure
context isolation between tasks executed by the same worker process.

This end-to-end flow ensures that:

1. The correlation ID from the web request is embedded in the Celery task
   message.
2. The Celery worker extracts this ID and establishes it in its own execution
   context using `contextvars`.
3. Logging within the Celery task (if configured with the same
   `ContextualLogFilter`) will automatically include the correct correlation
   ID. This provides seamless traceability from the initial web request through
   to asynchronous task execution. The `asgi-correlation-id` documentation also
   alludes to tracing IDs across Celery workers.[^2]

#### Table: Comparison of propagation methods

| System   | Method                       | Pros                                                                | Cons                                                                      | Recommended For                                                                   |
| -------- | ---------------------------- | ------------------------------------------------------------------- | ------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| `httpx`  | Client Event Hooks           | Centralized logic for reused `Client` instances.                    | Correlation ID is request-specific, hook needs access to `contextvars`.   | Applications with well-managed, request-scoped or short-lived `Client` instances. |
| `httpx`  | Custom Transport             | Cleanly encapsulates logic; transparent to calling code.            | More boilerplate than simple injection; might be overkill for one header. | Scenarios requiring uniform header injection across many calls or complex logic.  |
| `httpx`  | Wrapper Function             | Good balance of encapsulation and flexibility; easy to use.         | Requires developer discipline to consistently use the wrapper.            | Most common use cases, providing a simple and explicit way to add the header.     |
| `Celery` | `before_task_publish` Signal | Idiomatic Celery approach; modifies the actual message; global.     | Affects all tasks (can filter by `sender` argument if needed).            | **Generally recommended** for most Celery integration scenarios.                  |
| `Celery` | Custom `Task` Base Class     | Behaviour encapsulated with task definition; good for shared logic. | Requires modifying all task definitions to inherit from the custom base.  | Applications where tasks already share a custom base class for other reasons.     |

*Table 2: Comparison of propagation methods for httpx and Celery.*

### 3.6. Security and operational considerations

#### 3.6.1. Validating and sanitising incoming correlation IDs

Reiterating the importance of validation, even if an incoming ID is from a
trusted source, it's good practice to ensure it meets expected formats (e.g.,
UUID structure). If the "trusted source" check fails and a new ID is generated,
logging the attempted (and rejected) incoming ID might be useful for security
auditing. Validation can prevent issues like overly long IDs or potentially
malicious content from being processed or logged if not properly handled by all
downstream systems.

#### 3.6.2. Implications of trusted source logic

The list of trusted IP addresses or subnets must be carefully configured and
maintained. An overly permissive list could lead to the acceptance of
correlation IDs from untrusted or malicious sources, potentially allowing an
attacker to inject misleading IDs or attempt to link unrelated requests.
Conversely, an overly restrictive list might cause the system to unnecessarily
regenerate IDs for legitimate internal traffic, breaking the trace. Regular
audits of this configuration are advisable.

#### 3.6.3. Performance impact

The performance overhead of the correlation ID middleware should generally be
negligible.

- **Header parsing:** Accessing request headers is a standard operation.
- **IP address checking:** Comparing `req.remote_addr` against a list of
  trusted IPs is fast, especially if the list is small or implemented
  efficiently (e.g., using a set for lookups).
- **UUIDv7 generation:** Modern UUID generation libraries are highly optimised.
- **`contextvars` access:** `ContextVar.get()` and `ContextVar.set()` are
  designed to be efficient. `copy_context()` is O(1).[^17]
- **Logging filter:** Adding attributes to a `LogRecord` is a lightweight
  operation.

The cumulative impact on request latency should be minimal, typically in the
sub-millisecond range.

#### 3.6.4. Error handling within the middleware

The middleware itself must be robust. If an unexpected error occurs within the
middleware (e.g., a misconfigured UUID generator fails, though highly unlikely
for reputable libraries), it should not cause the entire request to fail
catastrophically. Falcon's middleware exception handling mechanisms can be
leveraged.[^11] If an exception is raised in `process_request`, Falcon will
attempt to find a registered error handler. The middleware should ideally log
its own errors and fall back to a state where the request can proceed, perhaps
without a correlation ID or with a default placeholder, rather than halting
processing.

## 4. Implementation guidance and examples

This section provides illustrative code snippets for the key components of the
Falcon correlation ID middleware. These examples assume a Falcon WSGI
application for simplicity, but adaptations for ASGI would primarily involve
`async` methods and type hints.

### 4.1. Core middleware code snippet (Falcon WSGI)

```python
import falcon
import uuid  # Standard library for UUID, specific v7 generator needed
import contextvars
from typing import Callable, List, Optional

# --- Context Variables (defined globally or in an appropriate module) ---
correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)
user_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "user_id", default=None
)


# Placeholder for a chosen UUIDv7 generator function
# For example, from the 'uuid_v7' package: from uuid_v7 import generate as uuid7_generate
# Or from 'uuid6' package: from uuid6 import uuid7 as uuid7_generate
# Or copied CPython source
def default_uuid7_generator() -> str:
    # Replace with actual UUIDv7 generation logic
    # This is a placeholder using uuid.uuid4 for concept illustration
    # In a real scenario, use a proper UUIDv7 generator.
    # For example: return uuid7_generate().hex if using a library that returns UUID object
    return uuid.uuid4().hex


class CorrelationIDMiddleware:
    def __init__(
        self,
        header_name: str = "X-Correlation-ID",
        trusted_sources: Iterable[str] | None = None,
        generator: Callable[[], str] = default_uuid7_generator,
        validator: Callable[[str], bool] | None = None,
        echo_header_in_response: bool = True,
    ):
        self.header_name = header_name
        self.trusted_sources = frozenset(trusted_sources) if trusted_sources else frozenset()
        self.generator = generator
        self.validator = validator
        self.echo_header_in_response = echo_header_in_response
        self._correlation_id_set_token = None  # For resetting contextvar

    def _is_trusted_source(self, remote_addr: Optional[str]) -> bool:
        if not remote_addr:
            return False
        return remote_addr in self.trusted_sources

    def process_request(self, req: falcon.Request, resp: falcon.Response):
        incoming_cid = req.get_header(self.header_name)
        final_cid = None

        if incoming_cid:
            is_valid = True
            if self.validator:
                is_valid = self.validator(incoming_cid)

            if is_valid and self._is_trusted_source(req.remote_addr):
                final_cid = incoming_cid
            elif not is_valid:
                # Log invalid incoming CID attempt if desired
                final_cid = self.generator()
            else:  # Valid format, but not trusted source
                final_cid = self.generator()
        else:
            final_cid = self.generator()

        # Store in contextvar
        self._correlation_id_set_token = correlation_id_var.set(final_cid)

        # Optionally store in req.context for Falcon-specific access
        if not hasattr(req.context, "correlation_id"):
            req.context.correlation_id = final_cid

        # User ID would typically be set by an authentication middleware
        # For demonstration, if auth middleware ran and set req.context.user:
        # if hasattr(req.context, 'user') and req.context.user:
        #     user_id_var.set(str(req.context.user.get('id')))

    def process_response(
        self,
        req: falcon.Request,
        resp: falcon.Response,
        resource,
        req_succeeded: bool,
    ):
        cid = correlation_id_var.get()
        if cid and self.echo_header_in_response:
            resp.set_header(self.header_name, cid)

        # Reset context variables
        if self._correlation_id_set_token:
            correlation_id_var.reset(self._correlation_id_set_token)
            self._correlation_id_set_token = None
        # user_id_var should also be reset if set by this middleware
        # current_user_token = getattr(self, '_user_id_set_token', None)
        # if current_user_token:
        #     user_id_var.reset(current_user_token)
```

### 4.2. `logging.Filter` implementation

```python
import logging

# Assumes correlation_id_var and user_id_var are accessible (e.g., imported)
# from .middleware import correlation_id_var, user_id_var  # Example import


class ContextualLogFilter(logging.Filter):
    def filter(self, record):
        record.correlation_id = correlation_id_var.get()
        record.user_id = user_id_var.get()  # Or a default like '-' if None
        return True


# Example logging configuration (simplified)
# import logging.config
# LOGGING_CONFIG = {
#     'version': 1,
#     'disable_existing_loggers': False,
#     'filters': {
#         'contextual_filter': {
#             '()': ContextualLogFilter,  # Path to your filter class
#         }
#     },
#     'formatters': {
#         'standard': {
#             'format': (
#                 '%(asctime)s [%(levelname)s][%(correlation_id)s]'
#                 '[%(user_id)s] %(name)s: %(message)s'
#             )
#         },
#     },
#     'handlers': {
#         'console': {
#             'level': 'INFO',
#             'filters': ['contextual_filter'],
#             'class': 'logging.StreamHandler',
#             'formatter': 'standard'
#         },
#     },
#     'root': {
#         'handlers': ['console'],
#         'level': 'INFO',
#     }
# }
# logging.config.dictConfig(LOGGING_CONFIG)
```

### 4.3. Example: `httpx` header injection wrapper

```python
import httpx
from typing import Any, Mapping, Optional

# Assumes correlation_id_var is accessible
# from .middleware import correlation_id_var  # Example import


def client_request_with_correlation_id(
    method: str, url: str, **kwargs: Any
) -> httpx.Response:
    headers: Optional[Mapping[str, str]] = kwargs.pop("headers", {})
    if headers is None:  # Ensure headers is a mutable dict
        headers = {}
    else:  # Ensure it's mutable if passed as an immutable mapping
        headers = dict(headers)

    cid = correlation_id_var.get()
    if cid:
        # Using the same header name as configured in the middleware
        # This could also be made configurable for the client wrapper
        headers["X-Correlation-ID"] = cid

    return httpx.request(method, url, headers=headers, **kwargs)


async def async_client_request_with_correlation_id(
    method: str, url: str, **kwargs: Any
) -> httpx.Response:
    headers: Optional[Mapping[str, str]] = kwargs.pop("headers", {})
    if headers is None:
        headers = {}
    else:
        headers = dict(headers)

    cid = correlation_id_var.get()
    if cid:
        headers["X-Correlation-ID"] = cid

    async with httpx.AsyncClient() as client:  # Or use a shared client
        return await client.request(method, url, headers=headers, **kwargs)


# Usage:
# response = client_request_with_correlation_id(
#     'GET', 'https://api.example.com/data'
# )
# response = await async_client_request_with_correlation_id(
#     'POST', 'https://api.example.com/submit', json={...}
# )
```

### 4.4. Example: Celery signal handler for propagation

```python
import contextvars
from celery import Celery
from celery.signals import before_task_publish, task_prerun, task_postrun

# Assumes correlation_id_var and user_id_var are accessible
# from .middleware import correlation_id_var, user_id_var  # Example import

# This would typically be your Celery application instance
# app = Celery('tasks', broker='redis://localhost:6379/0')

_celery_context_tokens = contextvars.ContextVar(
    "celery_context_tokens", default=None
)


@before_task_publish.connect
def propagate_correlation_id_to_celery(
    sender=None, headers=None, body=None, properties=None, **kwargs
):
    # 'properties' is the standard place for AMQP message properties
    # 'headers' are application-level headers within the Celery message body
    cid = correlation_id_var.get()
    if cid:
        current_properties = properties if properties is not None else {}
        current_properties["correlation_id"] = cid

        # If you also want to propagate user_id, it could go into task headers
        # current_headers = headers if headers is not None else {}
        # uid = user_id_var.get()
        # if uid:
        #     current_headers["X-User-ID"] = uid  # Custom header for user ID


@task_prerun.connect
def setup_correlation_id_in_worker(
    sender=None, task_id=None, task=None, args=None, kwargs=None, **kw
):
    # task.request.correlation_id is where Celery puts the AMQP correlation_id
    cid = task.request.correlation_id
    tokens = {}
    if cid:
        tokens["correlation_id"] = correlation_id_var.set(cid)

    # Example: If user ID was propagated via task headers
    # uid = task.request.get('X-User-ID')
    # if uid:
    #     tokens['user_id'] = user_id_var.set(uid)

    if tokens:
        _celery_context_tokens.set(tokens)


@task_postrun.connect
def clear_correlation_id_in_worker(
    sender=None,
    task_id=None,
    task=None,
    args=None,
    kwargs=None,
    retval=None,
    state=None,
    **kw,
):
    tokens = _celery_context_tokens.get()
    if tokens:
        if "correlation_id" in tokens:
            correlation_id_var.reset(tokens["correlation_id"])
        if "user_id" in tokens:
            user_id_var.reset(tokens["user_id"])
        _celery_context_tokens.set(None)  # Clear the tokens storage itself
```

### 4.5. Middleware configuration

The `CorrelationIDMiddleware` is instantiated and passed to the Falcon `App`
during its initialisation.

```python
# Example: In your main application setup file (e.g., app.py)
# from .middleware import CorrelationIDMiddleware
# from .custom_uuid_gen import my_uuid7_generator  # If you have a custom generator
# from .validators import is_valid_uuid_any_version  # If you have a custom validator

# Configure trusted IPs (e.g., your load balancer, API gateway)
TRUSTED_IPS = ["10.0.0.1", "192.168.1.254"]

# Instantiate the middleware
correlation_middleware = CorrelationIDMiddleware(
    header_name="X-MyCompany-Correlation-ID",  # Custom header name
    trusted_sources=TRUSTED_IPS,
    # generator=my_uuid7_generator,           # Custom generator
    # validator=is_valid_uuid_any_version,    # Custom validator
    echo_header_in_response=True,
)

# Create Falcon app with the middleware
# For WSGI:
# app = falcon.App(middleware=[correlation_middleware, ...other_middleware...])
# For ASGI:
# app = falcon.asgi.App(middleware=[correlation_middleware, ...other_middleware...])
```

#### Table: Middleware configuration options

| Parameter Name            | Type                              | Default Value             | Description                                                                                                        |
| ------------------------- | --------------------------------- | ------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `header_name`             | `str`                             | `X-Correlation-ID`        | The HTTP header name to check for an incoming correlation ID and to use for the outgoing response header.          |
| `trusted_sources`         | `Iterable[str]`, optional         | `None` (empty set)        | A collection of IP addresses or subnets considered trusted. If `None` or empty, no sources are trusted by default. |
| `generator`               | `Callable[[], str]`               | `default_uuid7_generator` | A callable that returns a new string-based correlation ID (e.g., a UUIDv7).                                        |
| `validator`               | `Callable[[str], bool]`, optional | `None`                    | An optional callable that takes the incoming ID string and returns `True` if valid, `False` otherwise.             |
| `echo_header_in_response` | `bool`                            | `True`                    | If `True`, the determined correlation ID will be added to the specified header in the outgoing response.           |

*Table 3: Middleware configuration options.*

### 4.6. Implementation notes

This section records design decisions made during implementation of the
configurable options (task 1.2.2).

#### 4.6.1. Keyword-only arguments

All constructor parameters are keyword-only (enforced via `*` in the function
signature). This design choice:

- Enforces explicit configuration, preventing positional argument mistakes
- Makes code self-documenting at the call site
- Allows future parameter additions without breaking existing code

#### 4.6.2. Internal storage of trusted_sources

The `trusted_sources` parameter accepts any `Sequence[str]` (list, tuple, set)
but is stored internally as a `frozenset[str]`. This provides:

- **Immutability**: Configuration cannot be accidentally modified after
  instantiation
- **O(1) lookup**: Membership testing during request processing is constant-time
- **Defensive copy**: Changes to the original sequence after middleware
  instantiation do not affect the middleware's trusted sources, protecting
  against accidental misconfiguration

#### 4.6.3. Default UUIDv7 generator implementation

The `default_uuid7_generator` function uses the standard library `uuid.uuid7()`
when available. If the runtime does not provide `uuid.uuid7()`, it falls back
to `uuid_utils.uuid7()` so UUIDv7 generation remains available. The generator
returns the UUID hex string representation to keep correlation IDs compact and
consistent. Custom generators remain supported via the `generator` parameter.

#### 4.6.4. Property-based attribute access

Configuration values are exposed via read-only properties rather than direct
attribute access. This ensures:

- Encapsulation of internal implementation details
- Consistent interface for subclasses (like `TrackingMiddleware`)
- Future flexibility to add computed properties if needed

#### 4.6.5. Header retrieval handling

Incoming correlation ID headers are read via `req.get_header` using the
configured header name. The middleware trims leading and trailing whitespace,
treats missing or empty values as absent, and stores the value on
`req.context.correlation_id` only when non-empty. This prevents empty
identifiers from entering the lifecycle while keeping generation and validation
logic isolated to later tasks.

#### 4.6.6. Trusted source IP/Classless Inter-Domain Routing (CIDR) matching

Trusted source matching is implemented using Python's standard library
`ipaddress` module. IP addresses and CIDR subnet notations provided in
`trusted_sources` are parsed at configuration time and stored as `IPv4Network`
or `IPv6Network` objects. This design choice:

- **Validates early**: Invalid IP/CIDR formats raise `ValueError` at
  instantiation, providing immediate feedback rather than runtime errors.
- **Optimizes lookups**: Pre-parsed network objects enable O(1) containment
  checks at request time using `addr in network`.
- **Enforces correctness**: Using `strict=True` ensures CIDR notations specify
  network addresses (e.g., `10.0.0.0/24`) rather than host addresses with
  subnet masks (e.g., `10.0.0.5/24`), preventing common configuration mistakes.

The `_is_trusted_source()` method returns `False` for:

- `None` or empty `remote_addr` values
- Malformed IP addresses that cannot be parsed
- IP addresses not matching any configured trusted source

This defensive approach ensures that misconfigured or unexpected inputs never
accidentally grant trust. The `process_request` method sets
`req.context.correlation_id` to the incoming ID when the source is trusted.
When the source is untrusted or the header is missing, a new correlation ID is
generated using the configured generator.

#### 4.6.7. Generator invocation timing

The configured generator is called in `process_request()` when either:

- No correlation ID header is present (missing or whitespace-only)
- The request source is not trusted (incoming ID rejected)

This ensures every request receives a correlation ID for complete traceability.
The generator is called synchronously; async generator support will be added
with the ASGI middleware variant (task 5.1). Generated IDs are not validated
since the generator is trusted to produce valid output. Validation (task 2.3)
applies only to incoming IDs from external sources.

## 5. Conclusion and recommendations

This report has detailed the design for a comprehensive correlation ID
middleware for the Falcon web framework. The proposed solution addresses the
generation and retrieval of correlation IDs, their secure handling based on
trusted sources, integration into logging systems using `contextvars` and
`logging.Filter`, and strategies for propagation to downstream HTTP services
via `httpx` and asynchronous Celery tasks.

### 5.1. Summary of the proposed design

The core of the design is a Falcon middleware component that intercepts
requests to manage the correlation ID. It prioritises incoming IDs from trusted
sources via a configurable header (e.g., `X-Correlation-ID`) and generates a
new UUIDv7 if necessary. UUIDv7 is chosen for its time-sortable properties,
aiding in log analysis and database indexing.

Contextual information, primarily the correlation ID and optionally a user ID,
is stored using Python's `contextvars` module, ensuring its availability
throughout the request lifecycle, including in asynchronous contexts. This
enables a custom `logging.Filter` to inject these IDs into all relevant log
records, which can then be included in log output via formatter configuration.
For applications using `structlog`, integration is even more seamless.

Downstream propagation to `httpx` clients can be achieved through various
methods, including client event hooks, custom transports, or wrapper functions,
ensuring the correlation ID is passed in headers. For Celery, the
`before_task_publish` signal is recommended to inject the ID into the task
message's standard `correlation_id` field. On the worker side, `task_prerun`
and `task_postrun` signals manage the lifecycle of the correlation ID within
the task's execution context, enabling consistent logging.

### 5.2. Best practices for deployment and usage

- **Middleware order:** The `CorrelationIDMiddleware` should generally be
  placed early in the middleware stack, but potentially after any middleware
  that might modify `req.remote_addr` (e.g., a proxy fixup middleware if not
  handled by the WSGI/ASGI server itself). It should ideally run before
  authentication middleware if it needs to rely on the user ID set by auth, or
  the auth middleware should set the user ID `contextvar` itself.
- **Trusted source configuration:** Diligently configure and maintain the list
  of `trusted_sources`. This is critical for security and the integrity of
  correlation IDs.
- **Log aggregation:** To fully leverage correlation IDs, employ a centralised
  log aggregation system (e.g., ELK Stack, Splunk, Grafana Loki). This allows
  for efficient searching and filtering of logs across all services using the
  correlation ID.
- **Consistency:** Ensure all services within the distributed system adhere to
  the same correlation ID header name and propagation practices.
- **UUIDv7 library selection:** Carefully choose and vet the UUIDv7 generation
  library, especially for Python versions older than 3.14, ensuring it conforms
  to the latest specification.

### 5.3. Potential future enhancements

The proposed design provides a solid foundation. Future enhancements could
include:

- **Deeper distributed tracing integration:** Integrate more closely with
  distributed tracing standards and tools like OpenTelemetry. The correlation
  ID could serve as, or be linked to, a trace ID or span ID, providing a richer
  observability experience.[^1]
- **Advanced validation and transformation:** Implement more sophisticated
  validation rules for incoming IDs or allow for transformation of IDs if
  required by specific interoperability scenarios, similar to the `transformer`
  parameter in `asgi-correlation-id`.[^2]
- **Broader protocol support:** Extend automatic propagation capabilities to
  other inter-service communication protocols if used within the architecture
  (e.g., gRPC, message queues other than Celery's direct broker communication).
- **Dynamic trusted source configuration:** Allow the list of trusted sources
  to be updated dynamically without application restarts, perhaps by
  integrating with a configuration management system.

By implementing a robust correlation ID mechanism as outlined, developers can
significantly improve the observability, debuggability, and operational
manageability of Falcon-based applications, especially within complex,
distributed environments.

[^1]: Elastic APM trace and transaction ID correlation.
[^2]: asgi-correlation-id library documentation.
[^4]: SAP Concur API correlation ID header.
[^5]: Kong API Gateway request ID header.
[^6]: UUIDv7 specification and time-sortable properties.
[^7]: uuid6 library documentation.
[^9]: CrowdStrike Falcon API SDK (falconpy).
[^10]: CrowdStrike NG-SIEM correlation features.
[^11]: Falcon web framework middleware documentation.
[^13]: X-Forwarded-For header specification.
[^14]: Security considerations for X-Forwarded-For headers.
[^15]: Python 3.14 uuid.uuid7() addition.
[^16]: UUIDv7 library comparison discussions.
[^17]: Python contextvars module documentation.
[^18]: structlog contextvars integration.
[^19]: Python logging.Filter documentation.
[^22]: httpx Client headers configuration.
[^23]: httpx custom Transport documentation.
[^24]: Celery message protocol correlation_id field.
[^25]: Celery signals documentation.
[^27]: Celery custom Task base class documentation.

## Appendix A: Implementation Design Decisions

This appendix documents design decisions made during implementation of the
middleware.

### A.1. Middleware Skeleton (Task 1.2.1)

**Decision:** Implement the initial `CorrelationIDMiddleware` as a skeleton
with method stubs, deferring full functionality to subsequent tasks.

**Rationale:**

1. **Incremental development:** Following the roadmap structure allows for
   focused, testable increments. The skeleton establishes the class structure
   and interface before adding complex logic.

2. **WSGI-first approach:** The initial implementation targets WSGI applications
   using synchronous `process_request` and `process_response` methods. The ASGI
   variant with async methods is planned for task 5.1.

3. **Type safety:** Full type hints using `falcon.Request` and `falcon.Response`
   from Falcon's public API ensure type checker compatibility and IDE support.

4. **Test-driven development:** Unit tests and BDD behavioural tests are written
   alongside the skeleton to validate the interface before functionality is
   added.

**Files created:**

- `src/falcon_correlate/middleware.py` - Core middleware class
- `src/falcon_correlate/unittests/test_middleware.py` - Colocated unit tests
- `tests/bdd/middleware.feature` - BDD feature file
- `tests/bdd/test_middleware_steps.py` - BDD step definitions

**Interface:**

```python
class CorrelationIDMiddleware:
    def process_request(self, req: falcon.Request, resp: falcon.Response) -> None:
        ...

    def process_response(
        self,
        req: falcon.Request,
        resp: falcon.Response,
        resource: object,
        req_succeeded: bool,
    ) -> None:
        ...
```

### A.2. Context Variable Definitions (Task 2.4.1)

**Decision:** Define `correlation_id_var` and `user_id_var` as module-level
`contextvars.ContextVar[str | None]` instances in `middleware.py`, with
`default=None`, and export them via `__init__.py` as part of the public API.

**Rationale:**

1. **Placement in `middleware.py`:** The design document (§3.3.1) specifies
   "At the module level where the middleware is defined." Co-locating the
   context variables with the middleware that will manage their lifecycle (task
   2.4.2) avoids circular imports and keeps the dependency graph simple.

2. **`default=None`:** Matches the design specification. A `None` default
   allows consumers to distinguish between "no correlation ID set" and a valid
   ID without risking `LookupError` exceptions from `ContextVar.get()`.

3. **Variable names (`"correlation_id"`, `"user_id"`):** Match the design
   specification exactly. These are the internal names passed to the
   `ContextVar` constructor and appear in debugging output.

4. **Public API export:** Both variables are included in `__all__` and
   importable from the package root
   (`from falcon_correlate import correlation_id_var, user_id_var`). This
   enables consumers — logging filters, downstream service clients, and
   application code — to access request-scoped data without coupling to
   Falcon's `req` object.

5. **Lifecycle deferred to task 2.4.2:** This task defines the variables
   only. Setting the correlation ID in `process_request` and resetting it in
   `process_response` is the responsibility of task 2.4.2. The `user_id_var` is
   intended for use by authentication middleware or application code; the
   correlation ID middleware does not set it.

**Files created/modified:**

- `src/falcon_correlate/middleware.py` — Added `import contextvars` and two
  `ContextVar` definitions.
- `src/falcon_correlate/__init__.py` — Added both variables to imports and
  `__all__`.
- `src/falcon_correlate/unittests/test_context_variables.py` — Unit tests.
- `tests/bdd/context_variables.feature` — BDD feature file.
- `tests/bdd/test_context_variables_steps.py` — BDD step definitions.
