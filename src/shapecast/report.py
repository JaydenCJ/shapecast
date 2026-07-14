"""Evidence reporting: the per-field statistics table behind the schema.

Where :mod:`shapecast.schema` answers "what is the shape?", this module
answers "how sure are we, and where does it wobble?". ``build_report``
flattens the profile tree into one row per JSON path with:

- observed types and their counts;
- presence rate in the parent object (absent keys vs. null values);
- nullability rate;
- the detected format, distinct-value counts, enum candidates;
- notes for the things that bite: type conflicts, int→number widening,
  value sets that overflowed the tracking cap.

``render_text`` draws the table for humans; the same report dict serializes
to JSON (``shapecast report --json``) for machines. Conflict rows are the
CI hook: ``--fail-on-conflict`` turns any of them into a non-zero exit.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .profile import FieldProfile, JSON_TYPES, Profiler

#: Column headers for the text table, in order.
COLUMNS = ("FIELD", "TYPES", "SEEN", "PRESENT", "NULL%", "FORMAT", "NOTES")


def _plural(count: int, noun: str) -> str:
    """``1 sample`` / ``2 samples`` — count plus a correctly numbered noun."""
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _percent(part: int, whole: int) -> str:
    """Human percentage: exact 0/100 stay bare, everything else 1 decimal."""
    if whole <= 0:
        return "-"
    if part == 0:
        return "0%"
    if part == whole:
        return "100%"
    return f"{100.0 * part / whole:.1f}%"


def _types_label(type_counts: Dict[str, int]) -> str:
    parts = [
        f"{name}({type_counts[name]})"
        for name in JSON_TYPES
        if name != "null" and name in type_counts
    ]
    return "|".join(parts) if parts else "null"


def _notes(node: FieldProfile, enum_limit: int) -> List[str]:
    notes: List[str] = []
    if node.has_conflict:
        notes.append("conflict: " + "|".join(node.non_null_types))
    elif node.is_widened:
        notes.append("widened int->number")
    enum_values = node.enum_values(enum_limit)
    if enum_values is not None:
        notes.append(f"enum({len(enum_values)})")
    elif node.values_overflowed:
        notes.append(f">{node.value_cap} distinct")
    return notes


def build_report(
    profiler: Profiler, enum_limit: int = 10, formats: bool = True
) -> Dict[str, Any]:
    """Flatten the profile into a JSON-serializable evidence report.

    ``formats=False`` leaves every row's ``format`` empty (the CLI's
    ``--no-formats``), mirroring what :func:`~shapecast.schema.to_schema`
    does with the ``format`` keyword.
    """
    fields: List[Dict[str, Any]] = []
    conflicts = 0
    optional = 0
    for node, parent in profiler.root.walk():
        parent_objects = parent.object_count if parent is not None else 0
        is_member = parent is not None and not node.path.endswith("[]")
        presence: Optional[Dict[str, Any]] = None
        if is_member and parent_objects:
            presence = {
                "present": node.count,
                "of": parent_objects,
                "rate": round(node.count / parent_objects, 4),
            }
            if node.count < parent_objects:
                optional += 1
        if node.has_conflict:
            conflicts += 1
        row: Dict[str, Any] = {
            "path": node.path,
            "types": dict(sorted(node.type_counts.items())),
            "seen": node.count,
            "presence": presence,
            "null_count": node.null_count,
            "null_rate": round(node.null_count / node.count, 4) if node.count else 0.0,
            "format": node.dominant_format() if formats else None,
            "distinct": node.distinct_count,
            "conflict": node.has_conflict,
            "notes": _notes(node, enum_limit),
        }
        enum_values = node.enum_values(enum_limit)
        if enum_values is not None:
            row["enum"] = enum_values
        fields.append(row)
    return {
        "generator": "shapecast",
        "samples": profiler.sample_count,
        "field_count": len(fields),
        "conflicts": conflicts,
        "optional_fields": optional,
        "fields": fields,
    }


def render_text(report: Dict[str, Any]) -> str:
    """Render the report as an aligned, pipeless table plus a summary line."""
    rows: List[List[str]] = [list(COLUMNS)]
    for field in report["fields"]:
        types_label = _types_label(field["types"])
        presence = field["presence"]
        present_label = (
            _percent(presence["present"], presence["of"]) if presence else "-"
        )
        null_label = _percent(field["null_count"], field["seen"])
        rows.append(
            [
                field["path"],
                types_label,
                str(field["seen"]),
                present_label,
                null_label,
                field["format"] or "-",
                ", ".join(field["notes"]) or "-",
            ]
        )
    widths = [max(len(row[i]) for row in rows) for i in range(len(COLUMNS))]
    lines = [
        "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip()
        for row in rows
    ]
    summary = (
        f"{_plural(report['samples'], 'sample')}, "
        f"{_plural(report['field_count'], 'field')}, "
        f"{report['optional_fields']} optional, "
        f"{_plural(report['conflicts'], 'conflict')}"
    )
    return "\n".join(lines) + "\n\n" + summary
