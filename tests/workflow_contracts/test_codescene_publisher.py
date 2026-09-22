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
from tests.workflow_contracts.guard_conditions import conjuncts

MAIN_REF = "github.ref == 'refs/heads/main'"
SKIP_WITHOUT_CREDENTIAL = "env.CS_ACCESS_TOKEN != ''"


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


class TestTrunkGenerations:
    """Trunk generations queue; none is cancelled."""

    def test_the_publisher_queues_and_never_cancels(
        self, publisher: tuple[str, dict]
    ) -> None:
        """A cancelled trunk run abandons its upload and its baseline write.

        Two running at once let the older commit finish last and leave its
        baseline as the newest. A group per ref with cancellation off queues
        them instead.
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
