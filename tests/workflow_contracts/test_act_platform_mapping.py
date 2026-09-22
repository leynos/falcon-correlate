"""Contract: every runner label in use is one ``act`` can run.

``act`` skips a job whose label it cannot map and exits zero, printing
``Skipping unsupported platform``. Nothing fails. The act integration tests
then assert against a job that never ran, and they are excluded from CI
besides, so removing or misspelling a mapping is invisible in both places at
once.

This contract runs in CI and derives the required labels from the workflow
the act harness is actually pointed at, rather than naming them. A
handwritten assertion that ``ubicloud-standard-2`` is mapped would go stale
the day a lane moves to a different runner, which is the same class of gap
the registry contract refuses next door.

The domain is one workflow, not all of them, and writing it the other way
round was the first version of this file. ``build-wheels.yml`` matrixes over
Windows and macOS, which act cannot host at any mapping, so a contract over
every lane in the repository demanded mappings that cannot exist. The
distinction is kept explicit below: an unmapped Linux label is a mapping to
add, and a Windows or macOS label in the act workflow is a lane act can no
longer cover. Those are different problems and the contract names which one
it found.
"""

from __future__ import annotations

from tests.workflow_contracts.runner_lanes import labels_of
from tests.workflow_contracts.workflow_documents import jobs_of, text_of, workflow_texts
from tests.workflows.act_platforms import (
    ACT_PLATFORM_IMAGES,
    ACT_WORKFLOW,
    UNHOSTABLE_PLATFORM_PREFIXES,
    UNSUPPORTED_PLATFORM_MESSAGE,
    act_platform_arguments,
)


def _labels_in_the_act_workflow() -> set[str]:
    """Return every literal runner label the act workflow's lanes resolve to."""
    jobs = jobs_of(text_of(workflow_texts(), ACT_WORKFLOW), ACT_WORKFLOW)
    labels: set[str] = set()
    for job in jobs.values():
        labels |= {label for label in labels_of(job) if not label.startswith("${{")}
    return labels


class TestActPlatformMapping:
    """Every runner label the act workflow uses is one act can run."""

    def test_no_act_lane_moved_to_a_platform_act_cannot_host(self) -> None:
        """Said first, because it is not a missing mapping.

        act runs Linux containers. A Windows or macOS lane in the act workflow
        cannot be fixed by adding a mapping, and reporting it as one would send
        the reader to the wrong file.
        """
        unhostable = sorted(
            label
            for label in _labels_in_the_act_workflow()
            if label.startswith(UNHOSTABLE_PLATFORM_PREFIXES)
        )
        assert not unhostable, (
            f"{ACT_WORKFLOW} has lanes on {unhostable}, which act cannot host at "
            "any mapping. Either the act harness no longer covers those lanes, "
            "which the guide must say, or the placement is wrong"
        )

    def test_every_label_in_the_act_workflow_is_one_act_can_run(self) -> None:
        """Containment, and derived rather than listed.

        Equality is wrong here and containment is right: the mapping may name a
        label no lane currently uses, because a mapping costs nothing and a
        missing one costs a silently skipped job. What it may not do is omit a
        label a lane in the act workflow resolves to.
        """
        missing = _labels_in_the_act_workflow() - set(ACT_PLATFORM_IMAGES)
        assert not missing, (
            f"these labels are used by a lane in {ACT_WORKFLOW} and unmapped for "
            f"act: {sorted(missing)}. act would skip those jobs, print "
            f"{UNSUPPORTED_PLATFORM_MESSAGE!r} and exit zero, so the act tests "
            "would assert nothing about them"
        )

    def test_every_mapping_names_an_image(self) -> None:
        """A label mapped to an empty string is a mapping act cannot use."""
        empty = sorted(
            label for label, image in ACT_PLATFORM_IMAGES.items() if not image
        )
        assert not empty, f"these labels map to no image: {empty}"

    def test_the_arguments_carry_every_mapping_in_the_shape_act_expects(self) -> None:
        """The mapping and the command line must not drift apart.

        The tests call ``act`` with the flattened arguments, not with the
        mapping, so a mapping that is correct and arguments that do not carry it
        would leave the label unmapped at the point it matters.
        """
        arguments = act_platform_arguments()
        assert len(arguments) == 2 * len(ACT_PLATFORM_IMAGES)
        pairs = {
            arguments[index + 1]
            for index in range(0, len(arguments), 2)
            if arguments[index] == "-P"
        }
        assert pairs == {
            f"{label}={image}" for label, image in ACT_PLATFORM_IMAGES.items()
        }
