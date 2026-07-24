"""Display interpreter path details for site-customization diagnostics."""

import sys
from pathlib import Path


def main() -> None:
    """Display interpreter path diagnostics."""
    print("sitecustomize_loaded", "sitecustomize" in sys.modules)
    print("cwd", Path.cwd())
    print("sys.path[:8]", sys.path[:8])


if __name__ == "__main__":
    main()
