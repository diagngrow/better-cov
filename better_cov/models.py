"""Language-independent coverage models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FunctionCoverage:
    """Coverage of an individual function or method."""

    file: str
    function: str
    line_rate: float
    lines_covered: int
    lines_total: int
