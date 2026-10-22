# falcon-correlate

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](
https://deepwiki.com/leynos/falcon-correlate)

*Give every Falcon request a correlation ID, then keep it through the logs, the
next HTTP hop, and the task queue.*

`falcon-correlate` is middleware for the
[Falcon web framework](https://falconframework.org/). It assigns a correlation
ID to each request, makes that ID available to application code, and helps it
travel through standard-library logs, outbound `httpx` calls, and Celery tasks.

______________________________________________________________________

## Why falcon-correlate?

A single request rarely stays inside one service. It is logged by your Falcon
app, forwarded to a downstream API, and queued as a background task. Without a
shared identifier, joining those records into one story is guesswork.

- **Trusted IDs, not just generated ones.** An incoming header is accepted only
  from a trusted source; when a validator is configured, it must also pass that
  format check. Otherwise the middleware generates a fresh UUIDv7.
- **Both Falcon flavours.** Synchronous Web Server Gateway Interface (WSGI)
  apps and Asynchronous Server Gateway Interface (ASGI) apps get the same
  behaviour from one shared configuration object.
- **Propagation where you need it.** The middleware, the logging filter, the
  `httpx` transports, and the Celery signal handlers all read one request-local
  context variable.
- **Optional stays optional.** Install only the extra you need; a Falcon-only
  application pulls in neither `httpx` nor Celery.

______________________________________________________________________

## Installation

```bash
pip install falcon-correlate
```

`falcon-correlate` requires Python 3.12 or later and Falcon 4.3.1 or later.

Two extras enable the propagation helpers:

```bash
pip install "falcon-correlate[httpx]"    # outbound HTTP propagation
pip install "falcon-correlate[celery]"   # Celery task propagation
```

______________________________________________________________________

## Quick start

### WSGI application

```python
import falcon

from falcon_correlate import CorrelationIDMiddleware

app = falcon.App(middleware=[CorrelationIDMiddleware()])


class HelloResource:
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        resp.media = {"correlation_id": req.context.correlation_id}


app.add_route("/hello", HelloResource())
```

Every response now echoes the correlation ID in an `X-Correlation-ID` header,
and the resource reads the same value from `req.context.correlation_id`. The
[quickstart guide](docs/quickstart.md) builds this app up into a runnable
example with logging.

### ASGI application

```python
import falcon.asgi

from falcon_correlate import CorrelationIDMiddlewareASGI

app = falcon.asgi.App(middleware=[CorrelationIDMiddlewareASGI()])
```

The ASGI middleware exposes the same hooks as coroutines. Correlation IDs stay
request-local, so concurrent requests never observe each other's values.

### Configuration

Pass a `CorrelationIDConfig` when the defaults are not enough, or supply the
same settings as keyword arguments to either middleware:

```python
from falcon_correlate import CorrelationIDConfig, CorrelationIDMiddleware

config = CorrelationIDConfig(
    header_name="X-Correlation-ID",
    trusted_sources=["127.0.0.1", "10.0.0.0/8"],
    echo_header_in_response=True,
)
middleware = CorrelationIDMiddleware(config=config)
```

`trusted_sources` accepts individual Internet Protocol (IP) addresses and
Classless Inter-Domain Routing (CIDR) ranges alike. The
[user's guide](docs/users-guide.md) documents every option, including custom
`generator` and `validator` callables.

______________________________________________________________________

## Logging

`ContextualLogFilter` copies the active correlation ID, and the user ID when
`user_id_var` is set, onto every log record. `RECOMMENDED_LOG_FORMAT` renders
both fields:

```python
import logging

from falcon_correlate import RECOMMENDED_LOG_FORMAT, ContextualLogFilter

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter(RECOMMENDED_LOG_FORMAT))
handler.addFilter(ContextualLogFilter())
logger.addHandler(handler)

logger.info("handled request")  # the line carries the active correlation ID
```

A field with no value in context renders as `-`. The user's guide also covers
`dictConfig` wiring and a structlog processor pattern.

______________________________________________________________________

## Outbound HTTP calls

Install the extra where requests are made:

```bash
pip install "falcon-correlate[httpx]"
```

`request_with_correlation_id` is a drop-in replacement for `httpx.request` that
adds the correlation header while a request context is active:

```python
from falcon_correlate import request_with_correlation_id

response = request_with_correlation_id("GET", "https://api.example.com/data")
```

`async_request_with_correlation_id` is the async counterpart. For shared
clients, wrap the transport instead, so every request is annotated
automatically:

```python
import httpx

from falcon_correlate import CorrelationIDTransport

base_transport = httpx.HTTPTransport()

with httpx.Client(transport=CorrelationIDTransport(base_transport)) as client:
    response = client.get("https://api.example.com/data")
```

`AsyncCorrelationIDTransport` does the same for `httpx.AsyncClient`. A
correlation header that the caller sets explicitly is always preserved.

______________________________________________________________________

## Celery tasks

Install the extra in every process that publishes or executes tasks:

```bash
pip install "falcon-correlate[celery]"
```

The `celery` extra installs Celery itself, not a broker transport. Install the
transport package for the broker you use alongside it; the example below
publishes to Redis, which needs `pip install "celery[redis]"`.

Register the signal handlers when the Celery application is created:

```python
from celery import Celery

from falcon_correlate import configure_celery_correlation

celery_app = configure_celery_correlation(
    Celery("myapp", broker="redis://localhost:6379/0"),
)
```

Publishing a task during a request copies the correlation ID into the task
message's `correlation_id`, and the worker restores it for the lifetime of the
task body. When the active application uses the `rpc://` result backend, the
handler instead leaves Celery's task-ID `correlation_id` in place, preserving
Celery's result retrieval contract:

```python
from falcon_correlate import correlation_id_var


@celery_app.task
def send_invoice_email(user_id: str) -> None:
    correlation_id = correlation_id_var.get()
    # log, call downstream services, or forward the task on
```

Importing `falcon_correlate` also registers the handlers when Celery is
installed, but the explicit `configure_celery_correlation` call is the
preferred form: it makes the integration visible where the application is
built. The worker context is reset after each task, so the next task never
inherits a stale ID.

______________________________________________________________________

## Learn more

- [Quickstart guide](docs/quickstart.md) — the tested path from an empty
  project to a Falcon WSGI app with correlation headers and logging.
- [User's guide](docs/users-guide.md) — the full configuration reference and
  the integration details for logging, structlog, `httpx`, and Celery.
- [Developer's guide](docs/developers-guide.md) — build, test, and release
  workflows for contributors.
- [Design document](docs/falcon-correlation-id-middleware-design.md) — the
  architecture and rationale behind the middleware.
- [Documentation contents](docs/contents.md) — the index of all project
  documentation.

______________________________________________________________________

## Licence

`falcon-correlate` is released under the ISC licence — see [licence](LICENSE)
for the full text.

______________________________________________________________________

## Contributing

Contributions are welcome. [AGENTS.md](AGENTS.md) describes the working
conventions, and the [developer's guide](docs/developers-guide.md) covers the
commit gates that every change must pass.
