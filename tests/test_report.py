"""Evidence report: per-field rows, notes, and the rendered table."""

from __future__ import annotations

import json

import pytest

from shapecast import build_report, render_text


def test_report_summary_counts_fields_optionals_and_conflicts(profiled):
    profiler = profiled(
        [{"a": 1, "b": "x"}, {"a": 2}, {"a": "s"}]  # b optional, a conflicted
    )
    report = build_report(profiler)
    assert report["samples"] == 3
    assert report["field_count"] == 3  # $, $.a, $.b
    assert report["optional_fields"] == 1
    assert report["conflicts"] == 1


def test_presence_is_none_for_root_and_array_items(profiled):
    report = build_report(profiled([{"xs": [1]}]))
    by_path = {row["path"]: row for row in report["fields"]}
    assert by_path["$"]["presence"] is None
    assert by_path["$.xs[]"]["presence"] is None
    assert by_path["$.xs"]["presence"] == {"present": 1, "of": 1, "rate": 1.0}


def test_presence_rate_reflects_missing_keys_not_null_values(profiled):
    report = build_report(profiled([{"a": None}, {"a": 1}, {}, {"a": 2}]))
    row = next(r for r in report["fields"] if r["path"] == "$.a")
    assert row["presence"] == {"present": 3, "of": 4, "rate": 0.75}
    assert row["null_count"] == 1
    assert row["null_rate"] == pytest.approx(0.3333, abs=1e-4)


def test_conflict_note_names_the_disagreeing_types(profiled):
    report = build_report(profiled([{"x": "a"}, {"x": {}}]))
    row = next(r for r in report["fields"] if r["path"] == "$.x")
    assert row["conflict"] is True
    assert "conflict: string|object" in row["notes"]


def test_widened_note_appears_for_int_float_mixes(profiled):
    report = build_report(profiled([{"n": 1}, {"n": 2.5}]))
    row = next(r for r in report["fields"] if r["path"] == "$.n")
    assert "widened int->number" in row["notes"]
    assert row["conflict"] is False


def test_enum_note_and_values_are_included(profiled):
    samples = [{"s": "on"}, {"s": "off"}, {"s": "on"}, {"s": "off"}]
    report = build_report(profiled(samples))
    row = next(r for r in report["fields"] if r["path"] == "$.s")
    assert "enum(2)" in row["notes"]
    assert row["enum"] == ["off", "on"]


def test_overflow_note_replaces_enum_when_the_value_cap_is_hit():
    from shapecast import Profiler

    profiler = Profiler(value_cap=4)
    profiler.add_all([{"s": f"v{i}"} for i in range(6)])
    report = build_report(profiler)
    row = next(r for r in report["fields"] if r["path"] == "$.s")
    assert ">4 distinct" in row["notes"]
    assert "enum" not in row


def test_format_column_carries_the_dominant_format(profiled):
    report = build_report(profiled([{"id": "5f2c1a8e-8d1b-4d6a-9c3e-2b7f0a1d4e90"}]))
    row = next(r for r in report["fields"] if r["path"] == "$.id")
    assert row["format"] == "uuid"


def test_render_text_aligns_columns_and_prints_a_summary(profiled):
    report = build_report(profiled([{"alpha": 1, "b": None}, {"alpha": 2}]))
    text = render_text(report)
    lines = text.splitlines()
    header = lines[0]
    assert header.startswith("FIELD")
    # Every data row's TYPES column starts where the header says it does.
    types_col = header.index("TYPES")
    assert lines[1][types_col:].startswith("object(")
    assert "2 samples, 3 fields, 1 optional, 0 conflicts" in text
    # Singular form when exactly one field conflicts.
    conflicted = render_text(build_report(profiled([{"x": "a"}, {"x": 1}])))
    assert conflicted.rstrip().endswith("1 conflict")


def test_summary_uses_singular_nouns_for_counts_of_one(profiled):
    # "1 samples" in a summary line is the kind of sloppiness the whole
    # tool exists to catch in other people's output; hold ourselves to it.
    text = render_text(build_report(profiled([42])))
    assert text.rstrip().endswith("1 sample, 1 field, 0 optional, 0 conflicts")


def test_formats_false_leaves_the_format_column_empty(profiled):
    profiler = profiled([{"ip": "203.0.113.7"}, {"ip": "203.0.113.9"}])
    report = build_report(profiler, formats=False)
    row = next(r for r in report["fields"] if r["path"] == "$.ip")
    assert row["format"] is None


def test_report_is_json_serializable(profiled):
    report = build_report(profiled([{"a": [1, 2.5], "b": {"c": None}}]))
    encoded = json.dumps(report, sort_keys=True)
    assert json.loads(encoded)["samples"] == 1

