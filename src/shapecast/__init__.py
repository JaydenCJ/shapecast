"""shapecast — infer JSON Schema from example payloads, with evidence.

Public API:

- :class:`Profiler` / :class:`FieldProfile` — one-pass statistical profiling
  of decoded JSON samples;
- :func:`to_schema` / :func:`dump_schema` — draft 2020-12 schema generation;
- :func:`build_report` / :func:`render_text` — per-field evidence reporting;
- :func:`load_samples` — file/stdin loading for JSON, JSON Lines and arrays;
- :class:`ShapecastError` / :class:`InputError` — the error hierarchy.

Typical embedding:

    from shapecast import Profiler, to_schema

    profiler = Profiler()
    for payload in payloads:
        profiler.add(payload)
    schema = to_schema(profiler, required_threshold=0.95)
"""

from .errors import InputError, ShapecastError
from .loader import load_samples, load_source
from .profile import FieldProfile, Profiler, json_type_of
from .report import build_report, render_text
from .schema import SCHEMA_DIALECT, dump_schema, to_schema

__version__ = "0.1.0"

__all__ = [
    "FieldProfile",
    "InputError",
    "Profiler",
    "SCHEMA_DIALECT",
    "ShapecastError",
    "__version__",
    "build_report",
    "dump_schema",
    "json_type_of",
    "load_samples",
    "load_source",
    "render_text",
    "to_schema",
]
