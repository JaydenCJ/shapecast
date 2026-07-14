#!/usr/bin/env python3
"""Library-API example: profile payloads in-process, no CLI involved.

Feeds the bundled ``events.jsonl`` into a :class:`shapecast.Profiler`, then
derives both outputs from the single profile pass:

1. a draft 2020-12 JSON Schema (with ``x-shapecast`` evidence embedded);
2. the per-field evidence report, printed as a table.

Run from the repository root: ``python3 examples/profile_api.py``
(with ``pip install -e .`` done, or ``PYTHONPATH=src``).
"""

from __future__ import annotations

import json
from pathlib import Path

from shapecast import Profiler, build_report, render_text, to_schema

EVENTS = Path(__file__).with_name("events.jsonl")


def main() -> None:
    profiler = Profiler()
    for line in EVENTS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            profiler.add(json.loads(line))

    schema = to_schema(profiler, required_threshold=0.9, evidence=True)
    coupon = schema["properties"]["coupon"]
    print("coupon subschema, with the evidence that produced it:")
    print(json.dumps(coupon, indent=2, sort_keys=True))
    print()

    report = build_report(profiler)
    print(render_text(report))

    conflicted = [f["path"] for f in report["fields"] if f["conflict"]]
    print(f"\nconflicted fields: {', '.join(conflicted) or 'none'}")


if __name__ == "__main__":
    main()
