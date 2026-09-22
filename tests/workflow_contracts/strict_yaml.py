"""A YAML loader that refuses a mapping repeating a key.

Separated from the document reader because it is a property of YAML rather
than of workflows, and because the reader is read far more often than this is.

PyYAML keeps the last value for a repeated key and says nothing. That is not a
lost byte, it inverts a contract: a workflow declaring ``runs-on`` twice parses
into a document that has discarded the first value, so a lane could carry a
paid label in the discarded half and read as hosted, and the placement contract
would pass on a file that bills.

GitHub Actions and actionlint both reject duplicate mapping keys, so a document
this refuses would never have run. Refusing it costs nothing and turns a silent
wrong answer into a loud one.
"""

from __future__ import annotations

import typing as typ

import yaml
import yaml.constructor
import yaml.resolver


class StrictLoader(yaml.SafeLoader):
    """A ``SafeLoader`` that refuses a mapping repeating a key.

    PyYAML keeps the last value for a repeated key and says nothing. A
    workflow declaring ``runs-on`` twice, or ``jobs`` twice, therefore parses
    into a document that silently discards the earlier value, and every
    contract here then asserts against data the file does not contain: a lane
    could carry a paid label in the discarded half and read as hosted.

    GitHub Actions and actionlint both reject duplicate mapping keys, so a
    document this refuses is one that would never have run anyway. Refusing it
    here means the contracts fail loudly rather than passing on a half of the
    file nobody chose.
    """


def _no_duplicate_keys(
    loader: StrictLoader, node: yaml.MappingNode, *, deep: bool = False
) -> dict[typ.Any, typ.Any]:
    """Construct a mapping, refusing a key that appears more than once.

    Parameters
    ----------
    loader : StrictLoader
        The loader constructing the node.
    node : yaml.MappingNode
        The mapping being constructed.
    deep : bool
        Whether to construct child objects eagerly.

    Returns
    -------
    dict[typ.Any, typ.Any]
        The constructed mapping.

    Raises
    ------
    yaml.constructor.ConstructorError
        If a key appears more than once, with the key and its line.
    """
    mapping: dict[typ.Any, typ.Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            message = (
                f"duplicate mapping key {key!r} at line "
                f"{key_node.start_mark.line + 1}; PyYAML would keep only the "
                "last value and every rule here would then read a document "
                "the file does not contain"
            )
            raise yaml.constructor.ConstructorError(
                None, None, message, key_node.start_mark
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicate_keys
)
