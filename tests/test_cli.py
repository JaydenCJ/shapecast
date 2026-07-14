"""CLI behavior end-to-end through ``main(argv)``: output, flags, exit codes."""

from __future__ import annotations

import io
import json

import pytest

from shapecast import __version__
from shapecast.cli import main

EVENTS = (
    '{"id": 1, "kind": "a", "when": "2026-06-01T00:00:00Z"}\n'
    '{"id": 2, "kind": "b", "when": "2026-06-02T00:00:00Z"}\n'
    '{"id": 3, "kind": "a", "note": "rare"}\n'
)

CONFLICTED = '{"x": "s"}\n{"x": 5}\n'


@pytest.fixture
def events_file(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text(EVENTS, encoding="utf-8")
    return str(path)


def test_version_flag_reports_the_package_version(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert capsys.readouterr().out.strip() == f"shapecast {__version__}"


def test_no_command_prints_help_and_exits_2(capsys):
    assert main([]) == 2
    assert "infer" in capsys.readouterr().out


def test_infer_emits_a_parseable_schema(events_file, capsys):
    assert main(["infer", events_file]) == 0
    schema = json.loads(capsys.readouterr().out)
    assert schema["$schema"].endswith("2020-12/schema")
    assert schema["properties"]["id"]["type"] == "integer"
    assert schema["required"] == ["id", "kind"]  # 'when'/'note' are not universal


def test_infer_title_and_evidence_flags(events_file, capsys):
    assert main(["infer", "--title", "Events", "--evidence", events_file]) == 0
    schema = json.loads(capsys.readouterr().out)
    assert schema["title"] == "Events"
    assert schema["properties"]["id"]["x-shapecast"]["seen"] == 3


def test_infer_required_threshold_admits_frequent_keys(events_file, capsys):
    assert main(["infer", "--required-threshold", "0.6", events_file]) == 0
    schema = json.loads(capsys.readouterr().out)
    assert "when" in schema["required"]  # present in 2 of 3
    assert "note" not in schema["required"]  # present in 1 of 3


def test_infer_rejects_out_of_range_threshold(events_file, capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["infer", "--required-threshold", "0", events_file])
    assert excinfo.value.code == 2
    assert "required-threshold" in capsys.readouterr().err


def test_infer_no_formats_drops_format_keywords(events_file, capsys):
    assert main(["infer", "--no-formats", events_file]) == 0
    assert '"format"' not in capsys.readouterr().out


def test_report_no_formats_clears_the_format_column(events_file, capsys):
    assert main(["report", "--no-formats", events_file]) == 0
    assert "date-time" not in capsys.readouterr().out


def test_report_prints_table_with_header_and_summary(events_file, capsys):
    assert main(["report", events_file]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith("FIELD")
    assert "$.when" in out
    assert "date-time" in out
    assert "3 samples" in out


def test_report_json_is_machine_readable(events_file, capsys):
    assert main(["report", "--json", events_file]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["samples"] == 3
    paths = [row["path"] for row in report["fields"]]
    assert "$.kind" in paths


def test_fail_on_conflict_exits_1_only_when_conflicts_exist(tmp_path, capsys):
    clean = tmp_path / "clean.jsonl"
    clean.write_text('{"a": 1}\n', encoding="utf-8")
    assert main(["report", "--fail-on-conflict", str(clean)]) == 0

    bad = tmp_path / "bad.jsonl"
    bad.write_text(CONFLICTED, encoding="utf-8")
    assert main(["report", "--fail-on-conflict", str(bad)]) == 1
    assert "1 conflicted field" in capsys.readouterr().err


def test_missing_file_and_empty_input_exit_2_with_clear_messages(tmp_path, capsys):
    assert main(["infer", "definitely-not-here.jsonl"]) == 2
    assert "no such file" in capsys.readouterr().err
    empty = tmp_path / "empty.json"
    empty.write_text("", encoding="utf-8")
    assert main(["infer", str(empty)]) == 2
    assert "no samples" in capsys.readouterr().err


def test_invalid_json_reports_file_and_line(tmp_path, capsys):
    path = tmp_path / "broken.jsonl"
    path.write_text('{"ok": 1}\nnot json\n', encoding="utf-8")
    assert main(["report", str(path)]) == 2
    err = capsys.readouterr().err
    assert "broken.jsonl:2" in err


def test_stdin_is_the_default_input(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO('{"a": 1}\n{"a": 2}\n'))
    assert main(["infer"]) == 0
    schema = json.loads(capsys.readouterr().out)
    assert schema["properties"]["a"]["type"] == "integer"


def test_max_samples_caps_the_evidence(events_file, capsys):
    assert main(["infer", "--evidence", "--max-samples", "2", events_file]) == 0
    schema = json.loads(capsys.readouterr().out)
    assert schema["x-shapecast"]["seen"] == 2


def test_enum_limit_flag_reaches_the_report(tmp_path, capsys):
    path = tmp_path / "enum.jsonl"
    path.write_text('{"s": "a"}\n{"s": "a"}\n{"s": "b"}\n{"s": "b"}\n', encoding="utf-8")
    assert main(["report", str(path)]) == 0
    assert "enum(2)" in capsys.readouterr().out
    assert main(["report", "--enum-limit", "1", str(path)]) == 0
    assert "enum(" not in capsys.readouterr().out


def test_multiple_input_files_are_merged(tmp_path, capsys):
    one = tmp_path / "one.jsonl"
    two = tmp_path / "two.jsonl"
    one.write_text('{"a": 1}\n', encoding="utf-8")
    two.write_text('{"a": null}\n', encoding="utf-8")
    assert main(["report", "--json", str(one), str(two)]) == 0
    report = json.loads(capsys.readouterr().out)
    row = next(r for r in report["fields"] if r["path"] == "$.a")
    assert row["types"] == {"integer": 1, "null": 1}
