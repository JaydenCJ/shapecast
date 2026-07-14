"""Exception types for shapecast.

All shapecast-raised errors derive from :class:`ShapecastError`, so callers
embedding the library can catch one type. The CLI maps :class:`InputError`
to exit code 2 (bad input) and everything else to a non-zero failure.
"""

from __future__ import annotations


class ShapecastError(Exception):
    """Base class for every error shapecast raises deliberately."""


class InputError(ShapecastError):
    """A payload source could not be read or parsed.

    Carries enough context (source name, line number where applicable) to
    point the user at the exact offending sample, because the whole point of
    the tool is to digest large, messy log files.
    """

    def __init__(self, source: str, message: str, line: "int | None" = None):
        self.source = source
        self.line = line
        self.message = message
        location = source if line is None else f"{source}:{line}"
        super().__init__(f"{location}: {message}")
