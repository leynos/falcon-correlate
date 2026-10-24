"""A fork-fallback guard without the Dependabot author test is not the fallback.

Split from `test_runner_placement` to keep that module under the 400-line
limit.
"""

from __future__ import annotations

import pytest

from tests.workflow_contracts.runner_lanes import FORK_FALLBACK


@pytest.mark.parametrize(
    "guard",
    [
        "github.event.pull_request.head.repo.fork",
        (
            "(github.event.pull_request.head.repo.fork"
            " || github.actor == 'dependabot[bot]')"
        ),
    ],
    ids=["fork-only", "actor-instead-of-author"],
)
def test_a_guard_without_the_dependabot_author_test_is_not_the_fallback(
    guard: str,
) -> None:
    """Refuse the fork-only guard and the `github.actor` stand-in.

    The fallback is read in one form: the fork field or the Dependabot author.
    A guard that omits the author sends Dependabot's pull requests to the paid
    runner, and `github.actor` is whoever triggered the run, so a person
    pushing to a Dependabot branch would flip the runner.
    """
    runs_on = "${{ " + guard + " && 'ubuntu-latest' || 'ubicloud-standard-2' }}"
    assert FORK_FALLBACK.match(runs_on) is None, f"{runs_on!r} was read as the fallback"
