"""Payload loading: files, stdin, JSON, JSON Lines, and top-level arrays.

Real-world "many samples" arrive in three shapes, and shapecast reads all of
them without flags in the common case:

- **jsonl** — one JSON document per non-empty line (``.jsonl``/``.ndjson``,
  and what most structured-log pipelines emit);
- **array** — a single ``.json`` file whose top level is an array; each
  element is treated as one sample (a captured list of API responses);
- **json** — a single JSON document treated as exactly one sample.

``detect`` picks between them from the extension and the parsed shape; the
``--format`` flag pins a specific reading when the guess would be wrong (for
example, one payload that happens to *be* an array). Parse failures raise
:class:`~shapecast.errors.InputError` with the source name and, for JSONL,
the 1-based line number of the bad line.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Iterable, Iterator, List, Optional

from .errors import InputError

#: Accepted values for the ``fmt`` argument / ``--format`` flag.
FORMATS = ("auto", "jsonl", "json", "array")

_JSONL_SUFFIXES = (".jsonl", ".ndjson")


def iter_jsonl(text: str, source: str) -> Iterator[Any]:
    """Yield one decoded document per non-empty line of *text*."""
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            yield json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise InputError(source, f"invalid JSON: {exc.msg}", line=lineno) from exc


def _parse_document(text: str, source: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise InputError(source, f"invalid JSON: {exc.msg} (char {exc.pos})") from exc


def _samples_from_text(text: str, source: str, fmt: str, is_jsonl_name: bool) -> List[Any]:
    if fmt == "jsonl":
        return list(iter_jsonl(text, source))
    if fmt == "json":
        return [_parse_document(text, source)]
    if fmt == "array":
        document = _parse_document(text, source)
        if not isinstance(document, list):
            raise InputError(source, "--format array requires a top-level JSON array")
        return document

    # fmt == "auto": extension first, then shape.
    if is_jsonl_name:
        return list(iter_jsonl(text, source))
    if not text.strip():
        return []
    try:
        document = json.loads(text)
    except json.JSONDecodeError:
        # Not one JSON document — fall back to line-delimited parsing so a
        # `.log`/stdin stream of JSONL still loads. Errors then carry the
        # precise line number instead of a whole-document position.
        return list(iter_jsonl(text, source))
    if isinstance(document, list):
        return list(document)
    return [document]


def load_source(path: str, fmt: str = "auto") -> List[Any]:
    """Load samples from one file path (or ``-`` for stdin).

    Returns the decoded samples in input order. *fmt* is one of
    :data:`FORMATS`; ``auto`` resolves ``.jsonl``/``.ndjson`` extensions to
    JSONL, parses everything else as JSON, and treats a top-level array as a
    list of samples.
    """
    if fmt not in FORMATS:
        raise InputError(path, f"unknown format {fmt!r} (expected one of {', '.join(FORMATS)})")
    if path == "-":
        text = sys.stdin.read()
        name = "<stdin>"
        is_jsonl_name = False
    else:
        file_path = Path(path)
        try:
            text = file_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise InputError(path, "no such file") from None
        except IsADirectoryError:
            raise InputError(path, "is a directory") from None
        except UnicodeDecodeError as exc:
            raise InputError(path, f"not valid UTF-8: {exc.reason}") from exc
        name = path
        is_jsonl_name = file_path.suffix.lower() in _JSONL_SUFFIXES
    return _samples_from_text(text, name, fmt, is_jsonl_name)


def load_samples(
    paths: Iterable[str],
    fmt: str = "auto",
    max_samples: Optional[int] = None,
) -> List[Any]:
    """Load and concatenate samples from every path, in order.

    ``max_samples`` caps the total across all sources (useful when pointing
    shapecast at a very large log and a few thousand samples are plenty of
    evidence). A cap of ``None`` or ``0`` means unlimited.
    """
    samples: List[Any] = []
    for path in paths:
        for sample in load_source(path, fmt):
            samples.append(sample)
            if max_samples and len(samples) >= max_samples:
                return samples
    return samples
