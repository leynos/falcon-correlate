"""Static curl arguments for HTTPS-only release file operations.

Distribution downloads treat every URL from the Simple index as one literal
HTTPS location: ``--globoff`` stops curl expanding bracket ranges or brace
lists into further transfers. Curl still bounds each attempt and its retry
window, and the caller adds an overall Python-side deadline on the whole
subprocess.
"""

SIMPLE_INDEX_CURL_ARGUMENTS = (
    "curl",
    "--silent",
    "--show-error",
    "--location",
    "--proto",
    "=https",
    "--proto-redir",
    "=https",
    "--retry",
    "5",
    "--retry-all-errors",
    "--retry-delay",
    "2",
    "--retry-max-time",
    "90",
    "--connect-timeout",
    "10",
    "--max-time",
    "30",
    "--write-out",
    "\\n%{http_code}",
)

PYPI_DOWNLOAD_CURL_ARGUMENTS = (
    "curl",
    "--silent",
    "--show-error",
    "--location",
    "--globoff",
    "--proto",
    "=https",
    "--proto-redir",
    "=https",
    "--fail",
    "--retry",
    "5",
    "--retry-all-errors",
    "--retry-delay",
    "2",
    "--retry-max-time",
    "300",
    "--connect-timeout",
    "10",
    "--max-time",
    "300",
    "--output",
)
