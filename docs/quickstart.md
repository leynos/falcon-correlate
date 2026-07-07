# Quickstart

This tutorial builds a small Falcon Web Server Gateway Interface (WSGI)
application that adds a correlation ID to each response and includes the same
ID in standard-library log output.

## Install

Create a project and install `falcon-correlate` with a WSGI server:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install falcon-correlate gunicorn
```

## Minimal application

Create `app.py` and start with the imports:

<!-- quickstart:minimal-imports -->

```python
import falcon

from falcon_correlate import CorrelationIDMiddleware
```

Add one Falcon resource:

<!-- quickstart:minimal-resource -->

```python
class HelloResource:
    """Return a small JSON response.

    Examples
    --------
    >>> resource = HelloResource()
    >>> resource.message
    'hello'
    """

    message: str = "hello"

    def on_get(self, _req: falcon.Request, resp: falcon.Response) -> None:
        """Handle ``GET /hello``.

        Parameters
        ----------
        _req : falcon.Request
            The incoming Falcon request.
        resp : falcon.Response
            The Falcon response to populate.

        Returns
        -------
        None
            This handler only mutates ``resp``.

        Examples
        --------
        >>> resource = HelloResource()
        >>> hasattr(resource, "on_get")
        True
        """
        resp.media = {"message": self.message}
```

Create the Falcon app with the middleware and route the resource:

<!-- quickstart:minimal-app -->

```python
app: falcon.App = falcon.App(middleware=[CorrelationIDMiddleware()])
app.add_route("/hello", HelloResource())
```

Run it:

```bash
gunicorn app:app
```

In another shell, request the endpoint:

```bash
curl -i http://127.0.0.1:8000/hello
```

The response includes a generated `X-Correlation-ID` header and the JSON body:

```http
HTTP/1.1 200 OK
X-Correlation-ID: 019b...

{"message": "hello"}
```

## Common configuration

Use `CorrelationIDConfig` when the application needs to make the header name,
trusted sources, and response echoing policy explicit:

Add the configuration import to the same `app.py` file used above:

```python
from falcon_correlate import CorrelationIDConfig
```

<!-- quickstart:configured-config -->

```python
config = CorrelationIDConfig(
    header_name="X-Correlation-ID",
    trusted_sources=frozenset({"127.0.0.1"}),
    echo_header_in_response=True,
)
```

Wire the config into the middleware:

<!-- quickstart:configured-app -->

```python
def build_app(app_config: CorrelationIDConfig) -> falcon.App:
    """Create the configured Falcon app.

    Parameters
    ----------
    app_config : CorrelationIDConfig
        Correlation-ID middleware configuration for the app.

    Returns
    -------
    falcon.App
        The configured Falcon application.

    Examples
    --------
    >>> configured = build_app(config)
    >>> isinstance(configured, falcon.App)
    True
    """
    configured_app = falcon.App(
        middleware=[CorrelationIDMiddleware(config=app_config)],
    )
    configured_app.add_route("/hello", HelloResource())
    return configured_app


app: falcon.App = build_app(config)
```

Requests from `127.0.0.1` may now provide an incoming `X-Correlation-ID` value,
and the response echoes that same value:

```bash
curl -i -H 'X-Correlation-ID: cid-quickstart-1' http://127.0.0.1:8000/hello
```

## Logging

Configure a logger with `ContextualLogFilter` and `RECOMMENDED_LOG_FORMAT`:

Create `logging_setup.py` with the imports used by the logging example:

```python
import logging

from falcon_correlate import RECOMMENDED_LOG_FORMAT, ContextualLogFilter
```

<!-- quickstart:logging-config -->

```python
def configure_logging() -> logging.Logger:
    """Create a logger that includes correlation context.

    Returns
    -------
    logging.Logger
        Logger named ``quickstart`` with one stream handler, the recommended
        formatter, and the contextual logging filter attached.

    Notes
    -----
    The example clears existing handlers on the named logger so repeated
    quickstart runs do not duplicate output.

    Examples
    --------
    >>> logger = configure_logging()
    >>> logger.name
    'quickstart'
    """
    logger = logging.getLogger("quickstart")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(RECOMMENDED_LOG_FORMAT))
    handler.addFilter(ContextualLogFilter())
    logger.addHandler(handler)
    return logger
```

Then use the logger in request-handling code:

<!-- quickstart:logging-usage -->

```python
def log_request(logger: logging.Logger) -> None:
    """Log one example request event.

    Parameters
    ----------
    logger : logging.Logger
        Logger returned by ``configure_logging()``.

    Returns
    -------
    None
        The function emits a log record for its side effect.

    Examples
    --------
    >>> logger = configure_logging()
    >>> log_request(logger)
    """
    logger.info("handled request")
    return
```

When the middleware has established a request context, emitted log lines
include the active correlation ID. If no user ID has been set, the formatter
writes `-` for that field.

## Next steps

Use the [user's guide](users-guide.md) for the full configuration reference,
ASGI usage, outbound HTTP propagation, Celery propagation, and logging
integration details.
