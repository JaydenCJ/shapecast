# shapecast examples

`events.jsonl` is a 12-sample capture of a fictional order-webhook stream. It
is small on purpose, but it packs in every situation shapecast is built to
surface:

| In the data | What shapecast reports |
| --- | --- |
| `event_id`, `created_at` | `format: uuid` / `format: date-time` (every sample matched) |
| `type`, `order.currency` | enums — few distinct values, each seen repeatedly |
| `order.total` mixes `15` and `49.99` | widened `int->number`, emitted as `type: number` |
| `coupon` is often `null` | nullability rate (58.3%), `type: ["string","null"]` |
| `legacy_ref` appears in 2 of 12 events | presence 16.7% — optional, not required |
| `source` is a string in 11 events, an object in 1 | **type conflict**, flagged in the report |

Run against it from the repository root:

```bash
shapecast report examples/events.jsonl
shapecast infer --title "Order events" examples/events.jsonl > schema.json
shapecast report --fail-on-conflict examples/events.jsonl   # exits 1: source conflicts
```

`profile_api.py` shows the library API doing the same thing without the CLI —
profiling payloads in-process, then asking for both the schema and the
evidence report:

```bash
python3 examples/profile_api.py
```
