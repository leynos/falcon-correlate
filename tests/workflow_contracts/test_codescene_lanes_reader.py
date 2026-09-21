"""Direct tests for the CodeScene boundary reader's refusals and its shapes.

The contracts next door read this repository's own seven workflows, which are
correct, so they pass whether or not the reader discriminates anything. These
tests drive the reader over documents built here, including shapes this
repository does not contain.

Trigger spelling gets its own group. Every workflow here uses the mapping form,
so the string and list arms of `serves_pull_requests` are unreachable from the
real files, and the boundary's whole subject is derived from that function: a
reader that answered `False` for a spelling in use would make the boundary
rules pass over an empty set rather than fail.
"""

from __future__ import annotations

import typing as typ

import pytest

from tests.workflow_contracts.codescene_lanes import (
    COVERAGE_ACTION,
    UPLOAD_ACTION,
    WorkflowContractError,
    WorkflowReadError,
    codescene_mentions,
    is_publisher,
    parse,
    pushes_to_main,
    serves_pull_requests,
    steps_of,
    steps_using,
    workflow_texts,
)
from tests.workflow_contracts.deprecated_checksum import deprecated_digest_mentions

if typ.TYPE_CHECKING:
    from pathlib import Path


class TestReaderRefusals:
    """Each refusal, shown to fire on the shape it names."""

    def test_a_missing_directory_is_refused_rather_than_empty(
        self, tmp_path: Path
    ) -> None:
        """An absent directory must raise, not glob to nothing.

        `Path.glob` on a directory that is not there yields no paths and no
        error, so the reader would return an empty mapping and every rule
        over "every workflow" would pass over no workflows at all. That is
        the failure this refusal exists for, and it is silent without it.
        """
        with pytest.raises(WorkflowReadError, match="not a readable workflow"):
            workflow_texts(tmp_path / "absent")

    def test_a_path_to_a_file_is_refused(self, tmp_path: Path) -> None:
        """A file reads as a directory to nobody, so say so."""
        target = tmp_path / "ci.yml"
        target.write_text("jobs: {}\n", encoding="utf-8")
        with pytest.raises(WorkflowReadError, match="not a readable workflow"):
            workflow_texts(target)

    def test_a_file_that_is_not_utf8_is_refused_by_name(self, tmp_path: Path) -> None:
        """The failure names the file, because the directory holds several."""
        (tmp_path / "ci.yml").write_bytes(b"jobs:\n  lint:\n    runs-on: \xff\n")
        with pytest.raises(WorkflowReadError) as raised:
            workflow_texts(tmp_path)
        assert raised.value.workflow == "ci.yml"
        assert "could not be read" in raised.value.reason

    def test_yaml_that_does_not_parse_is_refused(self) -> None:
        """A parse failure is this reader's own error, not PyYAML's.

        A `yaml.YAMLError` escaping from something that reads like a query is
        an unhandled crash; `WorkflowReadError` is what a caller expects.
        """
        with pytest.raises(WorkflowReadError) as raised:
            parse("ci.yml", "jobs: [unclosed\n")
        assert raised.value.workflow == "ci.yml"
        assert "could not be parsed" in raised.value.reason

    @pytest.mark.parametrize(
        "text",
        ["- lint\n- test\n", "just a string\n", "\n"],
        ids=["list", "scalar", "empty"],
    )
    def test_a_document_that_is_not_a_mapping_is_refused(self, text: str) -> None:
        """Each of these parses cleanly and is still not a workflow.

        The empty case is the one worth naming: an empty file yields `None`,
        which would otherwise reach every walk below as a document.
        """
        with pytest.raises(WorkflowReadError, match="must parse to a mapping"):
            parse("ci.yml", text)

    def test_a_workflow_without_jobs_is_refused(self) -> None:
        """A document with no jobs cannot answer the questions asked of it."""
        with pytest.raises(WorkflowReadError, match="needs jobs"):
            steps_of(parse("ci.yml", "on: push\n"))

    def test_a_job_that_is_not_a_mapping_is_refused(self) -> None:
        """A job written as a scalar would otherwise reach every predicate."""
        with pytest.raises(WorkflowReadError, match="must be a mapping"):
            steps_of(parse("ci.yml", "jobs:\n  lint: ubuntu-latest\n"))

    def test_a_step_that_is_not_a_mapping_is_refused(self) -> None:
        """A step written as a scalar is the same defect one level down."""
        with pytest.raises(WorkflowReadError, match="must map"):
            steps_of(parse("ci.yml", "jobs:\n  lint:\n    steps:\n      - build\n"))

    def test_a_with_block_that_is_not_a_mapping_is_refused(self) -> None:
        """Inputs read as a mapping or the rules read nothing from them."""
        text = (
            "jobs:\n  test:\n    steps:\n"
            f"      - uses: {COVERAGE_ACTION}@abc\n        with: 'language: python'\n"
        )
        with pytest.raises(WorkflowReadError, match="with must map"):
            steps_using(parse("ci.yml", text), COVERAGE_ACTION)

    def test_every_refusal_is_catchable_as_the_package_error(self) -> None:
        """The base class is the stable catch point it exists to be."""
        with pytest.raises(WorkflowContractError):
            parse("ci.yml", "- not a mapping\n")


class TestTriggerSpellings:
    """Every spelling GitHub accepts, because the real files use one."""

    @pytest.mark.parametrize(
        ("triggers", "serving"),
        [
            ("on: pull_request\n", True),
            ("on: push\n", False),
            ("on: [pull_request, push]\n", True),
            ("on: [push]\n", False),
            ("on:\n  pull_request:\n", True),
            ("on:\n  push:\n    branches: [main]\n", False),
            ("'on':\n  pull_request:\n", True),
        ],
        ids=[
            "string",
            "string-other",
            "list",
            "list-other",
            "mapping",
            "mapping-push",
            "quoted-mapping",
        ],
    )
    def test_a_pull_request_trigger_is_found_in_every_form(
        self, triggers: str, *, serving: bool
    ) -> None:
        """String, list and mapping, and the quoted key.

        PyYAML resolves an unquoted `on:` to the boolean `True`, so a reader
        checking only the string key reports every workflow as having no
        triggers. That would make the boundary rules vacuous rather than
        failing, which is the worst of the available outcomes.
        """
        document = parse("ci.yml", triggers + "jobs: {}\n")
        assert serves_pull_requests(document) is serving

    @pytest.mark.parametrize(
        ("triggers", "pushes"),
        [
            ("on:\n  push:\n    branches: [main]\n", True),
            ("on:\n  push:\n    branches: [develop]\n", False),
            ("on:\n  push:\n    tags: ['v*']\n", False),
            ("on: push\n", False),
            ("on:\n  pull_request:\n", False),
        ],
        ids=["main", "other-branch", "tags-only", "bare-push", "no-push"],
    )
    def test_a_push_to_main_is_distinguished_from_other_pushes(
        self, triggers: str, *, pushes: bool
    ) -> None:
        """A tag push or a release branch is not the publisher's trigger."""
        document = parse("ci.yml", triggers + "jobs: {}\n")
        assert pushes_to_main(document) is pushes

    def test_a_workflow_serving_both_is_not_the_publisher(self) -> None:
        """The shape `ci.yml` has, and the reason the predicate reads both.

        A predicate reading only the push arm would call `ci.yml` a publisher
        while the boundary rules also call it a pull-request workflow, so the
        same file would be required to upload and forbidden from uploading.
        """
        document = parse(
            "ci.yml", "on:\n  push:\n    branches: [main]\n  pull_request:\njobs: {}\n"
        )
        assert pushes_to_main(document) is True
        assert serves_pull_requests(document) is True
        assert is_publisher(document) is False

    def test_a_push_only_workflow_is_the_publisher(self) -> None:
        """Narrow as well as sufficient: the publisher must still be found."""
        document = parse(
            "coverage-main.yml", "on:\n  push:\n    branches: [main]\njobs: {}\n"
        )
        assert is_publisher(document) is True


class TestCodeSceneMarkers:
    """What counts as reaching CodeScene, and what does not."""

    @pytest.mark.parametrize(
        "line",
        [
            "        run: cs-coverage check --coverage-files coverage.xml",
            "          access-token: ${{ secrets.CS_ACCESS_TOKEN }}",
            f"        uses: {UPLOAD_ACTION}@abc",
            "          project-url: https://api.codescene.io/v2/projects/1",
        ],
        ids=["command", "token", "action", "url"],
    )
    def test_a_marker_is_found_wherever_it_sits(self, line: str) -> None:
        """A run script, an env value, a `uses` and an input.

        Read from the raw text rather than the parsed document, because a
        walk reading only the shapes it expects misses whichever location is
        used next.
        """
        assert codescene_mentions(f"jobs:\n  test:\n    steps:\n{line}\n")

    def test_a_comment_explaining_the_boundary_is_not_a_breach(self) -> None:
        """The rule must not forbid writing down its own reason.

        A comment invokes nothing. Refusing the word outright would mean the
        only place the reason can live is a file the rule rejects.
        """
        text = (
            "# The CS_ACCESS_TOKEN and cs-coverage live in the push lane only.\n"
            "on:\n  pull_request:\njobs: {}\n"
        )
        assert codescene_mentions(text) == []

    def test_a_clean_workflow_mentions_nothing(self) -> None:
        """Narrow as well as sufficient."""
        assert codescene_mentions("on:\n  pull_request:\njobs:\n  lint:\n") == []


class TestRetiredChecksumNames:
    """The retired-digest reader, driven over shapes this repository lacks.

    Every workflow here is already clean, so a reader that recognised nothing
    would pass the contracts next door over an empty set of offenders. These
    tests drive it over documents built in the test instead.
    """

    @pytest.mark.parametrize(
        ("line", "expected"),
        [
            ("          installer-checksum: ''", ["installer-checksum"]),
            (
                "          installer-checksum: ${{ vars.CODESCENE_CLI_SHA256 }}",
                ["CODESCENE_CLI_SHA256", "installer-checksum"],
            ),
            (
                "      CODESCENE_CLI_SHA256: ${{ vars.CODESCENE_CLI_SHA256 }}",
                ["CODESCENE_CLI_SHA256"],
            ),
            (
                '        run: echo "$CODESCENE_CLI_SHA256"',
                ["CODESCENE_CLI_SHA256"],
            ),
        ],
        ids=["input-literal", "input-from-variable", "env-value", "run-script"],
    )
    def test_a_retired_name_is_found_wherever_it_sits(
        self, line: str, expected: list[str]
    ) -> None:
        """An input, an env value and a run script each count.

        The input with an empty literal matters on its own: a contract
        written against the variable alone would accept it, and the action
        rejects the input rather than the value's origin.
        """
        text = f"jobs:\n  test:\n    steps:\n{line}\n"
        assert deprecated_digest_mentions(text) == expected

    def test_a_comment_explaining_the_retirement_is_not_a_breach(self) -> None:
        """`coverage-main.yml` says why it passes no checksum, in a comment.

        A comment invokes nothing. Refusing the word outright would delete
        the only place that reason can be written down.
        """
        text = (
            "# No checksum input: installer-checksum is rejected, and\n"
            "# CODESCENE_CLI_SHA256 has no consumer left.\n"
            "on:\n  push:\njobs: {}\n"
        )
        assert deprecated_digest_mentions(text) == []

    def test_a_clean_workflow_names_neither(self) -> None:
        """Narrow as well as sufficient."""
        assert deprecated_digest_mentions("on:\n  push:\njobs:\n  lint:\n") == []
