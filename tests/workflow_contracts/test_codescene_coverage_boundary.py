"""Contracts for CV-005: a pull request must not reach CodeScene.

Four rules, each written from a failure this estate has already had.

**The boundary.** No workflow serving pull requests may carry a CodeScene
action, a `cs-coverage` command or the access token. On 2026-09-16 a floating
CLI version broke its cobertura parser, and every branch in this estate whose
pull requests ran the check step went red on code that had not changed. A
third party in the path of every review is a third party that can stop every
review. It is also unavailable to a fork, so the step it guards has always
been a gate that some pull requests silently skip.

**One publisher.** Exactly one push-to-main workflow uploads, and it says
`mode: upload` rather than inheriting it. The default is what separates that
lane from the `check` this repository no longer runs anywhere, and a boundary
resting on a default is a boundary nobody can read.

**A comparable baseline.** The pull-request lane's ratchet compares against
the baseline the publisher writes, so the two must measure the same thing.
A language or format that differs between them makes the comparison silently
meaningless rather than failing.

**A deterministic install.** Both lanes pin an action revision carrying the
CLI manifest. An allowlist, because Dependabot chooses from the whole history
and a list of known-bad pins can never be complete.

**Nothing left of the old checksum.** The manifest replaced a digest of the
installer script. No workflow may pass `installer-checksum`, read or refresh
the `CODESCENE_CLI_SHA256` variable that fed it, or reinstate the dispatch
that maintained that variable.
"""

from __future__ import annotations

import typing as typ

import pytest

from tests.workflow_contracts.codescene_lanes import (
    COVERAGE_ACTION,
    MANIFEST_PINNED,
    UPLOAD_ACTION,
    WORKFLOWS_DIR,
    codescene_mentions,
    is_publisher,
    parse,
    serves_pull_requests,
    steps_using,
    workflow_texts,
)
from tests.workflow_contracts.deprecated_checksum import (
    DEPRECATED_CHECKSUM_INPUT,
    DEPRECATED_DIGEST_VARIABLE,
    DIGEST_REFRESH_WORKFLOW,
    deprecated_digest_mentions,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc


@pytest.fixture(name="documents")
def fixture_documents() -> dict[str, dict]:
    """Return every workflow, parsed.

    Returns
    -------
    dict[str, dict]
        File name to parsed document.
    """
    return {name: parse(name, text) for name, text in workflow_texts().items()}


class TestCodeSceneCoverageBoundary:
    """CV-005's four rules, over this repository's own workflows."""

    def test_some_workflow_serves_pull_requests(
        self, documents: dict[str, dict]
    ) -> None:
        """The boundary rules below are about pull-request workflows.

        If none were found the rules would pass over an empty set and say
        nothing, which is indistinguishable from compliance. Asserted separately
        so that failure names the reader rather than the workflows.
        """
        serving = [
            name
            for name, document in documents.items()
            if serves_pull_requests(document)
        ]

        assert serving, (
            "no workflow declares a pull_request trigger; the reader derives the "
            "boundary's subject from the triggers, so an empty set means the "
            "reader is broken rather than that the repository is compliant"
        )

    def test_no_pull_request_workflow_reaches_codescene(
        self, documents: dict[str, dict]
    ) -> None:
        """CV-005's boundary, asserted over the raw text.

        Read from the text rather than the parsed document because a mention can
        sit in a `run:` script, an `env:` value or an action input, and a walk
        reading only the shapes it expects misses whichever one is used next.
        """
        texts = workflow_texts()
        for name, document in documents.items():
            if not serves_pull_requests(document):
                continue
            mentions = codescene_mentions(texts[name])
            assert not mentions, (
                f"{name} serves pull requests and names {mentions}. A pull "
                f"request must not reach CodeScene: the CLI is a third party in "
                f"the path of every review, and a fork cannot obtain the token, "
                f"so the step is a gate that some pull requests skip. Coverage is "
                f"generated here and compared against the local ratchet; "
                f"publication belongs to the push-to-main lane"
            )

    def test_exactly_one_push_lane_uploads(self, documents: dict[str, dict]) -> None:
        """One publisher, and it states its mode.

        Two would upload the same commit twice and race on the ratchet baseline.
        None would leave CodeScene reading nothing while every other rule here
        passed, which is why the count is asserted in both directions.
        """
        uploads = [
            (name, job, ref, inputs)
            for name, document in documents.items()
            if is_publisher(document)
            for job, ref, inputs in steps_using(document, UPLOAD_ACTION)
        ]

        assert len(uploads) == 1, (
            f"exactly one push-to-main workflow must upload coverage; "
            f"{len(uploads)} do: {[(name, job) for name, job, _, _ in uploads]}"
        )
        name, job, ref, inputs = uploads[0]
        assert inputs.get("mode") == "upload", (
            f"{name}:{job} leaves mode at {inputs.get('mode')!r}. State it: "
            f"`upload` is the action's default, and the default is what separates "
            f"this lane from the `check` this repository no longer runs anywhere"
        )
        assert ref in MANIFEST_PINNED, (
            f"{name}:{job} pins {UPLOAD_ACTION} at {ref[:8]}, which is not on the "
            f"list of revisions verified to carry the CLI manifest. An older pin "
            f"installs a floating cs-coverage, which is what broke this estate's "
            f"lanes on 2026-09-16. Confirm the pin carries the manifest, then add "
            f"it to MANIFEST_PINNED rather than widening the rule"
        )

    def test_no_upload_runs_outside_the_push_lane(
        self, documents: dict[str, dict]
    ) -> None:
        """The publisher is the only place the upload action appears.

        The boundary rule above reads pull-request workflows. A scheduled or
        dispatch-only workflow is neither, and would carry the token past both
        rules without this one.

        `ci.yml` declares both `push` to main and `pull_request`, which is why
        the publisher is "pushes to main and serves no pull request" rather than
        "pushes to main": the looser reading would require `ci.yml` to upload
        and forbid it from uploading at the same time.
        """
        for name, document in documents.items():
            if is_publisher(document):
                continue
            assert not steps_using(document, UPLOAD_ACTION), (
                f"{name} invokes {UPLOAD_ACTION} and is not the push-to-main "
                f"publisher; this repository talks to CodeScene from one lane"
            )

    def test_the_pull_request_lane_measures_without_publishing(
        self, documents: dict[str, dict]
    ) -> None:
        """Ratchet on, artefact off, and the language stated.

        `publish-artefact: 'false'` is the only part of this boundary observable
        in the workflow file at all: the action archives the report under a step
        of its own, which no scanner over these steps can see.
        """
        found = [
            (name, job, ref, inputs)
            for name, document in documents.items()
            if serves_pull_requests(document)
            for job, ref, inputs in steps_using(document, COVERAGE_ACTION)
        ]

        assert len(found) == 1, (
            f"exactly one pull-request lane must generate coverage; {len(found)} do"
        )
        name, job, ref, inputs = found[0]
        assert inputs.get("with-ratchet") == "true", (
            f"{name}:{job} sets with-ratchet to {inputs.get('with-ratchet')!r}. "
            f"The ratchet is the whole gate on this lane now that the CodeScene "
            f"check is gone; without it the lane measures and asserts nothing"
        )
        assert inputs.get("publish-artefact") == "false", (
            f"{name}:{job} sets publish-artefact to "
            f"{inputs.get('publish-artefact')!r}. This lane does not publish, and "
            f"the archive step is inside the action where nothing here can see it"
        )
        assert inputs.get("language") == "python", (
            f"{name}:{job} leaves language at {inputs.get('language')!r}. State "
            f"it: `auto` reads the manifests, so a repository that acquires a "
            f"Cargo.toml would silently change what this lane measures"
        )
        assert ref in MANIFEST_PINNED, (
            f"{name}:{job} pins {COVERAGE_ACTION} at {ref[:8]}, which is not on "
            f"the list of revisions verified to carry the CLI manifest"
        )

    def test_the_publisher_measures_what_the_ratchet_compares_against(
        self, documents: dict[str, dict]
    ) -> None:
        """The baseline and the comparison must be the same measurement.

        A language or format differing between the two lanes makes the ratchet
        compare a number against one that was never comparable, and nothing
        fails: the ratchet reports a change in coverage that is really a change
        in what was measured.
        """

        def selection(chosen: cabc.Callable[[dict], bool]) -> dict[str, object]:
            rows = [
                inputs
                for document in documents.values()
                if chosen(document)
                for _job, _ref, inputs in steps_using(document, COVERAGE_ACTION)
            ]
            assert len(rows) == 1
            return {
                key: rows[0].get(key) for key in ("language", "format", "with-ratchet")
            }

        assert selection(serves_pull_requests) == selection(is_publisher), (
            "the pull-request lane and the publisher must measure the same thing, "
            "because the ratchet on the first compares against the baseline "
            "written by the second"
        )


class TestTheRetiredInstallerChecksum:
    """Nothing may pass, read, or refresh the retired digest again."""

    def test_no_workflow_passes_the_deprecated_installer_checksum(self) -> None:
        """Refuse the input the upload action rejects outright.

        At every pin in `MANIFEST_PINNED` a non-empty `installer-checksum`
        exits the action with a hard failure. This repository already passes
        nothing, so the rule guards a state rather than repairing one: the
        input's name still reads as an ordinary option, and re-adding it
        would go unremarked until a run that carried a value.
        """
        offending = {
            name: mentions
            for name, text in workflow_texts().items()
            if (mentions := deprecated_digest_mentions(text))
            and DEPRECATED_CHECKSUM_INPUT in mentions
        }

        assert not offending, (
            f"{DEPRECATED_CHECKSUM_INPUT} is rejected when non-empty; the "
            f"pinned manifest is the trust anchor and archive-checksum can "
            f"only repeat its digest: {offending}"
        )

    def test_no_workflow_reads_or_refreshes_the_digest_variable(self) -> None:
        """Leave no workflow maintaining a value nothing consumes.

        `installer-checksum` was the variable's only consumer. A workflow
        still reading it feeds a rejected input, which fails only when the
        action runs; one still refreshing it maintains dead state, which
        never fails at all and so is invisible without this rule.
        """
        offending = {
            name: mentions
            for name, text in workflow_texts().items()
            if (mentions := deprecated_digest_mentions(text))
            and DEPRECATED_DIGEST_VARIABLE in mentions
        }

        assert not offending, (
            f"no workflow may read or refresh {DEPRECATED_DIGEST_VARIABLE}; "
            f"the pinned action installs the CLI from its own manifest: "
            f"{offending}"
        )

    def test_the_digest_refresh_workflow_is_absent(self) -> None:
        """Keep the dispatch that wrote the dead variable out of the tree.

        Asserted by path rather than through the reader, because the reader
        answers questions about the workflows that exist and this rule is
        about one that must not. A dispatch-only workflow never runs on its
        own, so its return would show up in no run at all.
        """
        assert not (WORKFLOWS_DIR / DIGEST_REFRESH_WORKFLOW).exists(), (
            f"{DIGEST_REFRESH_WORKFLOW} refreshed {DEPRECATED_DIGEST_VARIABLE}, "
            f"which no workflow reads; delete it rather than leaving a "
            f"dispatch that maintains an unused repository variable"
        )
