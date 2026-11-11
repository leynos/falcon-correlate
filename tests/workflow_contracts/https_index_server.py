"""A throwaway HTTPS server for exercising real curl download behaviour.

The recorder stand-ins prove the arguments the downloader passes to curl. This
server proves what curl then does with them: it speaks TLS on the loopback
interface with a certificate generated for the test, records every request
path, and returns scripted bodies or statuses.
"""

from __future__ import annotations

import http.server
import shutil
import ssl
import subprocess  # ruff: ignore[suspicious-subprocess-import] - generates test certificates with the checked-in toolchain.
import threading
import typing as typ

if typ.TYPE_CHECKING:
    from pathlib import Path


def _generate_certificate(directory: Path) -> Path:
    """Write a one-day self-signed certificate for ``127.0.0.1``."""
    openssl = shutil.which("openssl")
    if openssl is None:
        msg = "openssl is required to generate the test certificate"
        raise RuntimeError(msg)
    directory.mkdir(parents=True, exist_ok=True)
    key = directory / "key.pem"
    certificate = directory / "certificate.pem"
    subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - fixed argv names the resolved OpenSSL executable.
        [
            openssl,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(certificate),
            "-days",
            "1",
            "-subj",
            "/CN=127.0.0.1",
            "-addext",
            "subjectAltName=IP:127.0.0.1",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return certificate


class _RecordingServer(http.server.ThreadingHTTPServer):
    """Threading HTTPS server carrying its scripted answer and request log."""

    def __init__(
        self,
        address: tuple[str, int],
        handler: type[http.server.BaseHTTPRequestHandler],
        *,
        status: int,
        body: bytes,
    ) -> None:
        super().__init__(address, handler)
        self.requests: list[str] = []
        self.status = status
        self.body = body


class _RecordingHandler(http.server.BaseHTTPRequestHandler):
    """Record one request path and answer with the server's scripted response."""

    def do_GET(self) -> None:
        """Record the request path and write the scripted response."""
        server = typ.cast("_RecordingServer", self.server)
        server.requests.append(self.path)
        body = server.body
        self.send_response(server.status)
        self.send_header("Content-Type", "application/vnd.pypi.simple.v1+json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(
        self,
        format: str,  # ruff: ignore[builtin-argument-shadowing] - matches the base signature.
        *args: object,
    ) -> None:
        """Suppress per-request logging so test output stays readable."""
        del format, args


class LocalHttpsServer:
    """A loopback HTTPS server that records requests and serves one response.

    Parameters
    ----------
    directory : pathlib.Path
        Directory in which to generate the test certificate and key.

    Examples
    --------
    >>> server = LocalHttpsServer(tmp_path)  # doctest: +SKIP
    >>> server.respond(status=200, body=b"{}")  # doctest: +SKIP
    >>> server.url.startswith("https://127.0.0.1:")  # doctest: +SKIP
    True
    """

    def __init__(self, directory: Path) -> None:
        self.certificate = _generate_certificate(directory)
        key = directory / "key.pem"
        self._server = _RecordingServer(
            ("127.0.0.1", 0), _RecordingHandler, status=200, body=b""
        )
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=self.certificate, keyfile=key)
        self._server.socket = context.wrap_socket(self._server.socket, server_side=True)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def url(self) -> str:
        """The server's base HTTPS URL.

        Returns
        -------
        str
            Base URL ending in a slash, for example ``https://127.0.0.1:8000/``.
        """
        host, port = self._server.server_address[:2]
        return f"https://{host}:{port}/"

    @property
    def requests(self) -> list[str]:
        """Request paths seen so far, in arrival order.

        Returns
        -------
        list of str
            Raw request targets recorded by the handler.
        """
        return self._server.requests

    def respond(self, *, status: int, body: bytes) -> None:
        """Serve ``body`` with ``status`` for subsequent requests.

        Parameters
        ----------
        status : int
            HTTP status code to return.
        body : bytes
            Response body to write for every subsequent request.
        """
        self._server.status = status
        self._server.body = body

    def stop(self) -> None:
        """Stop serving, close the socket, and join the server thread."""
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
