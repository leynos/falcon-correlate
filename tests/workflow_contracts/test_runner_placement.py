"""Contract tests for which runner each lane bills for.

Four rules, each written from a failure someone has already had.

**Placement.** A lane that runs on a per-minute runner must be one the
estate agreed to move there, and a lane that stays GitHub-hosted must stay
there. A scheduled or dispatch-only job on a paid runner is cost with no
latency benefit, which is the shape this repository is moving away from.

**The fork fallback.** A pull request from a fork cannot obtain an Ubicloud
runner, so a lane serving pull requests falls back to a GitHub-hosted runner
for forks only. The expression is written as a folded scalar, and a folded
scalar whose continuation is indented more deeply than its first line keeps
the line break: the resulting value carries a newline inside an expression
that GitHub evaluates anyway. A green run is therefore not evidence the
defect is absent, and nothing but a contract will find it.

**Ceilings.** An Ubicloud runner is a self-hosted JIT runner, so GitHub's
six-hour ceiling for hosted jobs does not apply to it; the limit is five
days. A lane with no ``timeout-minutes`` bills for a hang until someone
notices. Every paid lane declares one, bounded above so the declaration
cannot itself become a five-day ceiling written out longhand.

**The registry.** actionlint knows GitHub's labels and rejects anything else
as a typo, so every paid label must be registered in
``.github/actionlint.yaml``. The assertion is equality in both directions.
A subset catches an unregistered label but not a stale registration left
behind when a lane moved back, and a stale registration is exactly what
stops the check being about anything. "In use" is derived by subtracting a
named frozen set of the labels GitHub hosts, rather than by matching a
vendor prefix: a prefix reading works today and silently exempts a second
paid provider's labels the moment one appears, which inverts the question
the registry exists to ask.

The fork fallback's hosted arm is why the frozen set matters here. That arm
is a GitHub-hosted label and is not registrable, so a contract asking about
every label in use would fail the very change that adds the fallback.
"""

from __future__ import annotations

import pytest

from tests.workflow_contracts.runner_lanes import (
    FORK_FALLBACK,
    GITHUB_HOSTED_LABELS,
    HOSTED_LANES,
    MAXIMUM_TIMEOUT_MINUTES,
    PAID_LANES,
    UBICLOUD_LABEL,
    all_lanes,
    billable_labels,
    continue_on_error_sites,
    labels_of,
    paid_lanes_by_trigger,
    timeout_minutes_of,
)
from tests.workflow_contracts.workflow_documents import (
    WorkflowReadError,
    jobs_of,
    read_actionlint_registry,
    workflow_texts,
)


def test_every_paid_lane_is_one_that_was_agreed() -> None:
    """Equality, not containment, in both directions.

    Containment would let a new lane onto a paid runner without anyone
    naming it, which is how a migration becomes a bill.
    """
    in_use = {
        f"{workflow}:{name}"
        for workflow, name, job in all_lanes()
        if billable_labels(job)
    }
    assert in_use == set(PAID_LANES), (
        "the lanes billing for a paid runner and the lanes this repository "
        f"agreed to move must be the same set; only on a paid runner: "
        f"{sorted(in_use - set(PAID_LANES))}; agreed but not paid: "
        f"{sorted(set(PAID_LANES) - in_use)}"
    )


@pytest.mark.parametrize("lane", sorted(HOSTED_LANES), ids=str)
def test_a_lane_that_stays_hosted_bills_for_nothing(lane: str) -> None:
    """The named exceptions, asserted individually with their reason."""
    workflow, _, name = lane.partition(":")
    job = jobs_of(workflow_texts()[workflow], workflow)[name]
    assert not billable_labels(job), (
        f"{lane} stays GitHub-hosted ({HOSTED_LANES[lane]}) and must bill "
        f"for nothing; it resolves to {sorted(labels_of(job))}"
    )


def test_no_lane_takes_its_label_from_a_broken_folded_scalar() -> None:
    """A folded scalar's continuation must not keep its line break.

    Read from the parsed value rather than from the raw text, because that
    is what GitHub evaluates. The raw declaration is reported alongside so a
    failure is actionable without opening the file.
    """
    for workflow, name, job in all_lanes():
        runs_on = job.get("runs-on")
        if not isinstance(runs_on, str):
            continue
        assert "\n" not in runs_on, (
            f"{workflow}:{name} has a runs-on carrying a line break, which "
            "GitHub evaluates as written. A folded scalar's continuation "
            "must sit at the same indent as its first line. The value "
            f"parsed as {runs_on!r}"
        )


@pytest.mark.parametrize(
    "lane", paid_lanes_by_trigger(serving_pull_requests=True), ids=str
)
def test_a_pull_request_lane_falls_back_for_forks(lane: str) -> None:
    """Both arms, and the right way round.

    Asserting only that an expression is present would accept one with no
    fallback arm, or one whose arms are swapped so every branch build lands
    on the hosted runner and every fork build on the paid one.

    The lanes are derived from each workflow's own triggers rather than
    listed here. A second list is the gap: a paid lane added to a
    pull-request workflow would satisfy every other rule while carrying a
    literal label no fork can obtain.
    """
    workflow, _, name = lane.partition(":")
    job = jobs_of(workflow_texts()[workflow], workflow)[name]
    runs_on = job.get("runs-on")
    assert isinstance(runs_on, str), f"{lane} must declare a string runs-on"
    fallback = FORK_FALLBACK.match(runs_on.strip())
    assert fallback is not None, (
        f"{lane} serves pull requests and must carry the fork fallback, "
        f"guarded on the fork field; got {runs_on!r}"
    )
    assert fallback["when_fork"] in GITHUB_HOSTED_LABELS, (
        f"{lane}'s fork arm must be GitHub-hosted, because a fork cannot "
        f"obtain a paid runner; got {fallback['when_fork']!r}"
    )
    assert fallback["when_branch"] == UBICLOUD_LABEL, (
        f"{lane}'s branch arm must be the paid runner; got {fallback['when_branch']!r}"
    )


@pytest.mark.parametrize("lane", sorted(PAID_LANES), ids=str)
def test_every_paid_lane_declares_a_bounded_ceiling(lane: str) -> None:
    """An Ubicloud runner is self-hosted, so GitHub's six hours do not apply.

    The bound above matters as much as the requirement: a lane declaring
    ``timeout-minutes: 7200`` has satisfied "declares a ceiling" and has not
    bounded anything.
    """
    workflow, _, name = lane.partition(":")
    job = jobs_of(workflow_texts()[workflow], workflow)[name]
    timeout = timeout_minutes_of(job)
    assert timeout is not None, (
        f"{lane} runs on a paid runner and must declare timeout-minutes"
    )
    assert 0 < timeout <= MAXIMUM_TIMEOUT_MINUTES, (
        f"{lane} declares timeout-minutes {timeout}, outside the reviewed "
        f"range of 1 to {MAXIMUM_TIMEOUT_MINUTES}"
    )


@pytest.mark.parametrize("lane", sorted(PAID_LANES), ids=str)
def test_a_paid_lane_can_actually_run(lane: str) -> None:
    """A lane switched off is not a lane placed.

    A job-level ``if:`` that never holds, or ``continue-on-error`` at job or
    step scope, turns a placement into a decoration: the contract above
    would still see the label. Asserted separately so a failure names the
    mechanism rather than the label.

    ``continue-on-error`` is refused by presence rather than by value.
    GitHub accepts an expression there and PyYAML returns an expression as a
    string, so ``${{ true }}`` is not ``True``: a comparison against ``True``
    would accept the one spelling that is hardest to notice in review.
    """
    workflow, _, name = lane.partition(":")
    job = jobs_of(workflow_texts()[workflow], workflow)[name]
    assert "if" not in job, (
        f"{lane} carries a job-level if ({job.get('if')!r}). A guarded lane "
        "can be skipped without failing anything, so its placement asserts "
        "nothing; guard the steps inside it instead"
    )
    sites = continue_on_error_sites(job)
    assert not sites, (
        f"{lane} declares continue-on-error at {'; '.join(sites)}, so it can "
        "fail without failing the run. The key is refused wherever it "
        "appears and whatever its value, because an expression such as "
        "${{ true }} parses as a string and would slip past a comparison "
        "against True"
    )


def test_the_actionlint_registry_matches_the_labels_in_use() -> None:
    """Equality in both directions, over every arm of every conditional.

    A subset assertion catches an unregistered label and misses a stale
    registration. The stale one is the substantive gap: it outlives the lane
    that needed it and leaves the registry describing a repository that no
    longer exists.
    """
    registered = read_actionlint_registry()
    in_use = {label for _, _, job in all_lanes() for label in billable_labels(job)}
    assert in_use, (
        "no billable label was found at all; the reader subtracts a named "
        "hosted set, so an empty result means the reader is broken rather "
        "than that the repository stopped using paid runners"
    )
    assert registered == in_use, (
        "every label actionlint does not know must be registered, and every "
        "registration must name a label in use; registered but unused: "
        f"{sorted(registered - in_use)}; used but unregistered: "
        f"{sorted(in_use - registered)}"
    )


def test_an_unrecognized_label_is_reported_rather_than_excused() -> None:
    """The hosted set and a vendor prefix are not the same rule.

    Over this repository's own workflows the two readings agree exactly, so
    swapping one for the other changes no answer, and neither can be said to
    be proved by the lanes alone. This is the case that separates them, and
    it is driven directly for that reason.

    ``ubuntu-20.04`` is a GitHub-hosted family this estate does not use. A
    prefix reading excuses it silently because it does not begin with the
    Ubicloud prefix, and the registry then says nothing about a lane that
    has moved to a retired image or acquired a typo.
    """
    unrecognized = {"runs-on": "ubuntu-20.04"}
    assert "ubuntu-20.04" not in GITHUB_HOSTED_LABELS, (
        "this case only discriminates while the label is absent from the "
        "hosted set; adding it there makes the test vacuous"
    )
    assert billable_labels(unrecognized) == {"ubuntu-20.04"}, (
        "a label that is neither hosted nor reviewed must be reported, so "
        "the registry contract demands it be accounted for"
    )
    excused_by_a_prefix_reading = {
        label for label in labels_of(unrecognized) if label.startswith("ubicloud-")
    }
    assert not excused_by_a_prefix_reading, (
        "the prefix reading is what this contract deliberately does not use"
    )


def test_a_reusable_workflow_caller_contributes_no_labels() -> None:
    """A caller with no ``runs-on`` is not an unsupported shape.

    Two jobs here call a shared workflow and declare no ``runs-on``, because
    the called workflow places its own jobs. Refusing every non-string
    ``runs-on`` outright would stop the registry contract on both of them.
    The exemption is keyed on the caller's ``uses``, so a job declaring
    neither is still refused.
    """
    caller = {"uses": "leynos/shared-actions/.github/workflows/thing.yml@sha"}
    assert labels_of(caller) == set(), (
        "a reusable-workflow caller places no job itself and must contribute "
        f"no label; got {sorted(labels_of(caller))}"
    )
    assert billable_labels(caller) == set(), (
        f"a reusable-workflow caller must bill for nothing; got "
        f"{sorted(billable_labels(caller))}"
    )
    with pytest.raises(WorkflowReadError, match="declaring no runner"):
        labels_of({"steps": []})


@pytest.mark.parametrize(
    ("runs_on", "expected"),
    [
        pytest.param("ubuntu-latest", set(), id="hosted-literal"),
        pytest.param(UBICLOUD_LABEL, {UBICLOUD_LABEL}, id="paid-literal"),
        pytest.param(
            "${{ github.event.pull_request.head.repo.fork"
            " && 'ubuntu-latest' || 'ubicloud-standard-2' }}",
            {UBICLOUD_LABEL},
            id="fork-fallback-both-arms",
        ),
    ],
)
def test_the_reader_resolves_each_shape_github_accepts(
    runs_on: str, expected: set[str]
) -> None:
    """Drive the reader directly, not only over this repository's files.

    Parametrized over four correct workflows the reader passes whether or
    not it discriminates anything, so the shapes it must handle are built
    here instead.
    """
    assert billable_labels({"runs-on": runs_on}) == expected, (
        f"runs-on {runs_on!r} must resolve to {sorted(expected)}; got "
        f"{sorted(billable_labels({'runs-on': runs_on}))}"
    )


@pytest.mark.parametrize(
    "lane", paid_lanes_by_trigger(serving_pull_requests=False), ids=str
)
def test_a_lane_that_never_sees_a_pull_request_names_its_label(lane: str) -> None:
    """The complement of the fork-fallback rule, asserted rather than assumed.

    A push-only or tag-only lane cannot receive a fork's pull request, so a
    fork guard there is a condition that is always false: it reads as
    caution and buys nothing. Asserting the complement keeps the derivation
    honest in both directions, so a workflow that gains a `pull_request`
    trigger moves its lanes into the rule above rather than out of every
    rule.
    """
    workflow, _, name = lane.partition(":")
    job = jobs_of(workflow_texts()[workflow], workflow)[name]
    runs_on = job.get("runs-on")
    assert runs_on == UBICLOUD_LABEL, (
        f"{lane} never serves a pull request, so it must name the paid label "
        f"literally rather than guarding on a field that is always empty; "
        f"got {runs_on!r}"
    )


@pytest.mark.parametrize(
    ("runs_on", "expected"),
    [
        ("ubuntu-latest", {"ubuntu-latest"}),
        (
            ["self-hosted", "linux", "ubicloud-standard-2"],
            {"self-hosted", "linux", "ubicloud-standard-2"},
        ),
        ({"group": "ubicloud-runners"}, {"ubicloud-runners"}),
        (
            {"group": "ubicloud-runners", "labels": "ubicloud-standard-2"},
            {"ubicloud-runners", "ubicloud-standard-2"},
        ),
        (
            {"labels": ["ubicloud-standard-2", "linux"]},
            {"ubicloud-standard-2", "linux"},
        ),
    ],
    ids=["scalar", "sequence", "group", "group-and-labels", "labels-list"],
)
def test_every_runs_on_form_resolves_to_its_labels(
    runs_on: object, expected: set[str]
) -> None:
    """GitHub accepts three forms and a reader must model all three.

    The sequence and the ``group``/``labels`` mapping are the ones a reader
    usually misses. Missing them is not a narrow gap: a reader that returns
    the empty set for an unmodelled shape removes that lane from the
    placement rule, the ceiling rule and the registry rule at the same time,
    and all three then pass. vk's reader did exactly that and hid a paid,
    unregistered lane from all three (vk #264).
    """
    assert labels_of({"runs-on": runs_on}) == expected, (
        f"{runs_on!r} must resolve to {sorted(expected)}; got "
        f"{sorted(labels_of({'runs-on': runs_on}))}"
    )


@pytest.mark.parametrize(
    "runs_on",
    [42, {"cpu": 4}, [1, 2], None],
    ids=["number", "mapping-without-group-or-labels", "sequence-of-numbers", "absent"],
)
def test_an_unmodelled_runs_on_is_refused_rather_than_ignored(
    runs_on: object,
) -> None:
    """Fail closed. An unreadable shape must stop one rule, not silence three.

    Returning the empty set here would be the silent failure this whole
    module exists to refuse, because "this lane bills for nothing" and "this
    lane could not be read" would become the same answer.
    """
    with pytest.raises(WorkflowReadError):
        labels_of({"runs-on": runs_on} if runs_on is not None else {"steps": []})
