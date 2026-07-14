# The shapecast evidence model

This document specifies exactly what shapecast counts, and how each JSON
Schema keyword in `shapecast infer` output is justified by those counts.
The rule throughout: **every keyword must be backed by evidence from the
samples; nothing is guessed from a single value.**

## What gets counted

shapecast makes one pass over the samples and maintains one profile node per
JSON path. Paths use a compact JSONPath-like notation:

| Path | Meaning |
| --- | --- |
| `$` | the sample root |
| `$.user.id` | member `id` of member `user` of the root object |
| `$.items[]` | the items of the `items` array (all indices merged) |
| `$["odd key!"]` | members whose names need quoting |

Per node, the profiler records:

| Evidence | Detail |
| --- | --- |
| `seen` | how many times the path held any value, `null` included |
| type counts | occurrences per JSON type: `null`, `boolean`, `integer`, `number`, `string`, `object`, `array` |
| presence | for object members: `seen` vs. how often the parent was an object — a **missing key** and a **null value** are counted separately, because they are different API behaviors |
| numeric range | min/max over all integers and floats |
| string lengths | min/max length |
| array lengths | min/max item count |
| distinct values | scalar values with occurrence counts, up to a cap of 50; past the cap the set is marked incomplete and enum detection is off for that field |
| format matches | per-format match counts (see below) |

## From evidence to keywords

| Keyword | Rule |
| --- | --- |
| `type` | the set of observed types. `null` observations add `"null"` to the union. An integer/float mix **widens** to `number` (every JSON number consumer handles both); it is reported as widening, not a conflict. |
| `required` | keys present in at least `--required-threshold` (default 1.0) of the parent object's occurrences. `required` asserts presence only — a present-but-null key still counts as present. |
| `properties` / `items` | recursion. Arrays merge all items into one profile. An array that was always empty gets `items: {}` — the honest "no evidence" schema. |
| `enum` | claimed only when the set is provably closed-looking: the distinct-value set is complete (never hit the cap), a single scalar type covers **all** non-null observations, no string format matched, at most `--enum-limit` (default 10) distinct values, and **every value was seen at least twice**. Nullable enum fields get `null` appended to the value list so the enum stays valid against the type union. |
| `format` | claimed only when **every** string sample matched the detector. Detectors (most specific wins): `uuid`, `date-time`, `date`, `time`, `ipv4`, `ipv6`, `email`, `uri`. All are strict: RFC 3339 date-times need an offset, UUIDs must be canonically hyphenated, URIs need an explicit `scheme://`. Empty strings match nothing. |
| `x-shapecast` | with `--evidence`, each subschema carries its raw statistics (`seen`, per-type counts, `nullRate`, `presence`, ranges, `distinct`). The `x-` prefix means validators ignore it. |

## What is deliberately *not* emitted

- **No value constraints from samples.** `minimum`, `maxLength`, `minItems`
  and friends would freeze accidents of the sample window into the contract.
  The observed ranges are available as evidence (`--evidence`, `report`),
  where they inform rather than constrain.
- **No `additionalProperties: false`.** Absence of a key in N samples is not
  proof the API never sends it. The presence statistics quantify what was
  seen; closing the object is a decision for a human.

## Conflicts

A **conflict** is a field whose non-null samples disagree on the fundamental
type (`string` vs `object`, `boolean` vs `array`, …) — the classic symptom of
an undocumented API changing shape between code paths. Conflicted fields are
emitted as an honest type union in the schema, flagged in the report, and
turn `shapecast report --fail-on-conflict` into exit code 1 so a CI job can
watch a payload stream for shape drift.
