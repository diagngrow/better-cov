"""better-cov — Global coverage weighted by function importance."""

from better_cov.parsers.cobertura import FunctionCoverage, parse_coverage_xml
from better_cov.scorer import WeightedCoverageResult, compute_weighted_coverage

__all__ = [
    "FunctionCoverage",
    "WeightedCoverageResult",
    "compute_weighted_coverage",
    "parse_coverage_xml",
]
