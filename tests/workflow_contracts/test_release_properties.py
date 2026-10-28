"""Properties of release distribution and destination metadata validation."""

from __future__ import annotations

import json
import string
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from scripts import release_assets

_STEM = st.text(alphabet=string.ascii_lowercase + string.digits, min_size=1, max_size=8)
_NAME = _STEM.map(lambda stem: f"{stem}.whl")
_DIGEST = st.text(alphabet=string.hexdigits, min_size=64, max_size=64)
_INDEX_URL = "https://pypi.org/simple/falcon-correlate/"


class TestDigestDiagnostics:
    """Contracts for digest diagnostics."""

    @given(expected=st.lists(_NAME, max_size=12), present=st.sets(_NAME, max_size=12))
    def test_missing_names_are_unique_sorted_and_order_independent(
        self, expected: list[str], present: set[str]
    ) -> None:
        """The destination delta is invariant under input order and repetition."""
        missing = release_assets.missing_names(expected, present)
        oracle = sorted({name for name in expected if name not in present})

        assert missing == oracle, "the delta must contain only absent names once"
        assert release_assets.missing_names(reversed(expected), present) == missing, (
            "reordering expected names must not change the delta"
        )

    @example(
        states={
            "a.whl": "same",
            "b.whl": "missing-github",
            "c.whl": "unknown",
            "d.whl": "different",
            "e.whl": "missing-pypi",
        }
    )
    @given(
        states=st.dictionaries(
            _NAME,
            st.sampled_from((
                "same",
                "missing-github",
                "unknown",
                "different",
                "missing-pypi",
            )),
            max_size=8,
        )
    )
    def test_digest_diagnostics_are_complete_sorted_and_order_independent(
        self,
        states: dict[str, str],
    ) -> None:
        """Each missing or unequal digest is reported once in filename order."""
        index = {
            name: release_assets.PypiFile("a" * 64, f"https://example.org/{name}")
            for name, state in states.items()
            if state != "missing-pypi"
        }
        github = {
            name: None
            if state == "unknown"
            else "b" * 64
            if state == "different"
            else "a" * 64
            for name, state in states.items()
            if state != "missing-github"
        }
        names = list(states)
        problems = release_assets.digest_mismatches(names, index, github)
        expected_bad_names = sorted(
            name for name, state in states.items() if state != "same"
        )
        reported_names = [message.split(" ", maxsplit=1)[0] for message in problems]

        assert reported_names == expected_bad_names, (
            "every missing or unequal digest must be reported once in name order"
        )
        assert (
            release_assets.digest_mismatches(reversed(names), index, github) == problems
        ), "reordering expected names must not alter diagnostics"


class TestDestinationParsers:
    """Contracts for destination parsers."""

    @given(names=st.lists(_NAME, unique=True, max_size=8), digest=_DIGEST)
    def test_pep691_entries_preserve_names_and_normalize_digests(
        self, names: list[str], digest: str
    ) -> None:
        """Valid index entries retain their names and normalize SHA-256 hex."""
        entries = [
            {
                "filename": name,
                "hashes": {"sha256": digest},
                "url": f"https://files.pythonhosted.org/{name}",
            }
            for name in names
        ]
        parsed = release_assets.parse_pep691_index(
            json.dumps({"files": entries}), _INDEX_URL
        )
        expected = {
            name: release_assets.PypiFile(
                digest.lower(), f"https://files.pythonhosted.org/{name}"
            )
            for name in names
        }

        assert parsed == expected, "valid index metadata must map each file correctly"
        assert (
            release_assets.parse_pep691_index(
                json.dumps({"files": list(reversed(entries))}), _INDEX_URL
            )
            == expected
        ), "index ordering must not change the parsed mapping"

    @given(name=_NAME, unsafe=st.sampled_from(("/", "\\", " ", "\n", "%", "@")))
    def test_both_destination_parsers_reject_unsafe_names(
        self, name: str, unsafe: str
    ) -> None:
        """Neither remote metadata source may introduce a path or unsafe name."""
        unsafe_name = f"{name}{unsafe}payload"
        index = {
            "files": [
                {
                    "filename": unsafe_name,
                    "hashes": {"sha256": "a" * 64},
                    "url": "https://example.org/file",
                }
            ]
        }
        release = {"assets": [{"name": unsafe_name, "digest": f"sha256:{'a' * 64}"}]}

        with pytest.raises(release_assets.ReleaseAssetError, match="unsafe"):
            release_assets.parse_pep691_index(json.dumps(index), _INDEX_URL)
        with pytest.raises(release_assets.ReleaseAssetError, match="unsafe"):
            release_assets.parse_github_asset_digests(json.dumps(release))

    @example(name="a.whl", invalid=("invalid SHA-256", "g", "https://example.org/file"))
    @example(
        name="a.whl", invalid=("must use HTTPS", "a" * 64, "http://example.org/file")
    )
    @given(
        name=_NAME,
        invalid=st.one_of(
            st.tuples(
                st.just("invalid SHA-256"),
                st.text(alphabet="ghijkl", min_size=1, max_size=70),
                st.just("https://example.org/file"),
            ),
            st.tuples(
                st.just("must use HTTPS"),
                _DIGEST,
                st.just("http://example.org/file"),
            ),
        ),
    )
    def test_index_rejects_invalid_digest_or_non_https_url(
        self, name: str, invalid: tuple[str, str, str]
    ) -> None:
        """Index metadata must have a valid digest and an HTTPS download URL."""
        message, digest, url = invalid
        body = json.dumps({
            "files": [
                {
                    "filename": name,
                    "hashes": {"sha256": digest},
                    "url": url,
                }
            ]
        })

        with pytest.raises(release_assets.ReleaseAssetError, match=message):
            release_assets.parse_pep691_index(body, _INDEX_URL)

    @given(name=_NAME, digest=_DIGEST)
    def test_duplicate_names_are_rejected_by_both_destination_parsers(
        self, name: str, digest: str
    ) -> None:
        """Duplicate metadata cannot hide which remote bytes belong to a name."""
        entry = {
            "filename": name,
            "hashes": {"sha256": digest},
            "url": "https://example.org/file",
        }
        asset = {"name": name, "digest": f"sha256:{digest}"}

        with pytest.raises(release_assets.ReleaseAssetError, match="repeats"):
            release_assets.parse_pep691_index(
                json.dumps({"files": [entry, entry]}), _INDEX_URL
            )
        with pytest.raises(release_assets.ReleaseAssetError, match="repeats"):
            release_assets.parse_github_asset_digests(
                json.dumps({"assets": [asset, asset]})
            )

    @given(name=_NAME, digest=_DIGEST)
    def test_github_digest_metadata_normalizes_hex(
        self, name: str, digest: str
    ) -> None:
        """Valid GitHub SHA-256 metadata is normalized without losing the name."""
        body = json.dumps({"assets": [{"name": name, "digest": f"sha256:{digest}"}]})

        assert release_assets.parse_github_asset_digests(body) == {
            name: digest.lower()
        }, "a valid GitHub digest must be returned as lowercase hex"

    @given(
        name=_NAME, invalid_digest=st.text(alphabet="ghijkl", min_size=1, max_size=70)
    )
    def test_github_invalid_digest_is_reported_as_unknown(
        self, name: str, invalid_digest: str
    ) -> None:
        """Unusable GitHub hashes are unknown, not trusted as verified bytes."""
        body = json.dumps({
            "assets": [{"name": name, "digest": f"sha256:{invalid_digest}"}]
        })

        assert release_assets.parse_github_asset_digests(body) == {name: None}, (
            "an invalid GitHub digest must not be treated as verified"
        )


class TestDistributionCollection:
    """Contracts for distribution collection."""

    @given(
        wheel_stems=st.lists(_STEM, min_size=1, max_size=4, unique=True), sdist=_STEM
    )
    def test_collection_keeps_every_wheel_and_one_source_archive(
        self, wheel_stems: list[str], sdist: str
    ) -> None:
        """Every wheel survives collection and the sole sdist follows the wheels."""
        wheel_names = [f"{stem}.whl" for stem in wheel_stems]
        sdist_name = f"{sdist}.tar.gz"
        with TemporaryDirectory(prefix="release-distributions-") as temporary_directory:
            directory = Path(temporary_directory)
            for name in (*wheel_names, sdist_name):
                (directory / name).touch()
            collected = release_assets.collect_distributions(directory)

        assert [path.name for path in collected] == [
            *sorted(wheel_names),
            sdist_name,
        ], "collection must return every wheel in order and exactly one sdist"

    @pytest.mark.parametrize("sdist_count", [0, 2], ids=["missing", "duplicate"])
    @given(
        wheel=_STEM, sdist_stems=st.lists(_STEM, min_size=2, max_size=2, unique=True)
    )
    def test_collection_rejects_missing_or_multiple_sdists(
        self, wheel: str, sdist_stems: list[str], sdist_count: int
    ) -> None:
        """A wheel set is rejected whenever its source archive count is not one."""
        with TemporaryDirectory(prefix="release-distributions-") as temporary_directory:
            directory = Path(temporary_directory)
            (directory / f"{wheel}.whl").touch()
            for stem in sdist_stems[:sdist_count]:
                (directory / f"{stem}.tar.gz").touch()
            with pytest.raises(release_assets.ReleaseAssetError, match="exactly one"):
                release_assets.collect_distributions(directory)
