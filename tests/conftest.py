"""Shared test helpers: build profilers from inline samples in one call."""

from __future__ import annotations

from typing import Any, Iterable

import pytest

from shapecast import Profiler


@pytest.fixture
def profiled():
    """Return a factory: ``profiled(samples) -> Profiler`` (already fed)."""

    def build(samples: Iterable[Any]) -> Profiler:
        profiler = Profiler()
        profiler.add_all(samples)
        return profiler

    return build
