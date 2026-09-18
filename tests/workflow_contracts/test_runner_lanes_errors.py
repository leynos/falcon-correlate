"""Direct tests for the reader's refusals and its two shape predicates.

The contracts next door are parametrized over this repository's own
workflows, which are correct, so they pass whether or not the reader
discriminates anything. These tests drive the reader itself over documents
built here, including shapes this repository does not contain and should
never contain, so each refusal is shown to fire.

Each case is one failure someone can actually have. A workflow directory
that is not there, a file that is not UTF-8, YAML that does not parse, a
document that is not a mapping, a job that is not a mapping, a registry
whose labels are a bare scalar, a ceiling written as a Boolean, and a
``continue-on-error`` written as an expression. The last two are the ones
that read as correct: both satisfy the obvious check and neither is what
GitHub will do.
"""

from __future__ import annotations

import re
import typing as typ

import pytest

from tests.workflow_contracts.runner_lanes import (
    PAID_LANES,
    all_lanes,
    continue_on_error_sites,
    paid_lanes_by_trigger,
    serves_pull_requests,
    timeout_minutes_of,
)
from tests.workflow_contracts.workflow_documents import (
    WorkflowReadError,
    jobs_of,
    read_actionlint_registry,
    workflow_texts,
)

if typ.TYPE_CHECKING:
    from pathlib import Path


def test_a_missing_workflow_directory_is_refused_rather_than_empty(
    tmp_path: Path,
) -> None:
    """An absent directory must raise, not glob to nothing.

    ``Path.glob`` on a directory that is not there yields no paths and no
    error, so the reader would have returned an empty mapping and every
    contract over "every lane" would have passed over no lanes at all. That
    is the failure this refusal exists for, and it is silent without it.
    """
    with pytest.raises(WorkflowReadError, match="not a readable workflow directory"):
        workflow_texts(tmp_path / "absent")


def test_a_file_that_is_not_a_directory_is_refused(tmp_path: Path) -> None:
    """A path to a file reads as a directory to nobody, so say so."""
    target = tmp_path / "ci.yml"
    target.write_text("jobs: {}\n", encoding="utf-8")
    with pytest.raises(WorkflowReadError, match="not a readable workflow directory"):
        workflow_texts(target)


def test_a_file_that_is_not_utf8_is_refused_by_name(tmp_path: Path) -> None:
    """The failure names the file, because the directory holds several.

    Asserted against the exception's attributes rather than its rendered
    text: which file failed is what a caller acts on, and a message reworded
    for a reader should not break a test that is really about the file.
    """
    (tmp_path / "ci.yml").write_bytes(b"jobs:\n  lint:\n    runs-on: \xff\n")
    with pytest.raises(WorkflowReadError) as raised:
        workflow_texts(tmp_path)
    assert raised.value.workflow == "ci.yml"
    assert "could not be read" in raised.value.reason


def test_yaml_that_does_not_parse_is_refused(tmp_path: Path) -> None:
    """A parse failure is the reader's own error, not PyYAML's."""
    (tmp_path / "ci.yml").write_text("jobs: [unclosed\n", encoding="utf-8")
    texts = workflow_texts(tmp_path)
    with pytest.raises(WorkflowReadError) as raised:
        all_lanes(texts)
    assert raised.value.workflow == "ci.yml"
    assert "could not be parsed" in raised.value.reason


def test_a_document_that_is_not_a_mapping_is_refused(tmp_path: Path) -> None:
    """A list at the top level parses cleanly and is still not a workflow."""
    (tmp_path / "ci.yml").write_text("- lint\n- test\n", encoding="utf-8")
    texts = workflow_texts(tmp_path)
    with pytest.raises(WorkflowReadError, match="must parse to a mapping"):
        all_lanes(texts)


def test_a_job_that_is_not_a_mapping_is_refused(tmp_path: Path) -> None:
    """A job written as a scalar would otherwise reach every predicate."""
    (tmp_path / "ci.yml").write_text("jobs:\n  lint: ubuntu-latest\n", encoding="utf-8")
    not_a_mapping = re.escape("ci.yml:lint must be a mapping")
    with pytest.raises(WorkflowReadError, match=not_a_mapping):
        jobs_of((tmp_path / "ci.yml").read_text(encoding="utf-8"), "ci.yml")


def test_a_workflow_with_no_jobs_mapping_is_refused(tmp_path: Path) -> None:
    """No jobs key is a document this reader cannot answer questions about."""
    (tmp_path / "ci.yml").write_text("on: push\n", encoding="utf-8")
    with pytest.raises(WorkflowReadError, match="must declare a jobs mapping"):
        jobs_of((tmp_path / "ci.yml").read_text(encoding="utf-8"), "ci.yml")


def test_a_registry_that_cannot_be_read_is_refused(tmp_path: Path) -> None:
    """An absent configuration is reported by name."""
    with pytest.raises(WorkflowReadError, match="could not be read"):
        read_actionlint_registry(tmp_path / "actionlint.yaml")


def test_a_registry_without_the_runner_key_is_refused(tmp_path: Path) -> None:
    """The key the labels live under must be there to read them from."""
    config = tmp_path / "actionlint.yaml"
    config.write_text("paths: {}\n", encoding="utf-8")
    with pytest.raises(WorkflowReadError, match="must declare self-hosted-runner"):
        read_actionlint_registry(config)


def test_a_scalar_label_list_is_refused_rather_than_split(tmp_path: Path) -> None:
    """A bare scalar would become a set of its characters.

    ``set("ubicloud-standard-2")`` is nineteen one-character labels, and the
    registry contract would then compare letters against runner labels and
    report a difference nobody can act on. Refusing the shape says what is
    wrong with the file instead.
    """
    config = tmp_path / "actionlint.yaml"
    config.write_text(
        "self-hosted-runner:\n  labels: ubicloud-standard-2\n", encoding="utf-8"
    )
    with pytest.raises(WorkflowReadError, match="list of strings"):
        read_actionlint_registry(config)


def test_a_non_string_label_is_refused(tmp_path: Path) -> None:
    """A list is not enough; its elements must be labels."""
    config = tmp_path / "actionlint.yaml"
    config.write_text("self-hosted-runner:\n  labels:\n    - 2\n", encoding="utf-8")
    with pytest.raises(WorkflowReadError, match="list of strings"):
        read_actionlint_registry(config)


def test_a_registry_with_no_labels_reads_as_empty(tmp_path: Path) -> None:
    """Absent labels are a legitimate registry, not an error.

    The refusal above must be narrow as well as sufficient: a repository
    that registers nothing has a valid configuration, and reporting it as
    malformed would make the rule fire where there is nothing wrong.
    """
    config = tmp_path / "actionlint.yaml"
    config.write_text("self-hosted-runner:\n  labels:\n", encoding="utf-8")
    assert read_actionlint_registry(config) == set()


@pytest.mark.parametrize(
    "declared",
    [True, False],
    ids=["true", "false"],
)
def test_a_boolean_ceiling_is_refused(declared: bool) -> None:  # noqa: FBT001
    """``bool`` subclasses ``int``, so the obvious check accepts it.

    ``timeout-minutes: true`` would satisfy ``isinstance(value, int)`` and
    then satisfy ``0 < value <= 60`` as the value one, so a lane with no
    reviewed ceiling would have passed the ceiling contract. GitHub does not
    accept a Boolean there at all.
    """
    with pytest.raises(WorkflowReadError, match="must be an integer"):
        timeout_minutes_of({"timeout-minutes": declared})


def test_an_absent_ceiling_reads_as_none() -> None:
    """Absent and invalid are different answers, and the caller needs both."""
    assert timeout_minutes_of({}) is None


def test_an_integer_ceiling_reads_as_itself() -> None:
    """The refusal must not fire on the shape the workflows actually use."""
    assert timeout_minutes_of({"timeout-minutes": 15}) == 15


@pytest.mark.parametrize(
    "value",
    [True, "${{ true }}", "${{ github.event_name == 'push' }}", False, "false"],
    ids=["true", "expression", "conditional-expression", "false", "string-false"],
)
def test_continue_on_error_is_reported_at_job_scope(value: object) -> None:
    """Presence is the rule, because value comparison has a hole.

    PyYAML returns ``${{ true }}`` as a string, so ``is not True`` accepts
    it and the lane can fail without failing the workflow. ``false`` is
    reported too: a key that can be flipped to true in a one-character
    change is not a lane that must pass, and reviewing the flip is cheaper
    than discovering it.
    """
    assert continue_on_error_sites({"continue-on-error": value}) == [
        f"job scope ({value!r})"
    ]


def test_continue_on_error_is_reported_at_step_scope() -> None:
    """A step hides a failure inside a lane that is otherwise required."""
    job = {
        "steps": [
            {"name": "build", "run": "make"},
            {"name": "flaky", "run": "make check", "continue-on-error": "${{ true }}"},
        ]
    }
    assert continue_on_error_sites(job) == ["step 'flaky' ('${{ true }}')"]


def test_a_step_without_a_name_is_reported_by_what_it_uses() -> None:
    """A failure must be findable in the file it came from."""
    job = {"steps": [{"uses": "actions/checkout@v5", "continue-on-error": True}]}
    assert continue_on_error_sites(job) == ["step 'actions/checkout@v5' (True)"]


def test_a_clean_job_reports_no_sites() -> None:
    """The rule must be narrow: a job declaring nothing reports nothing."""
    job = {"runs-on": "ubuntu-latest", "steps": [{"run": "make"}]}
    assert not continue_on_error_sites(job)


def test_the_high_level_queries_read_the_source_they_are_given(
    tmp_path: Path,
) -> None:
    """Injection at the boundary, shown by answering about a built corpus.

    ``all_lanes``, ``serves_pull_requests`` and ``paid_lanes_by_trigger``
    each took the repository's own workflows from a module global, so
    nothing could ask them about anything else and their behaviour on a
    different corpus was unobservable.
    """
    (tmp_path / "ci.yml").write_text(
        "on:\n  pull_request:\njobs:\n  lint:\n    runs-on: ubuntu-latest\n",
        encoding="utf-8",
    )
    (tmp_path / "nightly.yml").write_text(
        "on:\n  schedule:\n    - cron: '0 0 * * *'\njobs:\n"
        "  sweep:\n    runs-on: ubuntu-latest\n",
        encoding="utf-8",
    )
    texts = workflow_texts(tmp_path)
    assert {(w, n) for w, n, _ in all_lanes(texts)} == {
        ("ci.yml", "lint"),
        ("nightly.yml", "sweep"),
    }
    assert serves_pull_requests("ci.yml", texts) is True
    assert serves_pull_requests("nightly.yml", texts) is False


def test_paid_lanes_by_trigger_partitions_the_agreed_lanes() -> None:
    """Both halves, and nothing lost between them.

    The two answers are complements, so their union must be every agreed
    lane and their intersection must be empty. Asserting one half alone
    would not notice a lane that fell out of both.
    """
    serving = set(paid_lanes_by_trigger(serving_pull_requests=True))
    not_serving = set(paid_lanes_by_trigger(serving_pull_requests=False))
    assert not serving & not_serving
    assert serving | not_serving == set(PAID_LANES)


def test_both_readers_raise_the_same_exception_class() -> None:
    """One catch point across the package, not one per reader.

    The two readers here grew on separate branches and each defined a
    `WorkflowReadError`. Two classes of that name in one package defeat the
    base class entirely: `except WorkflowReadError` catches whichever one the
    caller happened to import and silently misses the other. Asserted rather
    than assumed, because the failure is invisible until the day it matters.
    """
    from tests.workflow_contracts import codescene_lanes, errors, workflow_documents

    assert workflow_documents.WorkflowReadError is errors.WorkflowReadError
    assert codescene_lanes.WorkflowReadError is errors.WorkflowReadError
    assert issubclass(errors.WorkflowReadError, errors.WorkflowContractError)


def test_a_document_reader_failure_is_catchable_as_the_package_error() -> None:
    """The base class is a claim this file proves rather than states."""
    from tests.workflow_contracts.errors import WorkflowContractError

    with pytest.raises(WorkflowContractError):
        jobs_of("- not a mapping\n", "ci.yml")


def test_a_failure_renders_the_workflow_into_its_message() -> None:
    """The attributes are for a caller; the message is for a person.

    Both are behaviour. A failure reaching a log or a test report as "could
    not be parsed", with no file named, sends the reader to the wrong place
    in a directory holding seven workflows. Asserted separately from the
    attributes so that dropping either is visible.
    """
    from tests.workflow_contracts.errors import WorkflowReadError as Raised

    assert str(Raised("could not be parsed", "ci.yml")) == (
        "ci.yml: could not be parsed"
    )
    assert str(Raised("the directory is absent")) == "the directory is absent"
