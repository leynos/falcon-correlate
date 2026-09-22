"""Contracts on the one workflow allowed to contact CodeScene.

The boundary contracts clear everything a pull request can run. These hold
the publisher itself: the conditions its upload runs under, and whether two
trunk generations can overlap or be cancelled. Each is a way CV-005 fails
while every pull-request lane stays clean.
"""

from __future__ import annotations

import pytest

from tests.workflow_contracts.codescene_lanes import (
    UPLOAD_ACTION,
    is_publisher,
    parse,
    steps_of,
    workflow_texts,
)
from tests.workflow_contracts.guard_conditions import admits, conjuncts

MAIN_REF = "github.ref == 'refs/heads/main'"
SKIP_WITHOUT_CREDENTIAL = "env.CS_ACCESS_TOKEN != ''"


def _start(event: str, ref: str, token: str) -> dict[str, str]:
    """Return the context a workflow started by *event* on *ref* evaluates in."""
    return {"github.event_name": event, "github.ref": ref, "env.CS_ACCESS_TOKEN": token}


@pytest.fixture(name="publisher")
def fixture_publisher() -> tuple[str, dict]:
    """Return the one push-to-main publisher, by name and document.

    Returns
    -------
    tuple[str, dict]
        The publisher's file name and parsed document.
    """
    documents = {name: parse(name, text) for name, text in workflow_texts().items()}
    publishers = [
        name for name, document in documents.items() if is_publisher(document)
    ]
    assert len(publishers) == 1, f"exactly one publisher must exist; {publishers}"
    return publishers[0], documents[publishers[0]]


class TestTheUploadGuard:
    """The upload runs for the trunk only, whatever event started it."""

    def test_the_upload_guard_holds_the_main_ref_as_a_conjunct(
        self, publisher: tuple[str, dict]
    ) -> None:
        """Require the ref clause as a conjunct, and refuse any disjunction.

        `workflow_dispatch` can select any branch or tag, and the push
        trigger's branch filter says nothing about a dispatch. A substring
        check would pass `... && github.ref == 'refs/heads/main' ||
        github.event_name == 'workflow_dispatch'`, which lets every dispatch
        through; reading the guard as conjuncts refuses the `||` outright.
        """
        name, document = publisher
        guards = [
            str(step.get("if", ""))
            for job, step in steps_of(document)
            if str(step.get("uses", "")).partition("@")[0] == UPLOAD_ACTION
        ]

        assert len(guards) == 1, f"{name} must upload exactly once; {len(guards)} do"
        found = conjuncts(guards[0], name)
        assert MAIN_REF in found, (
            f"{name}'s upload must carry {MAIN_REF!r} as a conjunct; it has {found}"
        )
        assert SKIP_WITHOUT_CREDENTIAL in found, (
            f"{name}'s upload must skip when the token is absent; it has {found}"
        )

    @pytest.mark.parametrize(
        ("context", "expected"),
        [
            (_start("push", "refs/heads/main", "set"), True),
            (_start("workflow_dispatch", "refs/heads/main", "set"), True),
            (_start("workflow_dispatch", "refs/heads/feature", "set"), False),
            (_start("workflow_dispatch", "refs/tags/v1.0.0", "set"), False),
            (_start("push", "refs/heads/main", ""), False),
        ],
        ids=[
            "push to main",
            "dispatch on main",
            "dispatch on a branch",
            "dispatch on a tag",
            "no token",
        ],
    )
    def test_the_upload_runs_only_for_the_trunk(
        self, publisher: tuple[str, dict], context: dict[str, str], expected: object
    ) -> None:
        """Evaluate the guard for each way the workflow can be started.

        The behavioural question a workflow runner would answer, asked of the
        guard as GitHub evaluates it.
        """
        name, document = publisher
        guard = next(
            str(step.get("if", ""))
            for _job, step in steps_of(document)
            if str(step.get("uses", "")).partition("@")[0] == UPLOAD_ACTION
        )

        assert admits(guard, context, name) is expected, (
            f"{name}'s upload must {'run' if expected else 'not run'} in {context}"
        )


class TestTrunkGenerations:
    """Trunk runs never overlap, and a running one is never cancelled."""

    def test_the_publisher_never_overlaps_or_cancels_a_running_generation(
        self, publisher: tuple[str, dict]
    ) -> None:
        """A cancelled running generation abandons its upload and baseline.

        Two running at once would let the older commit finish last and leave
        its baseline as the newest. A group per ref with cancellation off
        prevents both. It is not a durable queue: GitHub keeps one pending
        run per group, so a newer push replaces an older pending one. That
        skips an intermediate commit's publication, which is the right
        outcome, because the newest commit's baseline is the one pull
        requests should read.
        """
        name, document = publisher
        declared = document.get("concurrency")

        assert isinstance(declared, dict), (
            f"{name} must declare a concurrency group; it declares {declared!r}"
        )
        assert declared.get("cancel-in-progress") is False, (
            f"{name} must never cancel a trunk generation; it declares "
            f"cancel-in-progress={declared.get('cancel-in-progress')!r}"
        )
        assert "github.ref" in str(declared.get("group")), (
            f"{name}'s group must be keyed on the ref, so pushes to main queue "
            f"behind one another; it declares {declared.get('group')!r}"
        )
