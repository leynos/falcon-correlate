"""The runner labels ``act`` is told how to run, kept free of side effects.

Separated from the act integration tests for one reason: those tests probe
for ``act`` and Docker at import time and are excluded from CI, so a guard
living beside them could not run where it is needed. The mapping is
configuration, the probing is not, and only the mapping has to be readable
from a contract that runs on every pull request.

``act`` knows GitHub's own labels and skips any job whose label it cannot
map, printing ``Skipping unsupported platform`` and **exiting zero**. A
skipped job makes every assertion about its output fail, or pass vacuously,
for a reason that has nothing to do with the job. Removing a mapping is
therefore not a visible failure, which is why the contract next door asserts
the mapping directly rather than inferring it from a green act run.
"""

from __future__ import annotations

#: Runner label to container image, as ``act`` expects them.
#:
#: ``ubicloud-standard-2`` is an ordinary x86-64 Ubuntu runner, so it maps to
#: the same image as ``ubuntu-latest``. This mapping is about what ``act``
#: can run locally, not about what the lane bills for in CI.
ACT_PLATFORM_IMAGES: dict[str, str] = {
    "ubuntu-latest": "catthehacker/ubuntu:act-latest",
    "ubicloud-standard-2": "catthehacker/ubuntu:act-latest",
}

#: The message ``act`` prints instead of failing when a label is unmapped.
UNSUPPORTED_PLATFORM_MESSAGE = "Skipping unsupported platform"

#: The workflow the act harness runs. The mapping only has to cover the
#: labels this workflow's lanes resolve to; act is never pointed at the
#: others.
ACT_WORKFLOW = "ci.yml"

#: Platforms act cannot host at all, because it runs Linux containers.
#: Named rather than inferred: a lane in ``ACT_WORKFLOW`` moving to one of
#: these is not a missing mapping to add, it is a lane act can no longer
#: cover, and the contract must say which of the two happened.
UNHOSTABLE_PLATFORM_PREFIXES = ("windows-", "macos-")


def act_platform_arguments() -> tuple[str, ...]:
    """Return the mapping as ``act`` command-line arguments.

    Returns
    -------
    tuple[str, ...]
        ``-P label=image`` pairs, flattened.
    """
    arguments: list[str] = []
    for label, image in ACT_PLATFORM_IMAGES.items():
        arguments.extend(("-P", f"{label}={image}"))
    return tuple(arguments)
