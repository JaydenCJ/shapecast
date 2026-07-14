"""Loader behavior: JSONL, single JSON, top-level arrays, and auto-detection."""

from __future__ import annotations

import pytest

from shapecast import InputError, load_samples, load_source


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_jsonl_yields_one_sample_per_nonempty_line(tmp_path):
    path = write(tmp_path, "a.jsonl", '{"a": 1}\n\n  \n{"a": 2}\n')
    assert load_source(path) == [{"a": 1}, {"a": 2}]


def test_jsonl_parse_error_reports_the_line_number(tmp_path):
    path = write(tmp_path, "a.jsonl", '{"a": 1}\n{oops}\n')
    with pytest.raises(InputError) as excinfo:
        load_source(path)
    assert excinfo.value.line == 2
    assert "a.jsonl:2" in str(excinfo.value)


def test_single_json_object_is_one_sample(tmp_path):
    path = write(tmp_path, "one.json", '{"a": 1}')
    assert load_source(path) == [{"a": 1}]


def test_auto_treats_top_level_json_array_as_many_samples(tmp_path):
    path = write(tmp_path, "batch.json", '[{"a": 1}, {"a": 2}]')
    assert load_source(path) == [{"a": 1}, {"a": 2}]


def test_format_json_pins_an_array_as_a_single_sample(tmp_path):
    # When the payload itself is an array, --format json stops auto-splitting.
    path = write(tmp_path, "one.json", "[1, 2, 3]")
    assert load_source(path, fmt="json") == [[1, 2, 3]]


def test_format_array_rejects_non_array_documents(tmp_path):
    path = write(tmp_path, "one.json", '{"a": 1}')
    with pytest.raises(InputError, match="top-level JSON array"):
        load_source(path, fmt="array")


def test_ndjson_extension_forces_line_parsing(tmp_path):
    # A one-line .ndjson file containing an array is one sample (the array),
    # not N samples — extension wins over shape in auto mode.
    path = write(tmp_path, "a.ndjson", "[1, 2]\n")
    assert load_source(path) == [[1, 2]]


def test_auto_falls_back_to_jsonl_for_multi_document_streams(tmp_path):
    # Logs frequently end up in .log/.txt files; auto must still read them.
    path = write(tmp_path, "capture.log", '{"a": 1}\n{"a": 2}\n')
    assert load_source(path) == [{"a": 1}, {"a": 2}]


def test_missing_file_raises_input_error_not_oserror(tmp_path):
    with pytest.raises(InputError, match="no such file"):
        load_source(str(tmp_path / "nope.jsonl"))


def test_non_utf8_and_unknown_format_raise_input_errors(tmp_path):
    binary = tmp_path / "bin.json"
    binary.write_bytes(b"\xff\xfe{}")
    with pytest.raises(InputError, match="not valid UTF-8"):
        load_source(str(binary))
    path = write(tmp_path, "a.jsonl", "{}")
    with pytest.raises(InputError, match="unknown format"):
        load_source(path, fmt="yaml")


def test_empty_input_yields_no_samples(tmp_path):
    path = write(tmp_path, "empty.json", "   \n")
    assert load_source(path) == []


def test_load_samples_concatenates_files_in_order(tmp_path):
    first = write(tmp_path, "one.jsonl", "1\n2\n")
    second = write(tmp_path, "two.jsonl", "3\n")
    assert load_samples([first, second]) == [1, 2, 3]


def test_load_samples_max_samples_caps_across_files(tmp_path):
    first = write(tmp_path, "one.jsonl", "1\n2\n3\n")
    second = write(tmp_path, "two.jsonl", "4\n")
    assert load_samples([first, second], max_samples=2) == [1, 2]
