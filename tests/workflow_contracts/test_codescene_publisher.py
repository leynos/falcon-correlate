"""Contracts on the one workflow allowed to contact CodeScene.

The boundary contracts clear everything a pull request can run. These hold
the publisher itself: the conditions its upload runs under, and whether two
trunk generations can overlap or be cancelled, and where the token is bound.
Each is a way CV-005 fails while every pull-request lane stays clean.
"""

from __future__ import annotations

import typing as typ

import pytest

from tests.workflow_contracts.codescene_lanes import (
    UPLOAD_ACTION,
    is_publisher,
    parse,
    steps_of,
    workflow_texts,
)
from tests.workflow_contracts.guard_conditions import admits, conjuncts

if typ.TYPE_CHECKING:
    import collections.abc as cabc

MAIN_REF = "github.ref == 'refs/heads/main'"

#: The publisher's credential check. It binds nothing and runs one command whose
#: expression GitHub evaluates before the shell starts, so the secret reaches no
#: process and no `env`; the upload consumes the output it writes.
CREDENTIAL_CHECK_ID = "codescene-token"
CREDENTIAL_CHECK_COMMAND = (
    'echo "available=${{ secrets.CS_ACCESS_TOKEN != \'\' }}" >> "$GITHUB_OUTPUT"'
)
CREDENTIAL_OUTPUT = f"steps.{CREDENTIAL_CHECK_ID}.outputs.available"
SKIP_WITHOUT_CREDENTIAL = f"{CREDENTIAL_OUTPUT} == 'true'"
CREDENTIAL_NAME = "CS_ACCESS_TOKEN"
CREDENTIAL_INPUT = "${{ secrets.CS_ACCESS_TOKEN }}"


def _start(event: str, ref: str, available: str) -> dict[str, str]:
    """Return the context a workflow started by *event* on *ref* evaluates in.

    Returns
    -------
    dict[str, str]
        The references the upload's guard reads. *available* is what the
        credential check wrote: ``'true'`` when the repository holds the
        secret, ``'false'`` when it does not.
    """
    return {"github.event_name": event, "github.ref": ref, CREDENTIAL_OUTPUT: available}


def _upload(document: dict) -> dict[str, typ.Any]:
    """Return the publisher's one upload step, failing if there is not one."""
    uploads = [
        step
        for _job, step in steps_of(document)
        if str(step.get("uses", "")).partition("@")[0] == UPLOAD_ACTION
    ]
    assert len(uploads) == 1, f"the publisher must upload exactly once; {uploads}"
    return uploads[0]


def _env_texts(value: object, *, under_env: bool = False) -> cabc.Iterator[str]:
    """Yield every key and scalar that sits beneath an ``env`` mapping."""
    match value:
        case dict():
            for key, entry in value.items():
                if under_env:
                    yield str(key)
                yield from _env_texts(entry, under_env=under_env or key == "env")
        case list():
            for entry in value:
                yield from _env_texts(entry, under_env=under_env)
        case _ if under_env:
            yield str(value)


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
            (_start("push", "refs/heads/main", "true"), True),
            (_start("workflow_dispatch", "refs/heads/main", "true"), True),
            (_start("workflow_dispatch", "refs/heads/feature", "true"), False),
            (_start("workflow_dispatch", "refs/tags/v1.0.0", "true"), False),
            (_start("push", "refs/heads/main", "false"), False),
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


class TestTheCredential:
    """The token is bound in no `env`, and the upload still cannot skip silently.

    The uploader is composite: it binds the token from its `access-token` input
    and hands a step's `env` to its nested upload-artifact and cache steps. A
    guard on `env.CS_ACCESS_TOKEN != ''` is simply false once the binding is
    deleted, and the upload then skips forever with nothing failing, so the
    check and the input are asserted positively.
    """

    def test_the_credential_check_is_one_exact_command(
        self, publisher: tuple[str, dict]
    ) -> None:
        """Require the check step with its command alone, no `if:` and no `env`.

        `false && X` contains X, so an `if:` could carry the command without
        running it, and an `env` would bind the secret this step exists not to.
        """
        name, document = publisher
        checks = [
            step
            for _job, step in steps_of(document)
            if step.get("id") == CREDENTIAL_CHECK_ID
        ]

        assert len(checks) == 1, (
            f"{name} must declare one step with id {CREDENTIAL_CHECK_ID!r}; "
            f"found {len(checks)}"
        )
        assert checks[0].get("run") == CREDENTIAL_CHECK_COMMAND, (
            f"{name}'s credential check must run exactly "
            f"{CREDENTIAL_CHECK_COMMAND!r}; it runs {checks[0].get('run')!r}"
        )
        assert set(checks[0]) <= {"name", "id", "run"}, (
            f"{name}'s credential check may carry only a name, its id and its "
            f"command; it declares {sorted(checks[0])}"
        )

    def test_the_upload_takes_the_secret_as_its_input(
        self, publisher: tuple[str, dict]
    ) -> None:
        """Pass the secret straight to `access-token`, not through `env`."""
        name, document = publisher
        inputs = _upload(document).get("with")

        assert isinstance(inputs, dict), f"{name}'s upload must declare inputs"
        assert inputs.get("access-token") == CREDENTIAL_INPUT, (
            f"{name}'s upload must pass {CREDENTIAL_INPUT!r} to access-token; "
            f"it passes {inputs.get('access-token')!r}"
        )

    def test_no_env_in_the_publisher_carries_the_token(
        self, publisher: tuple[str, dict]
    ) -> None:
        """Refuse the token in a workflow, job or step `env`, under any name."""
        name, document = publisher
        offending = [text for text in _env_texts(document) if CREDENTIAL_NAME in text]

        assert not offending, (
            f"{name} must bind {CREDENTIAL_NAME} in no env; the composite uploader "
            f"hands a step's env to its nested steps: {offending}"
        )
