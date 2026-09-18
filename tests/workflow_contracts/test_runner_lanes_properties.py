"""Properties of the runner-lane reader, over generated inputs.

The contracts next door assert what this repository's seven workflows must
say. They cannot show that the reader is right, because parametrized over
seven correct documents it passes whether or not it discriminates anything.
These properties drive it over inputs it has never seen, and compare it with
an independently computed expectation rather than with itself.

Four properties, each chosen because getting it wrong is a way the registry
contract could quietly stop asking anything:

- a literal label resolves to itself, and to nothing when GitHub hosts it;
- a label that is neither hosted nor vendor-spelled is still reported, which
  is the only case separating a named hosted set from a vendor prefix;
- a fork fallback contributes **both** arms, so a lane cannot hide its paid
  arm behind an expression;
- a matrix job contributes exactly its legs' images, so a leg cannot be
  added without the registry noticing.

Each is proved able to fail by a mutation of the reader, recorded in the
pull request. The second exists because the first attempt at these
properties survived its own mutation: generating only vendor-spelled paid
labels and hosted ones makes a prefix reading and a set subtraction agree on
every case, so the properties passed under both and discriminated neither.

Generation is bounded deliberately. The reader's input is a YAML document
GitHub already validated, so generating arbitrary text would spend the
budget on shapes the reader will never see and is documented to refuse.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from tests.workflow_contracts.runner_lanes import (
    GITHUB_HOSTED_LABELS,
    MATRIX_DEFERRAL,
    billable_labels,
    labels_of,
)

#: Paid labels, as a vendor spells them. Bounded to plausible shapes rather
#: than arbitrary text: the reader's input is a label GitHub accepted.
paid_labels = st.builds(
    lambda vendor, shape, size: f"{vendor}-{shape}-{size}",
    st.sampled_from(["ubicloud", "namespace", "blacksmith"]),
    st.sampled_from(["standard", "gpu", "arm"]),
    st.integers(min_value=1, max_value=64),
)

hosted_labels = st.sampled_from(sorted(GITHUB_HOSTED_LABELS))

#: Labels that are neither GitHub-hosted nor spelled like a vendor's. These
#: are the only cases that separate "subtract a named hosted set" from "match
#: a vendor prefix", and without them the property below passes under both
#: readings and so proves neither. A retired GitHub image, a bare
#: `self-hosted`, and an ad-hoc pool name all reach a lane this way.
unreviewed_labels = st.sampled_from([
    "ubuntu-20.04",
    "ubuntu-18.04",
    "self-hosted",
    "linux-x64",
    "big-runner-8",
])


@given(label=paid_labels)
def test_a_paid_literal_resolves_to_itself(label: str) -> None:
    """A label outside the hosted set is reported, whoever sells it.

    The independently computed expectation is the label itself: no parsing
    is involved, so a reader that agrees here is agreeing with the input
    rather than with a second implementation of itself.
    """
    job = {"runs-on": label}
    assert labels_of(job) == {label}, (
        f"a literal runs-on must resolve to itself; {label!r} gave "
        f"{sorted(labels_of(job))}"
    )
    assert billable_labels(job) == {label}, (
        f"{label!r} is not in the hosted set, so it must be reported as "
        f"billable; got {sorted(billable_labels(job))}"
    )


@given(label=hosted_labels)
def test_a_hosted_literal_bills_for_nothing(label: str) -> None:
    """A label named in the hosted set is excused, and only those are."""
    job = {"runs-on": label}
    assert billable_labels(job) == set(), (
        f"{label!r} is GitHub-hosted and must bill for nothing; got "
        f"{sorted(billable_labels(job))}"
    )


@given(label=unreviewed_labels)
def test_an_unreviewed_label_is_reported_rather_than_excused(label: str) -> None:
    """The case that separates the hosted set from a vendor prefix.

    Written after the first attempt at these properties survived its own
    mutation. Generating only vendor-spelled paid labels and GitHub-hosted
    ones makes the two readings agree on every case, so replacing the
    subtraction with `startswith(("ubicloud-", ...))` changed no answer and
    the properties passed unchanged. They discriminated nothing.

    A label that is neither hosted nor vendor-spelled is the whole
    difference. A prefix reading excuses it silently, so a lane that has
    moved to a retired image, to a bare `self-hosted`, or to an ad-hoc pool
    becomes invisible to the registry contract. Subtracting a named set
    reports it, which is what an unreviewed runner should do.
    """
    job = {"runs-on": label}
    assert label not in GITHUB_HOSTED_LABELS, (
        f"{label!r} only discriminates while it is absent from the hosted "
        "set; adding it there makes this property vacuous"
    )
    assert billable_labels(job) == {label}, (
        f"{label!r} is neither hosted nor reviewed, so it must be reported; "
        f"got {sorted(billable_labels(job))}"
    )


@given(
    fork_arm=hosted_labels,
    branch_arm=paid_labels,
    before=st.sampled_from(["", " ", "  ", "\n      "]),
    after=st.sampled_from(["", " ", "  ", "\n      "]),
)
def test_a_fork_fallback_contributes_both_arms(
    fork_arm: str, branch_arm: str, before: str, after: str
) -> None:
    """Both arms, under any whitespace a folded scalar can produce.

    The whitespace matters: a folded scalar collapses its continuation to a
    single space, but a reader that anchored on one exact spelling would
    accept the correctly written expression and silently stop recognising a
    differently wrapped one, which contributes nothing and so bills for
    nothing as far as the registry is concerned.

    The expectation is computed from the arms that went in, not from a
    second parse.
    """
    runs_on = (
        f"${{{{{before}github.event.pull_request.head.repo.fork"
        f"{after}&& '{fork_arm}' || '{branch_arm}' }}}}"
    )
    job = {"runs-on": runs_on}
    assert labels_of(job) == {fork_arm, branch_arm}, (
        f"a conditional must contribute both arms; {runs_on!r} gave "
        f"{sorted(labels_of(job))}"
    )
    assert billable_labels(job) == {branch_arm}, (
        f"only the arm outside the hosted set bills; got {sorted(billable_labels(job))}"
    )


@given(
    legs=st.lists(
        st.one_of(paid_labels, hosted_labels), min_size=1, max_size=6, unique=True
    )
)
def test_a_matrix_job_contributes_exactly_its_legs(legs: list[str]) -> None:
    """A leg cannot be added without the registry seeing its label.

    The deferral itself names no label, so a reader that returned it would
    report a phantom and a reader that returned nothing would miss every
    leg. The expectation is the set of images put in.
    """
    job = {
        "runs-on": MATRIX_DEFERRAL,
        "strategy": {"matrix": {"include": [{"os": leg} for leg in legs]}},
    }
    assert labels_of(job) == set(legs), (
        f"a matrix job must contribute exactly its legs' images; {legs} gave "
        f"{sorted(labels_of(job))}"
    )
    assert billable_labels(job) == set(legs) - set(GITHUB_HOSTED_LABELS), (
        "a matrix job bills for its legs less the hosted ones; got "
        f"{sorted(billable_labels(job))}"
    )
