"""The statistical profiler at the heart of shapecast.

A :class:`Profiler` consumes decoded JSON samples one at a time and maintains
a tree of :class:`FieldProfile` nodes, one per JSON path (``$``, ``$.user.id``,
``$.items[]`` …). Every node records *evidence*, not conclusions:

- how many times the path was observed, per JSON type (``null`` included);
- for object members, how often the key was present vs. missing in the parent
  (presence and nullability are different failure modes — a key that is
  sometimes absent and a key that is sometimes ``null`` need different code);
- numeric ranges, string length ranges, array length ranges;
- distinct scalar values up to a cap (enum candidates);
- per-format match counts for strings (see :mod:`shapecast.formats`).

Schema generation (:mod:`shapecast.schema`) and reporting
(:mod:`shapecast.report`) are pure functions over this tree, so the same
single pass over the data feeds both outputs.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

from .formats import FORMAT_PRIORITY, detect_formats

#: Every JSON type shapecast distinguishes, in canonical display order.
JSON_TYPES: Tuple[str, ...] = (
    "null",
    "boolean",
    "integer",
    "number",
    "string",
    "object",
    "array",
)

#: How many distinct scalar values a node tracks before giving up. This only
#: bounds enum detection; counts and ranges keep updating past the cap.
DEFAULT_VALUE_CAP = 50


def json_type_of(value: Any) -> str:
    """Return the JSON type name of a decoded Python value.

    ``bool`` is checked before ``int`` because ``bool`` is an ``int`` subclass
    in Python — without this, ``true`` would be profiled as an integer.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, (list, tuple)):
        return "array"
    raise TypeError(f"value of type {type(value).__name__} is not a JSON value")


class FieldProfile:
    """Accumulated evidence for one JSON path across all samples."""

    def __init__(self, path: str, value_cap: int = DEFAULT_VALUE_CAP):
        self.path = path
        self.value_cap = value_cap
        #: Times this path held any value at all (including null).
        self.count = 0
        self.type_counts: Dict[str, int] = {}
        # Numeric evidence (integers and floats share one range).
        self.num_min: Optional[float] = None
        self.num_max: Optional[float] = None
        # String evidence.
        self.str_min_len: Optional[int] = None
        self.str_max_len: Optional[int] = None
        self.format_counts: Dict[str, int] = {}
        # Distinct scalar values -> occurrence count, keyed by (type, value)
        # so that true/1 and 1/1.0 never collapse into one bucket.
        self.values: Dict[Tuple[str, Any], int] = {}
        self.values_overflowed = False
        # Array evidence: one merged profile for all items.
        self.items: Optional[FieldProfile] = None
        self.min_items: Optional[int] = None
        self.max_items: Optional[int] = None
        # Object evidence: child key -> profile, in first-seen order.
        self.children: Dict[str, FieldProfile] = {}

    # ------------------------------------------------------------------ #
    # Observation
    # ------------------------------------------------------------------ #

    def observe(self, value: Any) -> None:
        """Fold one observed value into this node (recursing into containers)."""
        kind = json_type_of(value)
        self.count += 1
        self.type_counts[kind] = self.type_counts.get(kind, 0) + 1

        if kind in ("integer", "number"):
            number = float(value)
            self.num_min = number if self.num_min is None else min(self.num_min, number)
            self.num_max = number if self.num_max is None else max(self.num_max, number)
            if kind == "integer":
                self._track_value(kind, value)
        elif kind == "string":
            length = len(value)
            self.str_min_len = length if self.str_min_len is None else min(self.str_min_len, length)
            self.str_max_len = length if self.str_max_len is None else max(self.str_max_len, length)
            for name in detect_formats(value):
                self.format_counts[name] = self.format_counts.get(name, 0) + 1
            self._track_value(kind, value)
        elif kind == "boolean":
            self._track_value(kind, value)
        elif kind == "array":
            size = len(value)
            self.min_items = size if self.min_items is None else min(self.min_items, size)
            self.max_items = size if self.max_items is None else max(self.max_items, size)
            if self.items is None:
                self.items = FieldProfile(f"{self.path}[]", self.value_cap)
            for item in value:
                self.items.observe(item)
        elif kind == "object":
            for key, child_value in value.items():
                child = self.children.get(key)
                if child is None:
                    child = FieldProfile(self._child_path(key), self.value_cap)
                    self.children[key] = child
                child.observe(child_value)

    def _child_path(self, key: str) -> str:
        # Bracket-quote keys that would make the dotted path ambiguous.
        if key and all(ch.isalnum() or ch in "_-" for ch in key):
            return f"{self.path}.{key}"
        return f'{self.path}["{key}"]'

    def _track_value(self, kind: str, value: Any) -> None:
        if self.values_overflowed:
            return
        key = (kind, value)
        if key in self.values:
            self.values[key] += 1
        elif len(self.values) < self.value_cap:
            self.values[key] = 1
        else:
            # Past the cap the set is no longer complete, so enum claims
            # would be lies; drop the partial tally entirely.
            self.values = {}
            self.values_overflowed = True

    # ------------------------------------------------------------------ #
    # Derived evidence
    # ------------------------------------------------------------------ #

    @property
    def null_count(self) -> int:
        return self.type_counts.get("null", 0)

    @property
    def object_count(self) -> int:
        return self.type_counts.get("object", 0)

    @property
    def string_count(self) -> int:
        return self.type_counts.get("string", 0)

    @property
    def non_null_types(self) -> List[str]:
        """Non-null JSON types seen at this path, in canonical order."""
        return [t for t in JSON_TYPES if t != "null" and t in self.type_counts]

    @property
    def has_conflict(self) -> bool:
        """True when samples disagree on the field's fundamental type.

        An integer/number mix is *widening*, not a conflict — every JSON
        number consumer must already handle both. Anything else (string vs
        object, boolean vs array …) is a genuine contradiction worth flagging.
        """
        kinds = set(self.non_null_types)
        if {"integer", "number"} <= kinds:
            kinds.discard("integer")
        return len(kinds) > 1

    @property
    def is_widened(self) -> bool:
        """True when both integers and floats were observed."""
        return "integer" in self.type_counts and "number" in self.type_counts

    @property
    def distinct_count(self) -> Optional[int]:
        """Number of distinct scalar values, or ``None`` once past the cap."""
        if self.values_overflowed:
            return None
        return len(self.values)

    def dominant_format(self) -> Optional[str]:
        """The highest-priority format matched by *all* string samples."""
        if self.string_count == 0:
            return None
        for name in FORMAT_PRIORITY:
            if self.format_counts.get(name, 0) == self.string_count:
                return name
        return None

    def enum_values(self, limit: int) -> Optional[List[Any]]:
        """Enum candidates, or ``None`` when the evidence does not justify one.

        Claiming ``enum`` is claiming the set is *closed*, so the bar is
        deliberately high. All of these must hold:

        - the value set is complete (never overflowed the tracking cap);
        - one scalar type (string, integer or boolean) accounts for every
          non-null observation — a widened int/number field or a conflicted
          field must never claim an enum from a subset of its samples;
        - no string format was detected: values that all parse as UUIDs,
          emails or timestamps are evidence of an *open* set with a shape,
          not a closed vocabulary;
        - at most ``limit`` distinct values;
        - every distinct value was observed at least twice. Three values
          seen three times each is evidence of a closed set; three values
          seen once each is just three samples.
        """
        if limit <= 0 or self.values_overflowed or not self.values:
            return None
        kinds = {kind for kind, _ in self.values}
        if len(kinds) != 1 or kinds - {"string", "integer", "boolean"}:
            return None
        scalar_kind = next(iter(kinds))
        if self.type_counts.get(scalar_kind, 0) != self.count - self.null_count:
            return None
        if scalar_kind == "string" and self.dominant_format() is not None:
            return None
        if len(self.values) > limit or min(self.values.values()) < 2:
            return None
        return sorted(value for _, value in self.values)

    # ------------------------------------------------------------------ #
    # Traversal
    # ------------------------------------------------------------------ #

    def walk(self) -> Iterator[Tuple["FieldProfile", Optional["FieldProfile"]]]:
        """Yield ``(node, parent)`` pairs depth-first in first-seen order."""
        stack: List[Tuple[FieldProfile, Optional[FieldProfile]]] = [(self, None)]
        while stack:
            node, parent = stack.pop()
            yield node, parent
            pending: List[Tuple[FieldProfile, Optional[FieldProfile]]] = []
            if node.items is not None:
                pending.append((node.items, node))
            pending.extend((child, node) for child in node.children.values())
            stack.extend(reversed(pending))


class Profiler:
    """Feeds samples into a :class:`FieldProfile` tree rooted at ``$``."""

    def __init__(self, value_cap: int = DEFAULT_VALUE_CAP):
        self.root = FieldProfile("$", value_cap)
        self.sample_count = 0

    def add(self, sample: Any) -> None:
        """Profile one decoded JSON sample."""
        self.root.observe(sample)
        self.sample_count += 1

    def add_all(self, samples: Iterable[Any]) -> int:
        """Profile every sample from an iterable; returns how many were added."""
        added = 0
        for sample in samples:
            self.add(sample)
            added += 1
        return added
