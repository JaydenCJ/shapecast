"""The bundled example log must keep demonstrating every advertised behavior.

These tests pin the claims made in ``examples/README.md`` and the README
quickstart to the actual file, so documentation and data cannot drift apart.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shapecast import Profiler, build_report, to_schema
from shapecast.cli import main

EVENTS = Path(__file__).resolve().parent.parent / "examples" / "events.jsonl"


@pytest.fixture(scope="module")
def events_profiler():
    profiler = Profiler()
    for line in EVENTS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            profiler.add(json.loads(line))
    return profiler


def test_example_log_has_twelve_samples(events_profiler):
    assert events_profiler.sample_count == 12


def test_example_log_demonstrates_formats_enums_and_widening(events_profiler):
    schema = to_schema(events_profiler)
    props = schema["properties"]
    assert props["event_id"]["format"] == "uuid"
    assert props["created_at"]["format"] == "date-time"
    assert props["type"]["enum"] == ["order.cancelled", "order.created", "order.paid"]
    assert props["order"]["properties"]["total"]["type"] == "number"  # widened
    assert props["coupon"]["type"] == ["string", "null"]


def test_example_log_demonstrates_the_source_conflict(events_profiler):
    report = build_report(events_profiler)
    row = next(r for r in report["fields"] if r["path"] == "$.source")
    assert row["conflict"] is True
    assert report["conflicts"] == 1


def test_example_log_demonstrates_optional_and_nullable_separately(events_profiler):
    report = build_report(events_profiler)
    legacy = next(r for r in report["fields"] if r["path"] == "$.legacy_ref")
    coupon = next(r for r in report["fields"] if r["path"] == "$.coupon")
    assert legacy["presence"]["rate"] < 0.2 and legacy["null_count"] == 0
    assert coupon["presence"]["rate"] == 1.0 and coupon["null_rate"] > 0.5


def test_fail_on_conflict_gate_fires_on_the_example_log(capsys):
    assert main(["report", "--fail-on-conflict", str(EVENTS)]) == 1
    capsys.readouterr()
