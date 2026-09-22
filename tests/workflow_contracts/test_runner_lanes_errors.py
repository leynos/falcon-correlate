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
    parse_workflow,
    read_actionlint_registry,
    workflow_texts,
)

if typ.TYPE_CHECKING:
    from pathlib import Path


def test_a_registry_with_no_labels_reads_as_empty(tmp_path: Path) -> None:
    """Absent labels are a legitimate registry, not an error.

    The refusal above must be narrow as well as sufficient: a repository
    that registers nothing has a valid configuration, and reporting it as
    malformed would make the rule fire where there is nothing wrong.
    """
    config = tmp_path / "actionlint.yaml"
    config.write_text("self-hosted-runner:\n  labels:\n", encoding="utf-8")
    assert read_actionlint_registry(config) == set(), (
        "a registry declaring no labels is valid and must read as the empty "
        "set rather than being refused"
    )


def test_an_absent_ceiling_reads_as_none() -> None:
    """Absent and invalid are different answers, and the caller needs both."""
    assert timeout_minutes_of({}) is None, (
        "an absent ceiling must read as None, which is a different answer "
        "from an invalid one"
    )


def test_an_integer_ceiling_reads_as_itself() -> None:
    """The refusal must not fire on the shape the workflows actually use."""
    assert timeout_minutes_of({"timeout-minutes": 15}) == 15, (
        "the refusal must not fire on the plain integer every workflow uses"
    )


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
    ], (
        f"the key must be reported at job scope whatever its value; "
        f"{value!r} gave {continue_on_error_sites({'continue-on-error': value})}"
    )


def test_continue_on_error_is_reported_at_step_scope() -> None:
    """A step hides a failure inside a lane that is otherwise required."""
    job = {
        "steps": [
            {"name": "build", "run": "make"},
            {"name": "flaky", "run": "make check", "continue-on-error": "${{ true }}"},
        ]
    }
    assert continue_on_error_sites(job) == ["step 'flaky' ('${{ true }}')"], (
        f"a step-scope expression must be reported by step name; got "
        f"{continue_on_error_sites(job)}"
    )


def test_a_step_without_a_name_is_reported_by_what_it_uses() -> None:
    """A failure must be findable in the file it came from."""
    job = {"steps": [{"uses": "actions/checkout@v5", "continue-on-error": True}]}
    assert continue_on_error_sites(job) == ["step 'actions/checkout@v5' (True)"], (
        f"a step with no name must be reported by what it uses; got "
        f"{continue_on_error_sites(job)}"
    )


def test_a_clean_job_reports_no_sites() -> None:
    """The rule must be narrow: a job declaring nothing reports nothing."""
    job = {"runs-on": "ubuntu-latest", "steps": [{"run": "make"}]}
    assert not continue_on_error_sites(job), (
        f"a job declaring the key nowhere must report no sites; got "
        f"{continue_on_error_sites(job)}"
    )


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
    }, (
        f"all_lanes must answer about the injected corpus; got "
        f"{sorted((w, n) for w, n, _ in all_lanes(texts))}"
    )
    assert serves_pull_requests("ci.yml", texts) is True, (
        "the built ci.yml declares a pull_request trigger, so the query must "
        "answer about the corpus it was given rather than this repository"
    )
    assert serves_pull_requests("nightly.yml", texts) is False, (
        "the built nightly.yml declares only a schedule"
    )


def test_paid_lanes_by_trigger_partitions_the_agreed_lanes() -> None:
    """Both halves, and nothing lost between them.

    The two answers are complements, so their union must be every agreed
    lane and their intersection must be empty. Asserting one half alone
    would not notice a lane that fell out of both.
    """
    serving = set(paid_lanes_by_trigger(serving_pull_requests=True))
    not_serving = set(paid_lanes_by_trigger(serving_pull_requests=False))
    assert not serving & not_serving, (
        f"the two answers are complements and must not overlap; both contain "
        f"{sorted(serving & not_serving)}"
    )
    assert serving | not_serving == set(PAID_LANES), (
        f"every agreed lane must fall in exactly one half; missing from both: "
        f"{sorted(set(PAID_LANES) - (serving | not_serving))}"
    )


@pytest.mark.parametrize(
    ("text", "expected_reason"),
    [
        ("- not a mapping\n", "must parse to a mapping"),
        ("on: push\n", "must declare a jobs mapping"),
        ("jobs:\n  lint: ubuntu-latest\n", "job lint must be a mapping"),
    ],
    ids=["document", "jobs", "job"],
)
def test_a_structural_refusal_names_its_source(text: str, expected_reason: str) -> None:
    """Structural failures carry the same `workflow` attribute as I/O ones.

    `WorkflowReadError` exists so a caller can act on which file failed
    without parsing prose. A refusal that omits the identifier makes that
    possible for an unreadable file and impossible for a malformed one, which
    is an arbitrary half of a distinction the exception exists to erase.
    """
    with pytest.raises(WorkflowReadError) as raised:
        jobs_of(text, "ci.yml")
    assert raised.value.workflow == "ci.yml", (
        f"expected the source name on a structural refusal; got "
        f"{raised.value.workflow!r}"
    )
    assert expected_reason in raised.value.reason, (
        f"expected {expected_reason!r} in the reason; got {raised.value.reason!r}"
    )


def test_a_registry_refusal_names_its_source(tmp_path: Path) -> None:
    """The same, for the actionlint configuration."""
    config = tmp_path / "actionlint.yaml"
    config.write_text("paths: {}\n", encoding="utf-8")
    with pytest.raises(WorkflowReadError) as raised:
        read_actionlint_registry(config)
    assert raised.value.workflow == "actionlint.yaml", (
        f"expected the configuration's name on the refusal; got "
        f"{raised.value.workflow!r}"
    )


def test_a_trigger_refusal_names_its_source() -> None:
    """And for the trigger mapping, which the lane queries read."""
    with pytest.raises(WorkflowReadError) as raised:
        serves_pull_requests("ci.yml", {"ci.yml": "on: 42\njobs: {}\n"})
    assert raised.value.workflow == "ci.yml", (
        f"expected the workflow name on a trigger refusal; got "
        f"{raised.value.workflow!r}"
    )


def test_a_document_without_repeats_still_parses() -> None:
    """Narrow as well as sufficient: the strict loader must accept real files.

    Every workflow in this repository goes through this loader on every run
    of the contracts, so a rule drawn too tightly would fail all of them. The
    explicit case is here so that intent is asserted rather than inferred from
    the other tests happening to pass.
    """
    document = parse_workflow(
        "on:\n  pull_request:\njobs:\n  lint:\n    runs-on: ubuntu-latest\n",
        "ci.yml",
    )
    assert document["jobs"]["lint"]["runs-on"] == "ubuntu-latest", (
        f"a document with no repeated key must parse unchanged; got {document}"
    )


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
