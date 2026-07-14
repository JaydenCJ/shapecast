# Contributing to shapecast

Thanks for your interest in contributing. Issues, discussions, and pull
requests are all welcome.

## Development setup

Requirements: Python 3.9 or newer. The package itself has zero runtime
dependencies; pytest is the only dev dependency.

```bash
git clone https://github.com/JaydenCJ/shapecast
cd shapecast
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Running the checks

```bash
pytest                 # 92 offline, deterministic tests
bash scripts/smoke.sh  # end-to-end CLI smoke; must print SMOKE OK
```

Both must pass before a pull request is reviewed. `scripts/smoke.sh` runs the
real CLI against the bundled example log — infer, report, the conflict gate,
stdin, and error paths — and prints `SMOKE OK` on success. The whole suite
runs offline in seconds and needs no services or keys.

## Before you open a pull request

1. Format touched files consistently with the surrounding code (PEP 8,
   4-space indents; formatting is enforced in review).
2. Run `pytest` — must pass.
3. Run `bash scripts/smoke.sh` — must print `SMOKE OK`.
4. Add tests for behavior changes; keep logic in the pure modules
   (`profile`, `schema`, `report`, `formats`) and out of `cli.py`.

## Ground rules

- **No new runtime dependencies.** The package is standard-library only;
  that is a feature. Test-only dependencies belong in the `dev` extra.
- **Every emitted schema keyword needs evidence.** New inference rules must
  be justified by sample statistics and documented in
  `docs/evidence-model.md` in the same pull request.
- **No network calls, ever.** shapecast reads local files and stdin; it
  sends nothing anywhere. No telemetry.
- **Every public API needs an English docstring and a test.** Code comments
  are written in English.
- **Keep the three READMEs aligned.** `README.md`, `README.zh.md`, and
  `README.ja.md` share the same structure; update all three when you change
  one (English is the authoritative version).

## Reporting bugs

Please include `shapecast --version` output, a minimal sample file (a few
JSONL lines that reproduce it — redact real values, keep the shape), the
exact command, and what you expected the schema or report to say.

## Security

Please do not open public issues for security problems; use GitHub's private
vulnerability reporting on the repository instead.
