#!/usr/bin/env bash
# Smoke test for shapecast: infer a schema and an evidence report from the
# bundled example log, check the CLI contract end-to-end (exit codes, JSON
# output, stdin, --version), and verify the conflict gate fires.
# Self-contained: pure stdlib, no network, idempotent (works from a clean tree).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
if [ -x "$ROOT/.venv/bin/python" ]; then
  PYTHON="$ROOT/.venv/bin/python"
fi

# Zero runtime dependencies: running from src/ needs no install.
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/shapecast-smoke.XXXXXX")"
trap 'rm -rf "$WORKDIR"' EXIT

fail() { echo "SMOKE FAIL: $1" >&2; exit 1; }

echo "[smoke] python: $("$PYTHON" --version 2>&1)"

# 1. infer: schema from the example log parses and makes the right claims.
"$PYTHON" -m shapecast infer --title "Order events" "$ROOT/examples/events.jsonl" \
  > "$WORKDIR/schema.json" || fail "infer exited non-zero"
"$PYTHON" - "$WORKDIR/schema.json" <<'PY' || fail "schema assertions failed"
import json, sys
schema = json.load(open(sys.argv[1]))
assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
assert schema["title"] == "Order events"
props = schema["properties"]
assert props["event_id"]["format"] == "uuid"
assert props["created_at"]["format"] == "date-time"
assert props["type"]["enum"] == ["order.cancelled", "order.created", "order.paid"]
assert props["order"]["properties"]["total"]["type"] == "number"  # widened
assert props["coupon"]["type"] == ["string", "null"]
assert "legacy_ref" not in schema["required"]  # present in 2 of 12 samples
print("[smoke] schema claims verified")
PY

# 2. report: evidence table shows presence, nullability, and the conflict.
report_out="$("$PYTHON" -m shapecast report "$ROOT/examples/events.jsonl")"
echo "$report_out" | sed 's/^/[report] /'
echo "$report_out" | grep -q "conflict: string|object" || fail "report missing the source conflict"
echo "$report_out" | grep -q "widened int->number" || fail "report missing the widening note"
echo "$report_out" | grep -Eq '\$\.legacy_ref +string\(2\) +2 +16\.7%' || fail "report missing legacy_ref presence"
echo "$report_out" | grep -q "12 samples, 20 fields, 1 optional, 1 conflict" || fail "report summary wrong"

# 3. report --json round-trips and agrees with the table.
"$PYTHON" -m shapecast report --json "$ROOT/examples/events.jsonl" > "$WORKDIR/report.json" \
  || fail "report --json exited non-zero"
"$PYTHON" - "$WORKDIR/report.json" <<'PY' || fail "JSON report assertions failed"
import json, sys
report = json.load(open(sys.argv[1]))
assert report["samples"] == 12 and report["conflicts"] == 1
coupon = next(f for f in report["fields"] if f["path"] == "$.coupon")
assert coupon["null_rate"] == 0.5833
print("[smoke] JSON report verified")
PY

# 4. The CI gate: --fail-on-conflict exits 1 on the example log.
set +e
"$PYTHON" -m shapecast report --fail-on-conflict "$ROOT/examples/events.jsonl" >/dev/null 2>"$WORKDIR/gate.err"
gate_rc=$?
set -e
[ "$gate_rc" -eq 1 ] || fail "--fail-on-conflict should exit 1, got $gate_rc"
grep -q "1 conflicted field" "$WORKDIR/gate.err" || fail "conflict gate message missing"
echo "[smoke] conflict gate exits 1 as documented"

# 5. stdin piping and --evidence annotations.
piped="$(printf '{"a": 1}\n{"a": null}\n' | "$PYTHON" -m shapecast infer --evidence -)"
echo "$piped" | grep -q '"x-shapecast"' || fail "--evidence produced no annotations"
echo "$piped" | grep -q '"nullRate": 0.5' || fail "evidence nullRate missing"
echo "[smoke] stdin + --evidence verified"

# 6. Bad input fails loudly with the offending line, exit code 2.
printf '{"ok": 1}\n{broken\n' > "$WORKDIR/bad.jsonl"
set +e
"$PYTHON" -m shapecast infer "$WORKDIR/bad.jsonl" >/dev/null 2>"$WORKDIR/bad.err"
bad_rc=$?
set -e
[ "$bad_rc" -eq 2 ] || fail "bad input should exit 2, got $bad_rc"
grep -q "bad.jsonl:2" "$WORKDIR/bad.err" || fail "error did not name file:line"
echo "[smoke] bad input rejected with file:line"

# 7. --version agrees with the package version.
version_out="$("$PYTHON" -m shapecast --version)"
pkg_version="$("$PYTHON" -c 'import shapecast; print(shapecast.__version__)')"
[ "$version_out" = "shapecast $pkg_version" ] \
  || fail "--version mismatch: '$version_out' vs package '$pkg_version'"

echo "SMOKE OK"
