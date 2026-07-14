"""Schema generation: every keyword must be justified by the evidence."""

from __future__ import annotations

import json

import pytest

from shapecast import dump_schema, to_schema
from shapecast.schema import SCHEMA_DIALECT


def test_root_schema_declares_the_2020_12_dialect(profiled):
    schema = to_schema(profiled([{"a": 1}]))
    assert schema["$schema"] == SCHEMA_DIALECT
    assert schema["type"] == "object"
    assert "title" not in schema
    titled = to_schema(profiled([{}]), title="Orders API")
    assert titled["title"] == "Orders API"


def test_always_present_keys_are_required_and_sorted(profiled):
    schema = to_schema(profiled([{"b": 1, "a": 2}, {"a": 3, "b": 4}]))
    assert schema["required"] == ["a", "b"]


def test_sometimes_missing_key_is_not_required_at_default_threshold(profiled):
    schema = to_schema(profiled([{"a": 1, "b": 2}, {"a": 3}]))
    assert schema["required"] == ["a"]


def test_required_threshold_admits_keys_at_exactly_the_boundary(profiled):
    # 19 of 20 = 0.95: float arithmetic must not push the boundary case out.
    samples = [{"a": 1, "b": 2}] * 19 + [{"a": 1}]
    schema = to_schema(profiled(samples), required_threshold=0.95)
    assert schema["required"] == ["a", "b"]
    strict = to_schema(profiled(samples), required_threshold=1.0)
    assert strict["required"] == ["a"]


def test_null_observations_add_null_to_the_type_union(profiled):
    schema = to_schema(profiled([{"a": "x"}, {"a": None}]))
    assert schema["properties"]["a"]["type"] == ["string", "null"]


def test_field_that_is_only_ever_null_has_type_null(profiled):
    schema = to_schema(profiled([{"a": None}, {"a": None}]))
    assert schema["properties"]["a"]["type"] == "null"


def test_integer_float_mix_widens_to_number_not_a_union(profiled):
    schema = to_schema(profiled([{"n": 1}, {"n": 2.5}]))
    assert schema["properties"]["n"]["type"] == "number"
    pure = to_schema(profiled([{"n": 1}, {"n": 2}]))
    assert pure["properties"]["n"]["type"] == "integer"


def test_conflicting_types_become_an_honest_union(profiled):
    schema = to_schema(profiled([{"x": "a"}, {"x": {"k": 1}}]))
    node = schema["properties"]["x"]
    assert node["type"] == ["string", "object"]
    # The object evidence still produces properties for the object case.
    assert node["properties"]["k"]["type"] == "integer"


def test_format_is_claimed_only_for_pure_or_nullable_string_fields(profiled):
    dated = to_schema(profiled([{"t": "2026-06-01T00:00:00Z"}, {"t": None}]))
    assert dated["properties"]["t"]["format"] == "date-time"
    mixed = to_schema(profiled([{"t": "2026-06-01T00:00:00Z"}, {"t": 5}]))
    assert "format" not in mixed["properties"]["t"]


def test_formats_flag_disables_format_detection(profiled):
    schema = to_schema(profiled([{"t": "2026-06-01"}]), formats=False)
    assert "format" not in schema["properties"]["t"]


def test_enum_includes_null_when_the_field_is_nullable(profiled):
    samples = [{"s": "a"}, {"s": "a"}, {"s": "b"}, {"s": "b"}, {"s": None}]
    schema = to_schema(profiled(samples))
    assert schema["properties"]["s"]["enum"] == ["a", "b", None]
    assert schema["properties"]["s"]["type"] == ["string", "null"]


def test_enum_limit_zero_disables_enums(profiled):
    samples = [{"s": "a"}, {"s": "a"}, {"s": "b"}, {"s": "b"}]
    schema = to_schema(profiled(samples), enum_limit=0)
    assert "enum" not in schema["properties"]["s"]


def test_array_items_recurse_and_always_empty_arrays_accept_anything(profiled):
    schema = to_schema(profiled([{"xs": [1, 2], "ys": []}, {"xs": [3], "ys": []}]))
    assert schema["properties"]["xs"]["items"]["type"] == "integer"
    # No item was ever observed: the honest item schema is {} (anything).
    assert schema["properties"]["ys"]["items"] == {}


def test_root_scalar_samples_produce_a_scalar_schema(profiled):
    schema = to_schema(profiled(["a", "b", "c"]))
    assert schema["type"] == "string"
    assert "properties" not in schema


def test_evidence_blocks_carry_counts_rates_and_ranges(profiled):
    samples = [{"n": 1, "s": "ab"}, {"n": 4, "s": "abcd"}, {"n": None}]
    schema = to_schema(profiled(samples), evidence=True)
    n_block = schema["properties"]["n"]["x-shapecast"]
    assert n_block["seen"] == 3
    assert n_block["types"] == {"integer": 2, "null": 1}
    assert n_block["nullRate"] == pytest.approx(0.3333, abs=1e-4)
    assert n_block["range"] == [1, 4]
    assert n_block["presence"] == {"present": 3, "of": 3, "rate": 1.0}
    s_block = schema["properties"]["s"]["x-shapecast"]
    assert s_block["stringLength"] == [2, 4]
    assert s_block["presence"]["rate"] == pytest.approx(0.6667, abs=1e-4)
    # And off by default: schemas stay clean unless evidence is requested.
    assert "x-shapecast" not in json.dumps(to_schema(profiled(samples)))


def test_invalid_required_threshold_raises_value_error(profiled):
    profiler = profiled([{}])
    with pytest.raises(ValueError):
        to_schema(profiler, required_threshold=0.0)
    with pytest.raises(ValueError):
        to_schema(profiler, required_threshold=1.5)


def test_dump_schema_is_deterministic_and_sorted(profiled):
    profiler = profiled([{"b": 1, "a": "2026-06-01"}])
    first = dump_schema(to_schema(profiler))
    second = dump_schema(to_schema(profiler))
    assert first == second
    assert first.index('"a"') < first.index('"b"')
    # Round-trips as JSON.
    assert json.loads(first)["properties"]["a"]["format"] == "date"
