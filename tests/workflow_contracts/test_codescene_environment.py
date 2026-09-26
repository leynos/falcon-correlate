"""CV-005: the ``codescene`` environment sits on the uploading job alone.

The repository's own workflows are checked first. Each other test changes a
copy of the parsed workflows the way a later edit could, and asserts that the
clause meant to catch it does. The check step, the ref guard and
``access-token:`` stay held by the publisher contracts.
"""

from __future__ import annotations

import copy
import typing as typ

import pytest

from tests.workflow_contracts.codescene_environment import (
    MISSING,
    NO_UPLOADER,
    REACHABLE,
    STRAY,
    environment_violations,
)
from tests.workflow_contracts.codescene_lanes import parse, workflow_texts

PUBLISHER = "coverage-main.yml"
PUBLISHER_JOB = "coverage-upload"
PR_WORKFLOW = "ci.yml"
PR_JOB = "test"

Documents = dict[str, dict[str, typ.Any]]


@pytest.fixture(name="documents")
def fixture_documents() -> Documents:
    """Return a fresh copy of every workflow, parsed.

    Returns
    -------
    Documents
        File name to parsed document; each test may change its copy.
    """
    return copy.deepcopy({
        name: parse(name, text) for name, text in workflow_texts().items()
    })


def _job(documents: Documents, name: str, job: str) -> dict[str, typ.Any]:
    """Return one job mapping from the parsed documents."""
    return documents[name]["jobs"][job]


def _reports(documents: Documents, message: str) -> bool:
    """Return whether the rule reports *message* over *documents*."""
    return any(message in problem for problem in environment_violations(documents))


def test_the_repository_places_the_environment(documents: Documents) -> None:
    """The publisher declares the environment, and nothing else does."""
    assert not environment_violations(documents)


def test_the_publisher_cannot_drop_the_environment(documents: Documents) -> None:
    """Without it the token never reaches the upload, which then skips."""
    _job(documents, PUBLISHER, PUBLISHER_JOB).pop("environment", None)

    assert _reports(documents, MISSING)


def test_the_publisher_cannot_name_another_environment(
    documents: Documents,
) -> None:
    """Another environment holds no CodeScene token."""
    _job(documents, PUBLISHER, PUBLISHER_JOB)["environment"] = "production"

    assert _reports(documents, MISSING)


def test_the_mapping_form_is_accepted(documents: Documents) -> None:
    """``{name: codescene}`` is the same declaration as the bare string."""
    _job(documents, PUBLISHER, PUBLISHER_JOB)["environment"] = {"name": "codescene"}

    assert not environment_violations(documents)


def test_no_other_job_may_declare_it(documents: Documents) -> None:
    """A second holder of the token widens what can read it."""
    documents[PUBLISHER]["jobs"]["other"] = {
        "runs-on": "ubuntu-latest",
        "environment": "codescene",
        "steps": [{"run": "true"}],
    }

    assert _reports(documents, STRAY)


def test_no_pull_request_job_may_declare_it(documents: Documents) -> None:
    """A pull request's own code must never be able to request the token."""
    _job(documents, PR_WORKFLOW, PR_JOB)["environment"] = {"name": "codescene"}

    assert _reports(documents, REACHABLE)


def test_an_empty_reading_is_refused(documents: Documents) -> None:
    """With no uploader left the rule says so rather than passing."""
    job = _job(documents, PUBLISHER, PUBLISHER_JOB)
    job["steps"] = [
        step
        for step in job["steps"]
        if "upload-codescene-coverage" not in str(step.get("uses", ""))
    ]

    assert _reports(documents, NO_UPLOADER)
