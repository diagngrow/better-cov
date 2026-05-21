"""Computes the coverage score weighted by function importance.

Formula:
    weighted_score = Σ(line_rate_i × importance_i) / Σ(importance_i)

A function's importance is the weighted sum of scores from each
indicator. Functions not referenced by any indicator receive
a minimum importance (``min_importance``) to avoid being ignored.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from better_cov.indicators.base import ImportanceIndicator
from better_cov.parsers.cobertura import FunctionCoverage


@dataclass
class IndicatorConfig:
    """Binds an indicator with its relative weight in the calculation."""

    indicator: ImportanceIndicator
    weight: float = 1.0
    """Weight of this indicator in the composite importance score."""


@dataclass
class FunctionScore:
    """Detailed score for an individual function."""

    file: str
    function: str
    line_rate: float
    lines_covered: int
    lines_total: int
    importance: float
    """Normalized importance score [min_importance, 1.0]."""
    weighted_contribution: float
    """Weighted contribution of this function to the global score."""
    indicator_scores: dict[str, float] = field(default_factory=dict)
    """Raw scores per indicator (for debugging/detailed reporting)."""


@dataclass
class WeightedCoverageResult:
    """Complete result of the weighted coverage calculation."""

    global_score: float
    """Global weighted score between 0.0 and 1.0."""

    global_score_pct: float
    """Global score as percentage (0 to 100)."""

    raw_coverage: float
    """Unweighted raw coverage (for comparison)."""

    total_functions: int
    functions: list[FunctionScore]

    source_dirs: list[str]
    indicators: list[str]
    """Names of indicators used."""


def compute_weighted_coverage(
    functions: list[FunctionCoverage],
    indicator_configs: list[IndicatorConfig],
    source_dirs: list[str],
    min_importance: float = 0.1,
) -> WeightedCoverageResult:
    """Computes the weighted coverage score.

    Args:
        functions: List of per-function coverages (from parse_coverage_xml).
        indicator_configs: Importance indicators with their weights.
        source_dirs: Source directories passed to indicators.
        min_importance: Minimum importance for functions not referenced
            by any indicator (prevents them from being completely ignored).

    Returns:
        WeightedCoverageResult with global score and per-function details.
    """
    if not functions:
        return WeightedCoverageResult(
            global_score=0.0,
            global_score_pct=0.0,
            raw_coverage=0.0,
            total_functions=0,
            functions=[],
            source_dirs=source_dirs,
            indicators=[ic.indicator.name for ic in indicator_configs],
        )

    indicator_scores_map: dict[str, dict[str, float]] = {}
    for ic in indicator_configs:
        indicator_scores_map[ic.indicator.name] = ic.indicator.compute(source_dirs)

    total_weight = sum(ic.weight for ic in indicator_configs) or 1.0

    function_scores: list[FunctionScore] = []
    for fc in functions:
        raw_scores: dict[str, float] = {}
        composite_importance = 0.0

        for ic in indicator_configs:
            scores = indicator_scores_map[ic.indicator.name]
            score = _lookup_score(fc.file, scores, fc.function)
            raw_scores[ic.indicator.name] = score
            composite_importance += score * ic.weight

        composite_importance /= total_weight

        importance = max(min_importance, composite_importance)

        function_scores.append(
            FunctionScore(
                file=fc.file,
                function=fc.function,
                line_rate=fc.line_rate,
                lines_covered=fc.lines_covered,
                lines_total=fc.lines_total,
                importance=importance,
                weighted_contribution=fc.line_rate * importance,
                indicator_scores=raw_scores,
            )
        )

    total_importance = sum(fs.importance for fs in function_scores)
    if total_importance == 0:
        global_score = 0.0
    else:
        global_score = (
            sum(fs.line_rate * fs.importance for fs in function_scores)
            / total_importance
        )

    total_lines = sum(fc.lines_total for fc in functions)
    raw_coverage = (
        sum(fc.lines_covered for fc in functions) / total_lines
        if total_lines > 0
        else 0.0
    )

    function_scores.sort(key=lambda fs: fs.importance, reverse=True)

    return WeightedCoverageResult(
        global_score=round(global_score, 6),
        global_score_pct=round(global_score * 100, 2),
        raw_coverage=round(raw_coverage, 6),
        total_functions=len(function_scores),
        functions=function_scores,
        source_dirs=source_dirs,
        indicators=[ic.indicator.name for ic in indicator_configs],
    )


def _lookup_score(file_path: str, scores: dict[str, float], function: str = "") -> float:
    """Looks up the score of a function in a scores dict.

    Resolution order:
    1. Exact key ``file_path::function`` (per-symbol indicators).
    2. Exact key ``file_path`` alone (per-file indicators, backward compat).
    3. Suffix match on both forms (relative/absolute paths).
    """
    if function:
        exact_sym = f"{file_path}::{function}"
        if exact_sym in scores:
            return scores[exact_sym]

        for key, value in scores.items():
            if "::" in key:
                file_part, sym_part = key.rsplit("::", 1)
                if sym_part == function and (
                    file_part.endswith(file_path) or file_path.endswith(file_part)
                ):
                    return value

    if file_path in scores:
        return scores[file_path]

    for key, value in scores.items():
        if "::" not in key and (key.endswith(file_path) or file_path.endswith(key)):
            return value

    return 0.0
