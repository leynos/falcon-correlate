# Architectural decision record (ADR) 002: tested documentation examples

## Status

Accepted on 2026-06-24. The quickstart guide embeds snippets from runnable
Python modules and uses an AST drift guard to keep the prose and source in sync.

## Date

2026-06-24.

## Context and Problem Statement

The quickstart guide needs examples that newcomers can copy, but Markdown-only
code fences are easy to let drift. This project already treats formatting,
linting, typechecking, unit tests, behavioural tests, and documentation linting
as commit gates, so the tutorial examples need to participate in those gates
rather than living only in prose.

Several Markdown execution tools were considered, including `doctest`, Sybil,
pytest-markdown-docs, mktestdocs, phmdoctest/phmutest, pytest-examples, and
pytest-codeblocks. They can execute fenced code, but they do not make those
fences normal Python modules inspected by Ruff, `ty`, and PyPy-backed Pylint.
Byte-for-byte snippet comparison was also rejected because it fails on harmless
formatter changes and comments.

## Decision

Keep runnable documentation examples under `examples/`. For the quickstart, the
source modules live under `examples/quickstart/` and are imported directly by
tests.

Embed guide-visible regions by placing sentinel comments around source regions:

```python
# [quickstart:region-id]
app.add_route("/hello", HelloResource())
# [/quickstart:region-id]
```

Place a matching HTML marker immediately before each Markdown Python fence:

````markdown
<!-- quickstart:region-id -->

```python
app.add_route("/hello", HelloResource())
```
````

`tests/docs/test_quickstart_doc_matches_examples.py` parses both sides and
compares `ast.dump(ast.parse(...), include_attributes=False)`. This checks the
semantic Python shape while ignoring whitespace, comments, and line wrapping.

`make lint` includes `examples` in `PYLINT_TARGETS` so the second lint tier
inspects runnable examples as well as `src` and `tests`.

## Consequences

Positive consequences:

- Tutorial examples are importable, typechecked, linted, tested, and
  behaviourally exercised.
- The quickstart can show short snippets while source files remain the
  executable source of truth.
- The AST guard catches semantic drift without creating brittle formatting
  failures.

Negative consequences:

- Contributors must maintain sentinel comments in source and HTML markers in
  Markdown when changing quickstart snippets.
- Snapshot testing adds a dev-only dependency on `syrupy`.
- The lint gate now checks `examples`, so example code must meet the same style
  bar as tests and package source.
