"""Turn a :class:`~shapecast.profile.FieldProfile` tree into a JSON Schema.

The emitted schema targets **draft 2020-12** and is deliberately conservative:
every keyword in it is backed by the evidence the profiler collected, and
nothing is guessed from a single sample.

- ``type`` unions come straight from observed type counts; an
  integer/number mix widens to ``number`` (never a union of the two).
- ``required`` lists the keys present in at least ``required_threshold`` of
  the parent object's occurrences (default: all of them).
- ``enum`` appears only when the complete value set is small **and** values
  repeat — three values seen once each is three samples, not a closed set.
- ``format`` appears only when every string sample matched the detector.
- With ``evidence=True`` every subschema carries an ``x-shapecast`` block
  (counts, rates, ranges) so the numbers behind each decision travel with
  the schema. ``x-``-prefixed keys are ignored by JSON Schema validators.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Union

from .profile import FieldProfile, Profiler

#: The dialect the generated schemas declare.
SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"

# Tolerance for the required-threshold comparison so a rate that is exactly
# the threshold (e.g. 95 of 100 vs 0.95) never fails on float rounding.
_EPSILON = 1e-9


def _rate(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0.0


def _type_list(node: FieldProfile) -> List[str]:
    """Observed types for the ``type`` keyword, integer widened as needed."""
    types: List[str] = []
    for name in node.non_null_types:
        if name == "integer" and node.is_widened:
            continue  # covered by "number"
        types.append(name)
    if node.null_count > 0:
        types.append("null")
    return types


def _evidence_block(node: FieldProfile, parent: Optional[FieldProfile]) -> Dict[str, Any]:
    block: Dict[str, Any] = {
        "seen": node.count,
        "types": dict(sorted(node.type_counts.items())),
    }
    if node.null_count:
        block["nullRate"] = _rate(node.null_count, node.count)
    if parent is not None and parent.object_count:
        block["presence"] = {
            "present": node.count,
            "of": parent.object_count,
            "rate": _rate(node.count, parent.object_count),
        }
    if node.num_min is not None:
        low = int(node.num_min) if not node.is_widened and "number" not in node.type_counts else node.num_min
        high = int(node.num_max) if not node.is_widened and "number" not in node.type_counts else node.num_max
        block["range"] = [low, high]
    if node.str_min_len is not None:
        block["stringLength"] = [node.str_min_len, node.str_max_len]
    if node.min_items is not None:
        block["arrayLength"] = [node.min_items, node.max_items]
    if node.distinct_count is not None and node.distinct_count > 0:
        block["distinct"] = node.distinct_count
    return block


def _node_schema(
    node: FieldProfile,
    parent: Optional[FieldProfile],
    required_threshold: float,
    enum_limit: int,
    formats: bool,
    evidence: bool,
) -> Dict[str, Any]:
    if node.count == 0:
        # Never observed (e.g. the item profile of arrays that were always
        # empty): the honest schema accepts anything.
        return {}

    schema: Dict[str, Any] = {}
    types = _type_list(node)
    if len(types) == 1:
        schema["type"] = types[0]
    elif types:
        schema["type"] = types

    if formats and node.non_null_types == ["string"]:
        fmt = node.dominant_format()
        if fmt is not None:
            schema["format"] = fmt

    enum_values = node.enum_values(enum_limit)
    if enum_values is not None:
        schema["enum"] = enum_values + [None] if node.null_count else enum_values

    if node.children:
        properties: Dict[str, Any] = {}
        for key, child in node.children.items():
            properties[key] = _node_schema(
                child, node, required_threshold, enum_limit, formats, evidence
            )
        schema["properties"] = properties
        object_count = node.object_count
        required = sorted(
            key
            for key, child in node.children.items()
            if object_count and (child.count / object_count) + _EPSILON >= required_threshold
        )
        if required:
            schema["required"] = required

    if "array" in node.type_counts:
        schema["items"] = (
            _node_schema(node.items, node, required_threshold, enum_limit, formats, evidence)
            if node.items is not None
            else {}
        )

    if evidence:
        schema["x-shapecast"] = _evidence_block(node, parent)
    return schema


def to_schema(
    source: Union[Profiler, FieldProfile],
    required_threshold: float = 1.0,
    enum_limit: int = 10,
    formats: bool = True,
    evidence: bool = False,
    title: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a draft 2020-12 JSON Schema from profiled evidence.

    *source* is a :class:`Profiler` (or its root :class:`FieldProfile`).
    ``required_threshold`` is the minimum presence rate for a key to be
    listed in ``required`` (1.0 = present in every parent object).
    ``enum_limit`` caps enum size; ``0`` disables enum detection entirely.
    """
    if not 0.0 < required_threshold <= 1.0:
        raise ValueError("required_threshold must be in (0, 1]")
    root = source.root if isinstance(source, Profiler) else source
    schema: Dict[str, Any] = {"$schema": SCHEMA_DIALECT}
    if title:
        schema["title"] = title
    schema.update(
        _node_schema(root, None, required_threshold, enum_limit, formats, evidence)
    )
    return schema


def dump_schema(schema: Dict[str, Any], indent: int = 2) -> str:
    """Serialize a schema with sorted keys for stable, diff-friendly output."""
    return json.dumps(schema, indent=indent, sort_keys=True, ensure_ascii=False)
