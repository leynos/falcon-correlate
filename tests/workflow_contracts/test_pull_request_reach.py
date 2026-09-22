"""Drive the pull-request closure over documents built for each reading.

Nothing in this repository calls a local reusable workflow, and every workflow
declares its triggers in the mapping form, so a reader that followed no call
and understood one trigger form would pass over the real files. Each reading
and each refusal is proved here against a document carrying exactly its shape.
"""

from __future__ import annotations

import pytest

from tests.workflow_contracts.codescene_lanes import codescene_mentions, parse
from tests.workflow_contracts.errors import WorkflowReadError
from tests.workflow_contracts.guard_conditions import conjuncts
from tests.workflow_contracts.pull_request_reach import (
    inherited_secrets,
    local_calls,
    pull_request_closure,
    trigger_names,
)


def _caller(reference: str) -> dict[str, object]:
    """Return a workflow whose only job calls ``reference``."""
    return {"jobs": {"call": {"uses": reference}}}


class TestTriggerForms:
    """Every form GitHub accepts is read, and no other."""

    @pytest.mark.parametrize("key", [True, "on"], ids=["boolean key", "string key"])
    @pytest.mark.parametrize(
        ("declared", "expected"),
        [
            ("pull_request", {"pull_request"}),
            (["push", "pull_request"], {"push", "pull_request"}),
            (
                {"push": {"branches": ["main"]}, "pull_request_target": None},
                {"push", "pull_request_target"},
            ),
        ],
        ids=["scalar", "list", "mapping"],
    )
    def test_every_trigger_form_is_read(
        self, key: object, declared: object, expected: set[str]
    ) -> None:
        """A list form read as one stringified key escapes every rule."""
        found = trigger_names({key: declared}, "ci.yml")

        assert found == expected, f"{declared!r} must read as {expected}; got {found}"

    @pytest.mark.parametrize(
        "document",
        [{"jobs": {}}, {True: "push", "on": "pull_request"}, {True: []}, {True: 42}],
        ids=["absent", "both keys", "empty list", "number"],
    )
    def test_an_unreadable_trigger_block_is_refused(self, document: dict) -> None:
        """A workflow read as declaring nothing is cleared by every rule."""
        with pytest.raises(WorkflowReadError):
            trigger_names(document, "ci.yml")


class TestLocalCalls:
    """A same-repository call is recognized by where it resolves."""

    @pytest.mark.parametrize(
        "reference",
        [
            "./.github/workflows/called.yml",
            "./.github/workflows/../workflows/called.yml",
            "leynos/falcon-correlate/.github/workflows/called.yml@main",
        ],
    )
    def test_a_local_call_is_followed_by_shape(self, reference: str) -> None:
        """Follow any spelling that resolves into the workflow directory."""
        found = local_calls(_caller(reference), {"called.yml"}, "ci.yml")

        assert found == {"called.yml"}, f"{reference!r} must be followed; got {found}"

    def test_a_remote_reusable_workflow_is_not_followed(self) -> None:
        """Its text is not here; the caller's `secrets:` decides what it gets."""
        reference = "leynos/shared-actions/.github/workflows/x.yml@" + "0" * 40

        found = local_calls(_caller(reference), {"x.yml"}, "ci.yml")

        assert found == frozenset(), f"a remote call must not be followed; got {found}"

    def test_a_step_level_uses_is_not_a_call(self) -> None:
        """A step runs an action; only a job calls a workflow."""
        document = {
            "jobs": {"a": {"steps": [{"uses": "./.github/workflows/called.yml"}]}}
        }

        found = local_calls(document, {"called.yml"}, "ci.yml")

        assert found == frozenset(), f"a step-level uses is not a call; got {found}"

    @pytest.mark.parametrize(
        "reference",
        [
            "$/.github/workflows/called.yml",
            "called.yml",
            "./.github/workflows/absent.yml",
        ],
        ids=["unknown prefix", "bare name", "missing file"],
    )
    def test_an_unplaceable_call_is_refused(self, reference: str) -> None:
        """Skipping it would drop the callee from the closure in silence."""
        with pytest.raises(WorkflowReadError):
            local_calls(_caller(reference), {"called.yml"}, "ci.yml")


class TestTheClosure:
    """The boundary's subject is everything a pull request can run."""

    def test_the_closure_follows_calls_transitively(self) -> None:
        """Reach a workflow only a called workflow calls, and nothing else."""
        documents = {
            "entry.yml": {
                True: "pull_request",
                **_caller("./.github/workflows/middle.yml"),
            },
            "middle.yml": {
                True: "workflow_call",
                **_caller("./.github/workflows/leaf.yml"),
            },
            "leaf.yml": {True: "workflow_call", "jobs": {}},
            "nightly.yml": {True: {"schedule": None}, "jobs": {}},
        }

        reached = pull_request_closure(documents)

        assert reached == {"entry.yml", "middle.yml", "leaf.yml"}, (
            f"the closure must reach the chain and nothing else; got {sorted(reached)}"
        )

    def test_a_pull_request_target_workflow_is_an_entry_point(self) -> None:
        """Start from `pull_request_target` too; it runs with the base secrets."""
        documents = {"automerge.yml": {True: {"pull_request_target": None}, "jobs": {}}}

        reached = pull_request_closure(documents)

        assert reached == {"automerge.yml"}, (
            f"a pull_request_target workflow is reachable; got {sorted(reached)}"
        )

    def test_the_closure_reaches_a_called_workflows_codescene_contact(self) -> None:
        """The probe that measured the hole elsewhere in the estate.

        A `workflow_call`-only workflow, called from a pull-request job with
        `secrets: inherit`, curling the CodeScene API with the inherited
        token. By triggers alone the called workflow is not a pull-request
        workflow, so every clause passes over it.
        """
        caller = (
            "on: pull_request\n"
            "jobs:\n"
            "  call:\n"
            "    uses: ./.github/workflows/helper.yml\n"
            "    secrets: inherit\n"
        )
        helper = (
            "on: workflow_call\n"
            "jobs:\n"
            "  probe:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: >-\n"
            '          curl -H "Authorization: Bearer ${{ secrets.CS_ACCESS_TOKEN }}"\n'
            "          https://api.codescene.io/v2/projects\n"
        )
        texts = {"gate.yml": caller, "helper.yml": helper}
        documents = {name: parse(name, text) for name, text in texts.items()}

        reached = pull_request_closure(documents)

        assert reached == {"gate.yml", "helper.yml"}, (
            f"the closure must include the called workflow; got {sorted(reached)}"
        )
        assert codescene_mentions(texts["helper.yml"]), (
            "the called workflow's token and host must be found"
        )
        assert inherited_secrets(documents["gate.yml"]) == ["call"], (
            "the caller's secrets: inherit must be found"
        )


class TestStrictParsing:
    """A document PyYAML would misread is refused."""

    @pytest.mark.parametrize(
        "text",
        [
            (
                "jobs:\n  a:\n    env:\n"
                "      CS_ACCESS_TOKEN: x\n      CS_ACCESS_TOKEN: ''\n"
            ),
            "? [a, b]\n: value\n",
        ],
        ids=["repeated key", "list as key"],
    )
    def test_a_document_pyyaml_would_misread_is_refused(self, text: str) -> None:
        """PyYAML keeps the last of two equal keys, so a token could hide."""
        with pytest.raises(WorkflowReadError, match=r"ci\.yml"):
            parse("ci.yml", text)


class TestGuardConjuncts:
    """A guard is read as the conjunction GitHub evaluates."""

    def test_a_folded_guard_splits_into_its_conjuncts(self) -> None:
        """Read a multi-line guard as its conjuncts."""
        found = conjuncts(
            "${{ github.ref == 'refs/heads/main'\n && env.T != '' }}", "x"
        )

        assert found == ["github.ref == 'refs/heads/main'", "env.T != ''"], (
            f"the guard must split into its two conjuncts; got {found}"
        )

    @pytest.mark.parametrize(
        "condition",
        [
            (
                "github.ref == 'refs/heads/main' || "
                "github.event_name == 'workflow_dispatch'"
            ),
            "github.ref == 'refs/heads/main' && (env.T != '')",
            "!cancelled()",
            "github.ref == 'refs/heads/main' && ",
        ],
        ids=["disjunction", "group", "negation", "empty conjunct"],
    )
    def test_a_form_that_is_not_a_conjunction_is_refused(self, condition: str) -> None:
        """Refuse rather than approximate; the disjunction is the case."""
        with pytest.raises(WorkflowReadError):
            conjuncts(condition, "x")

    def test_operators_inside_a_literal_are_data(self) -> None:
        """A quoted literal spelling an operator is not an operator."""
        assert conjuncts("env.A == '||(!)'", "x") == ["env.A == '||(!)'"], (
            "operators inside a quoted literal must not be read"
        )
