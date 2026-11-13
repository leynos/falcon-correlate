# Architectural decision record (ADR) 005: attested, reconciled release pipeline

## Status

Accepted on 2026-10-26. Version 0.2.0 will be the first release published with
an sdist, a wheel, and build provenance; PyPI is the source of truth and the
GitHub Release is its reconciled second destination.

## Date

2026-10-26.

## Context and problem statement

The earlier `release.yml` published a GitHub Release before uploading any
assets. Its artefact download path no longer matched the artefact names, and
the empty upload was silently accepted. The `v0.1.0` release consequently has
no assets. The project has no PyPI release, although its installation guides
already direct users to install `falcon-correlate`.

The project is pure Python and uses the `uv_build` backend. A release must
prove that its source distribution builds, publish that sdist and its wheel,
and preserve the exact bytes described by provenance when a tag is run again.
PyPI rejects duplicate filenames, and neither destination may silently replace
files consumers may already have downloaded.

The design follows the merged
[cuprum release pipeline](https://github.com/leynos/cuprum/blob/main/docs/adr-017-release-pipeline.md)
and the pure-Python port in
[polythene ADR-002](https://github.com/leynos/polythene/blob/ae72080/docs/adr-002-attested-reconciled-release-pipeline.md),
with adaptation for one platform-independent wheel, `uv_build`, and no release
telemetry.

## Decision Drivers

- Publish exactly one sdist and one pure-Python wheel for each release.
- Attest the built bytes before they leave the workflow run.
- Make a repeated tag safe without overwriting either destination.
- Reconcile GitHub assets against the bytes PyPI already holds.
- Give each job only the permissions it needs and use OIDC for PyPI.
- Fail clearly on an empty or invalid release distribution set.

## Options considered

### Publish only to GitHub Releases

This would keep the current destination but leave the documented
`pip install falcon-correlate` command unusable from PyPI. It also would not
provide an install source independent of GitHub Releases.

### Upload to PyPI and GitHub without reconciliation

A direct upload to both destinations can leave them with different bytes after
a partial run or a rebuild. Using `--clobber` would hide that disagreement by
replacing files consumers may have already verified.

### Reconcile both destinations with PyPI as the source of truth

The release workflow publishes missing names to PyPI, then downloads PyPI's
bytes for any missing GitHub assets. It verifies the digests before publishing
the draft. Repeated runs add only missing assets and preserve existing bytes.

## Decision outcome

Adopt the per-filename reconciliation model with PyPI as the source of truth
and the tag's GitHub Release as the second, reconciled destination.

- `pure-wheel` runs `uv build --out-dir dist`. This builds the sdist first and
  builds the wheel from it. The pull-request build checks for exactly one sdist
  and one wheel, installs the wheel into a clean environment, and imports
  `falcon_correlate` without the optional Celery or HTTPX dependencies.
- `check-version` requires the exact string match between the tag and
  `pyproject.toml`: `v0.2.0` matches `0.2.0`. It reports PEP 440
  pre-release/dev classification, and every job that attests, uploads, or
  releases depends on it.
- `attest` collects every wheel and exactly one sdist, rejects unknown or
  missing files, and attests the files with `actions/attest-build-provenance`.
  It names the Sigstore bundle after the tag alone and carries distributions
  plus the bundle in `release-dist`.
- `publish-pypi` runs in the `pypi` environment with `contents: read` and
  `id-token: write`. It reads the PEP 691 Simple index, stages only filenames
  PyPI does not list, and uses `pypa/gh-action-pypi-publish` with
  `skip-existing: true`. It stores no PyPI token.
- `draft-release` creates the tag's GitHub Release as a draft or reuses the
  existing release. `publish-release` waits for PyPI and the draft, adds only
  missing release assets using PyPI's bytes, checks SHA-256 digests across both
  destinations, and then publishes the release with the pre-release flag from
  `check-version`.
- A distribution set with no wheel or not exactly one sdist fails. No empty
  release can be published. The release job uses pinned actions, disabled
  checkout credentials, top-level `permissions: {}`, least-privilege job
  grants, and `cancel-in-progress: false`.
- Release telemetry is omitted. The Actions run history and artefact
  attestations provide the required record without adding an unneeded sink.

## Goals and non-goals

- Goals:
  - Publish attestable source and wheel distributions to PyPI.
  - Keep the same distribution bytes on PyPI and GitHub Releases.
  - Make retries safe after either destination has accepted part of a release.
  - Keep ordinary imports free of Celery and HTTPX extras.
- Non-goals:
  - Build platform-specific wheels; the package contains no native code.
  - Back-fill assets onto the asset-less `v0.1.0` GitHub Release.
  - Add a PyPI API token, release telemetry service, or release tag in this
    change.

## Consequences

The untagged `0.2.0` changelog entry is re-dated to 2026-10-26 and will be
published unchanged as the first PyPI release with distributions. The `v0.1.0`
GitHub Release remains asset-less; the artefact download-path defect is
recorded in `CHANGELOG.md` rather than repaired with unaudited manual uploads.

The PyPI project endpoint currently returns 404. Before the first release,
maintainers must create a pending Trusted Publisher for project
`falcon-correlate`, owner `leynos`, repository `falcon-correlate`, workflow
`release.yml`, and environment `pypi`. PyPI creates the project on the first
trusted publish; a pending publisher does not reserve the name. The GitHub
`pypi` environment must separately restrict deployments to tags matching
`v*.*.*`. If the distribution name is unavailable at registration, change
`[project].name`, the Simple-index URLs, and all eight install commands while
retaining the `falcon_correlate` import package. See the
[PyPI Trusted Publisher instructions](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).

## Known risks and limitations

- PyPI's Simple index may lag after an upload. The workflow retries bounded,
  time-limited requests and fails rather than guessing on other HTTP errors; a
  later run can safely continue from the files already published.
- A digest disagreement leaves the GitHub Release as a draft and requires
  manual recovery. PyPI files cannot be deleted or overwritten by this pipeline.
- GitHub environment rules and the PyPI pending publisher are account or
  repository settings. They must be configured before the first tag and cannot
  be established by a source-code change alone.
- A pending PyPI publisher does not reserve the project name until its first
  trusted publish. Another account could register the name first.
