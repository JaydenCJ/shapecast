"""The ``shapecast`` command-line interface.

Two subcommands over the same one-pass profile:

- ``shapecast infer``  — emit a draft 2020-12 JSON Schema to stdout;
- ``shapecast report`` — emit the per-field evidence table (or ``--json``).

Exit codes: 0 on success, 1 when ``report --fail-on-conflict`` found type
conflicts, 2 for unusable input (missing file, bad JSON, bad flags). All
reading is local files or stdin; shapecast never opens a network connection.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional, Sequence

from . import __version__
from .errors import ShapecastError
from .loader import FORMATS, load_samples
from .profile import Profiler
from .report import build_report, render_text
from .schema import dump_schema, to_schema

#: Exit code for input/usage errors, matching argparse's own convention.
EXIT_USAGE = 2
#: Exit code when --fail-on-conflict finds at least one conflicted field.
EXIT_CONFLICT = 1


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "paths",
        nargs="*",
        default=["-"],
        metavar="FILE",
        help="input files (.json / .jsonl / .ndjson); '-' or none reads stdin",
    )
    parser.add_argument(
        "--format",
        choices=FORMATS,
        default="auto",
        help="how to split input into samples (default: auto-detect)",
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=0,
        metavar="N",
        help="stop after N samples across all inputs (0 = no limit)",
    )
    parser.add_argument(
        "--enum-limit",
        type=int,
        default=10,
        metavar="N",
        help="max distinct values for enum detection; 0 disables (default: 10)",
    )
    parser.add_argument(
        "--no-formats",
        action="store_true",
        help="disable string format detection (uuid, date-time, email, ...)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shapecast",
        description=(
            "Infer JSON Schema from example payloads, with per-field type and "
            "presence statistics."
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"shapecast {__version__}"
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    infer = subparsers.add_parser(
        "infer",
        help="emit a draft 2020-12 JSON Schema inferred from the samples",
        description="Infer a JSON Schema from example payloads and print it to stdout.",
    )
    _add_common_arguments(infer)
    infer.add_argument(
        "--required-threshold",
        type=float,
        default=1.0,
        metavar="RATE",
        help="minimum presence rate for a key to be required (default: 1.0)",
    )
    infer.add_argument("--title", help="set the schema's title keyword")
    infer.add_argument(
        "--evidence",
        action="store_true",
        help="embed per-field statistics as x-shapecast annotations",
    )
    infer.add_argument(
        "--indent",
        type=int,
        default=2,
        metavar="N",
        help="JSON indentation for the emitted schema (default: 2)",
    )

    report = subparsers.add_parser(
        "report",
        help="print the per-field evidence table (counts, presence, conflicts)",
        description="Report per-field type, presence and nullability statistics.",
    )
    _add_common_arguments(report)
    report.add_argument(
        "--json", action="store_true", help="emit the report as JSON instead of a table"
    )
    report.add_argument(
        "--fail-on-conflict",
        action="store_true",
        help="exit 1 if any field mixes incompatible types (CI gate)",
    )
    return parser


def _profile_inputs(args: argparse.Namespace) -> Profiler:
    samples = load_samples(
        args.paths, fmt=args.format, max_samples=args.max_samples or None
    )
    if not samples:
        raise ShapecastError("no samples found in the input")
    profiler = Profiler()
    profiler.add_all(samples)
    return profiler


def _run_infer(args: argparse.Namespace) -> int:
    profiler = _profile_inputs(args)
    schema = to_schema(
        profiler,
        required_threshold=args.required_threshold,
        enum_limit=args.enum_limit,
        formats=not args.no_formats,
        evidence=args.evidence,
        title=args.title,
    )
    print(dump_schema(schema, indent=args.indent))
    return 0


def _run_report(args: argparse.Namespace) -> int:
    profiler = _profile_inputs(args)
    report = build_report(
        profiler, enum_limit=args.enum_limit, formats=not args.no_formats
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print(render_text(report))
    if args.fail_on_conflict and report["conflicts"]:
        print(
            f"shapecast: {report['conflicts']} conflicted "
            + ("field" if report["conflicts"] == 1 else "fields")
            + " (--fail-on-conflict)",
            file=sys.stderr,
        )
        return EXIT_CONFLICT
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return EXIT_USAGE
    try:
        if args.command == "infer":
            if not 0.0 < args.required_threshold <= 1.0:
                parser.error("--required-threshold must be in (0, 1]")
            return _run_infer(args)
        return _run_report(args)
    except ShapecastError as exc:
        print(f"shapecast: error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except BrokenPipeError:
        # Piping into `head` is normal usage, not an error.
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
