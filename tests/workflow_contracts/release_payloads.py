"""Shared release workflow response data for command stand-ins."""

from __future__ import annotations

import hashlib
import json

TAG = "v1.2.0"
WHEEL = "falcon_correlate-1.2.0-py3-none-any.whl"
SDIST = "falcon_correlate-1.2.0.tar.gz"
BUNDLE = f"{TAG}.sigstore.json"
BUNDLE_BYTES = b"attestation bundle"
SIMPLE_URL = "https://pypi.org/simple/falcon-correlate/"


def sha256(content: bytes) -> str:
    """Return a SHA-256 digest for fixture bytes."""
    return hashlib.sha256(content).hexdigest()


def simple_body(files: dict[str, bytes]) -> str:
    """Build a PEP 691 response for fixture files."""
    return json.dumps({
        "files": [
            {
                "filename": name,
                "hashes": {"sha256": sha256(content)},
                "url": f"https://files.pythonhosted.org/{name}",
            }
            for name, content in files.items()
        ]
    })


def release_view(files: dict[str, bytes], names: tuple[str, ...] | None = None) -> str:
    """Build a GitHub Release view for selected fixture assets."""
    if names is None:
        names = tuple(files)
    return json.dumps({
        "assets": [
            {"name": name, "digest": f"sha256:{sha256(files[name])}"} for name in names
        ]
    })
