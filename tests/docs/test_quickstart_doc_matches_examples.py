"""Drift guard for quickstart snippets embedded in Markdown."""

from __future__ import annotations

import ast
import pathlib
import re

_QUICKSTART_DOC = pathlib.Path("docs/quickstart.md")
_EXAMPLES_DIR = pathlib.Path("examples/quickstart")
_MARKER_PATTERN = re.compile(
    r"<!-- quickstart:(?P<id>[a-z0-9-]+) -->\s*```python\n(?P<src>.*?)\n```",
    re.DOTALL,
)
_START_PATTERN = re.compile(r"^# \[quickstart:(?P<id>[a-z0-9-]+)\]\s*$")
_END_TEMPLATE = "# [/quickstart:{region_id}]"


def test_quickstart_doc_snippets_match_example_regions() -> None:
    """Verify every documented quickstart snippet matches runnable source."""
    guide_regions = _extract_guide_regions(_QUICKSTART_DOC)
    source_regions = _extract_source_regions(_EXAMPLES_DIR)

    assert guide_regions.keys() == source_regions.keys()
    for region_id, guide_src in guide_regions.items():
        source_src = source_regions[region_id]
        assert _normalised_ast(guide_src) == _normalised_ast(source_src), region_id


def _extract_guide_regions(path: pathlib.Path) -> dict[str, str]:
    """Extract tagged Python fences from the quickstart guide."""
    assert path.exists(), f"{path} must exist"
    text = path.read_text(encoding="utf-8")
    return {
        match.group("id"): match.group("src")
        for match in _MARKER_PATTERN.finditer(text)
    }


def _extract_source_regions(directory: pathlib.Path) -> dict[str, str]:
    """Extract sentinel-delimited regions from quickstart source modules."""
    assert directory.exists(), f"{directory} must exist"
    regions: dict[str, str] = {}
    for path in sorted(directory.glob("*.py")):
        regions.update(_extract_regions_from_source(path))
    return regions


def _extract_regions_from_source(path: pathlib.Path) -> dict[str, str]:
    """Extract all quickstart regions from one source file."""
    regions: dict[str, str] = {}
    current_id: str | None = None
    current_lines: list[str] = []

    for line in path.read_text(encoding="utf-8").splitlines():
        start = _START_PATTERN.match(line)
        if start is not None:
            assert current_id is None, f"nested quickstart region in {path}"
            current_id = start.group("id")
            current_lines = []
            continue
        if current_id is not None and line == _END_TEMPLATE.format(
            region_id=current_id,
        ):
            regions[current_id] = "\n".join(current_lines)
            current_id = None
            current_lines = []
            continue
        if current_id is not None:
            current_lines.append(line)

    assert current_id is None, f"unterminated quickstart region in {path}"
    return regions


def _normalised_ast(source: str) -> str:
    """Return a stable AST representation for semantically comparing snippets."""
    return ast.dump(ast.parse(source), include_attributes=False)
