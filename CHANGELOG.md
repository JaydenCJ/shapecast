# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-07-13

### Added

- One-pass statistical profiler building one evidence node per JSON path:
  per-type occurrence counts, presence vs. nullability (missing keys and
  null values counted separately), numeric/string/array ranges, and distinct
  scalar values with occurrence counts up to a cap of 50.
- Draft 2020-12 JSON Schema generation where every keyword is evidence-backed:
  type unions from observed types, integer/float widening to `number`,
  `required` from a configurable presence threshold, recursion through
  objects and merged array items.
- Conservative enum detection: claimed only for a complete value set of one
  scalar type covering all non-null samples, within `--enum-limit`, with
  every value observed at least twice and no string format detected;
  nullable enums include `null` so they stay valid against the type union.
- Strict string format detection (`uuid`, `date-time`, `date`, `time`,
  `ipv4`, `ipv6`, `email`, `uri`), claimed only when every string sample
  matches; RFC 3339 date-times require an offset, UUIDs the canonical
  hyphenated form.
- `--evidence` flag embedding per-field statistics into the schema as
  `x-shapecast` annotations that validators ignore.
- Per-field evidence report (`shapecast report`) as an aligned table or
  `--json`: types with counts, presence %, null %, formats, and notes for
  conflicts, widening, enums, and overflowed value sets.
- Type-conflict detection with a CI gate: `report --fail-on-conflict`
  exits 1 when any field mixes incompatible types.
- Input loading for JSON Lines, single JSON documents, and top-level JSON
  arrays, with auto-detection, `--format` override, multi-file merging,
  `--max-samples`, stdin via `-`, and parse errors that name file and line.
- `shapecast` CLI (`infer`, `report`) with exit codes 0/1/2, plus a
  documented library API (`Profiler`, `to_schema`, `build_report`).
- Runnable example: a 12-sample order-webhook log exercising every reported
  behavior, and a library-API demo script.
- 92 offline deterministic tests and `scripts/smoke.sh` (prints `SMOKE OK`).

### Notes

- The repository ships no CI workflow; verification is local — `pip install -e '.[dev]' && pytest && bash scripts/smoke.sh`.

[0.1.0]: https://github.com/JaydenCJ/shapecast/releases/tag/v0.1.0
