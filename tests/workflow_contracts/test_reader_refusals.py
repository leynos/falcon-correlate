"""Every refusal the workflow readers raise, driven over built documents.

Split from the predicate tests next door for the repository's module-size
limit, and along a real seam: this module is about failures, that one is about
what the readers return when nothing is wrong.

The contracts in `test_runner_placement.py` are parametrized over this
repository's own workflows, which are correct, so they pass whether or not a
refusal fires. Only documents built here show one firing.
"""

from __future__ import annotations

import os
import typing as typ

import pytest

from tests.workflow_contracts.runner_lanes import all_lanes, serves_pull_requests
from tests.workflow_contracts.workflow_documents import (
    WorkflowReadError,
    jobs_of,
    parse_workflow,
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
    assert raised.value.workflow == "ci.yml", (
        f"the failure must name the file it is about; got {raised.value.workflow!r}"
    )
    assert "could not be read" in raised.value.reason, (
        f"the reason must say the file could not be read; got {raised.value.reason!r}"
    )


def test_yaml_that_does_not_parse_is_refused(tmp_path: Path) -> None:
    """A parse failure is the reader's own error, not PyYAML's."""
    (tmp_path / "ci.yml").write_text("jobs: [unclosed\n", encoding="utf-8")
    texts = workflow_texts(tmp_path)
    with pytest.raises(WorkflowReadError) as raised:
        all_lanes(texts)
    assert raised.value.workflow == "ci.yml", (
        f"the failure must name the file it is about; got {raised.value.workflow!r}"
    )
    assert "could not be parsed" in raised.value.reason, (
        f"the reason must say the text could not be parsed; got {raised.value.reason!r}"
    )


def test_a_document_that_is_not_a_mapping_is_refused(tmp_path: Path) -> None:
    """A list at the top level parses cleanly and is still not a workflow."""
    (tmp_path / "ci.yml").write_text("- lint\n- test\n", encoding="utf-8")
    texts = workflow_texts(tmp_path)
    with pytest.raises(WorkflowReadError, match="must parse to a mapping"):
        all_lanes(texts)


def test_a_job_that_is_not_a_mapping_is_refused(tmp_path: Path) -> None:
    """A job written as a scalar would otherwise reach every predicate."""
    (tmp_path / "ci.yml").write_text("jobs:\n  lint: ubuntu-latest\n", encoding="utf-8")
    with pytest.raises(WorkflowReadError) as raised:
        jobs_of((tmp_path / "ci.yml").read_text(encoding="utf-8"), "ci.yml")
    assert raised.value.workflow == "ci.yml", (
        f"a structural refusal must name its source like an I/O one; got "
        f"{raised.value.workflow!r}"
    )
    assert "job lint must be a mapping" in raised.value.reason, (
        f"the reason must name the offending job; got {raised.value.reason!r}"
    )


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


def test_both_readers_raise_the_same_exception_class() -> None:
    """One catch point across the package, not one per reader.

    The two readers here grew on separate branches and each defined a
    `WorkflowReadError`. Two classes of that name in one package defeat the
    base class entirely: `except WorkflowReadError` catches whichever one the
    caller happened to import and silently misses the other. Asserted rather
    than assumed, because the failure is invisible until the day it matters.
    """
    from tests.workflow_contracts import codescene_lanes, errors, workflow_documents

    assert workflow_documents.WorkflowReadError is errors.WorkflowReadError, (
        "the document reader must raise the package's error, not one of its own"
    )
    assert codescene_lanes.WorkflowReadError is errors.WorkflowReadError, (
        "the CodeScene reader must raise the same class as the document reader"
    )
    assert issubclass(errors.WorkflowReadError, errors.WorkflowContractError), (
        "the read error must derive from the package's stable catch point"
    )


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
    assert str(Raised("the directory is absent")) == "the directory is absent", (
        "a failure with no known file must render the reason alone"
    )


def test_an_absent_workflow_is_refused_by_name() -> None:
    """A stale list of lane names must say which name is stale.

    This is not hypothetical. `get-codescene-sha.yml` was deleted from this
    repository on 2026-09-22 while `HOSTED_LANES` still named it, and the
    reader raised a bare `KeyError` carrying only the name. It surfaced during
    pytest's parameter generation, so it reported as a collection error rather
    than as a contract failure, and it said nothing about which list was stale
    or what the directory actually holds.
    """
    with pytest.raises(WorkflowReadError) as raised:
        serves_pull_requests("absent.yml", {"ci.yml": "on: push\njobs: {}\n"})
    assert raised.value.workflow == "absent.yml", (
        f"the failure must name the workflow that is missing; got "
        f"{raised.value.workflow!r}"
    )
    assert "ci.yml" in raised.value.reason, (
        f"the reason must list what the corpus does hold, so a stale name is "
        f"actionable without opening the directory; got {raised.value.reason!r}"
    )


@pytest.mark.parametrize(
    ("text", "key"),
    [
        ("jobs:\n  lint:\n    runs-on: a\n    runs-on: b\n", "runs-on"),
        ("jobs:\n  lint: {}\njobs:\n  test: {}\n", "jobs"),
        ("on: push\njobs:\n  a: {}\n  a: {}\n", "a"),
    ],
    ids=["runs-on", "jobs", "job-name"],
)
def test_a_repeated_mapping_key_is_refused(text: str, key: str) -> None:
    """PyYAML keeps the last value and says nothing, which inverts a contract.

    A workflow declaring `runs-on` twice parses into a document that has
    discarded the first value, so a lane could carry a paid label in the
    discarded half and read as hosted here. GitHub Actions and actionlint both
    reject duplicate mapping keys, so a document this refuses would never have
    run; refusing it means the contracts fail loudly instead of passing over a
    half of the file nobody chose.
    """
    with pytest.raises(WorkflowReadError) as raised:
        parse_workflow(text, "ci.yml")
    assert raised.value.workflow == "ci.yml", (
        f"the refusal must name the file; got {raised.value.workflow!r}"
    )
    assert key in raised.value.reason, (
        f"the reason must name the repeated key {key!r} so it can be found; "
        f"got {raised.value.reason!r}"
    )


def test_an_unreadable_directory_arrives_as_the_reader_s_own_error(
    tmp_path: Path,
) -> None:
    """No `OSError` escapes `workflow_texts`, on any interpreter CI runs.

    `Path.is_dir()` is not uniform across this repository's matrix. Measured
    on 2026-09-22: 3.12.12 and 3.13.11 raise `PermissionError` when a parent
    directory denies traversal, while 3.14.2 returns `False`. Probing outside
    the `OSError` handler therefore leaks a `PermissionError` out of a
    function whose documented contract is `WorkflowReadError`, on two of the
    three legs and on neither of the others.

    The assertion is the contract rather than the platform: whichever way the
    interpreter behaves, the caller sees `WorkflowReadError`.
    """
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    target = blocked / "workflows"
    target.mkdir()
    blocked.chmod(0o000)
    try:
        if os.access(target, os.R_OK):
            pytest.skip("this user can traverse a mode-000 directory")
        with pytest.raises(WorkflowReadError) as raised:
            workflow_texts(target)
        assert raised.value.workflow == str(target), (
            f"the refusal must name the directory; got {raised.value.workflow!r}"
        )
    finally:
        blocked.chmod(0o700)
