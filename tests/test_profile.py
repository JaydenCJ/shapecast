"""Profiler evidence collection: counts, presence, distinct values, walks."""

from __future__ import annotations

import pytest

from shapecast import Profiler, json_type_of
from shapecast.profile import FieldProfile


def test_json_type_of_distinguishes_all_seven_json_types():
    assert json_type_of(None) == "null"
    # bool is an int subclass in Python: checked before int, or every
    # boolean field would be profiled as integer.
    assert json_type_of(True) == "boolean"
    assert json_type_of(3) == "integer"
    assert json_type_of(3.5) == "number"
    assert json_type_of("x") == "string"
    assert json_type_of({}) == "object"
    assert json_type_of([]) == "array"
    with pytest.raises(TypeError):
        json_type_of({1, 2})


def test_type_counts_accumulate_across_samples(profiled):
    profiler = profiled([{"a": 1}, {"a": "x"}, {"a": None}, {"a": 2}])
    node = profiler.root.children["a"]
    assert node.count == 4
    assert node.type_counts == {"integer": 2, "string": 1, "null": 1}


def test_missing_key_and_null_value_are_counted_separately(profiled):
    # {"a": null} and {} are different API behaviors; presence comes from
    # parent object count vs child count, nullability from null_count.
    profiler = profiled([{"a": None}, {}, {"a": 1}])
    root = profiler.root
    node = root.children["a"]
    assert root.object_count == 3
    assert node.count == 2  # present twice, missing once
    assert node.null_count == 1


def test_nested_paths_are_dotted_and_array_items_bracketed(profiled):
    profiler = profiled([{"user": {"tags": ["a"]}}])
    user = profiler.root.children["user"]
    tags = user.children["tags"]
    assert user.path == "$.user"
    assert tags.path == "$.user.tags"
    assert tags.items.path == "$.user.tags[]"


def test_keys_needing_quoting_get_bracket_paths(profiled):
    profiler = profiled([{"odd key!": 1, "ok-key_2": 2}])
    assert '$["odd key!"]' in [c.path for c in profiler.root.children.values()]
    assert "$.ok-key_2" in [c.path for c in profiler.root.children.values()]


def test_array_items_merge_into_one_profile_with_length_range(profiled):
    profiler = profiled([{"xs": [1, 2, 3]}, {"xs": []}, {"xs": [9]}])
    xs = profiler.root.children["xs"]
    assert (xs.min_items, xs.max_items) == (0, 3)
    assert xs.items.count == 4
    assert xs.items.type_counts == {"integer": 4}


def test_numeric_and_string_ranges_are_tracked(profiled):
    profiler = profiled([{"n": 3, "s": "ab"}, {"n": -1.5, "s": "abcd"}])
    root = profiler.root
    assert (root.children["n"].num_min, root.children["n"].num_max) == (-1.5, 3.0)
    assert (root.children["s"].str_min_len, root.children["s"].str_max_len) == (2, 4)


def test_distinct_values_are_counted_with_type_aware_keys(profiled):
    # 1 and True must not collapse into one bucket (True == 1 in Python).
    profiler = profiled([{"v": 1}, {"v": True}, {"v": 1}])
    node = profiler.root.children["v"]
    assert node.values[("integer", 1)] == 2
    assert node.values[("boolean", True)] == 1
    assert node.distinct_count == 2


def test_value_cap_overflow_disables_distinct_tracking():
    node = FieldProfile("$", value_cap=3)
    for i in range(5):
        node.observe(f"v{i}")
    assert node.values_overflowed
    assert node.distinct_count is None
    assert node.values == {}
    assert node.count == 5  # counting continues past the cap


def test_widened_is_not_a_conflict_but_string_vs_object_is(profiled):
    widened = profiled([{"x": 1}, {"x": 1.5}]).root.children["x"]
    assert widened.is_widened and not widened.has_conflict
    conflicted = profiled([{"x": "a"}, {"x": {}}]).root.children["x"]
    assert conflicted.has_conflict and not conflicted.is_widened


def test_dominant_format_requires_every_string_to_match(profiled):
    all_match = profiled([{"t": "2026-06-01"}, {"t": "2026-06-02"}])
    assert all_match.root.children["t"].dominant_format() == "date"
    one_off = profiled([{"t": "2026-06-01"}, {"t": "yesterday"}])
    assert one_off.root.children["t"].dominant_format() is None
    # Nulls are not strings; they must not break format coverage.
    nullable = profiled([{"t": "2026-06-01"}, {"t": None}])
    assert nullable.root.children["t"].dominant_format() == "date"


def test_enum_values_requires_every_value_to_repeat(profiled):
    closed = profiled([{"s": "on"}, {"s": "off"}, {"s": "on"}, {"s": "off"}])
    assert closed.root.children["s"].enum_values(10) == ["off", "on"]
    # Two values seen once each is two samples, not a closed set.
    sparse = profiled([{"s": "on"}, {"s": "off"}])
    assert sparse.root.children["s"].enum_values(10) is None


def test_enum_values_rejected_on_widened_and_conflicted_fields(profiled):
    # The tracked integers repeat, but they do not cover the float samples;
    # claiming enum [1] for a number field would be a lie.
    widened = profiled([{"x": 1}, {"x": 1}, {"x": 2.5}]).root.children["x"]
    assert widened.enum_values(10) is None
    mixed = profiled([{"x": "a"}, {"x": "a"}, {"x": {}}]).root.children["x"]
    assert mixed.enum_values(10) is None


def test_enum_values_rejected_when_a_format_covers_the_field(profiled):
    # Two repeated emails are still an open set with a shape, not a vocabulary.
    profiler = profiled(
        [{"e": "ana@example.test"}, {"e": "ana@example.test"},
         {"e": "bo@example.test"}, {"e": "bo@example.test"}]
    )
    assert profiler.root.children["e"].enum_values(10) is None


def test_enum_values_tolerates_nulls_and_respects_limit_zero(profiled):
    profiler = profiled([{"s": "a"}, {"s": "a"}, {"s": None}])
    node = profiler.root.children["s"]
    assert node.enum_values(10) == ["a"]  # nulls do not break coverage
    assert node.enum_values(0) is None  # limit 0 disables detection


def test_walk_yields_nodes_with_parents_in_first_seen_order(profiled):
    profiler = profiled([{"b": {"c": 1}, "a": [2]}])
    pairs = [(node.path, parent.path if parent else None) for node, parent in profiler.root.walk()]
    assert pairs == [
        ("$", None),
        ("$.b", "$"),
        ("$.b.c", "$.b"),
        ("$.a", "$"),
        ("$.a[]", "$.a"),
    ]


def test_profiler_add_all_returns_count_and_tracks_samples(profiled):
    profiler = Profiler()
    assert profiler.add_all([1, 2, 3]) == 3
    assert profiler.sample_count == 3
    assert profiler.root.type_counts == {"integer": 3}
