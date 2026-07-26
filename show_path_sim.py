"""Display interpreter path details for site-customization diagnostics."""

import sys
from pathlib import Path


def main() -> None:
    """Display interpreter path diagnostics.

    Prints site-customisation diagnostics for the interpreter path: whether
    ``sitecustomize`` has been loaded, the current working directory, and
    the first eight entries of ``sys.path``. The function returns nothing; it
    produces console output as a side effect only.

    """
    print("sitecustomize_loaded", "sitecustomize" in sys.modules)
    print("cwd", Path.cwd())
    print("sys.path[:8]", sys.path[:8])


if __name__ == "__main__":
    main()
