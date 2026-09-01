from better_cov.indicators.base import ImportanceIndicator
from better_cov.parsers.cobertura import FunctionCoverage
from better_cov.scorer import (
    IndicatorConfig,
    _lookup_score,
    compute_weighted_coverage,
)


class StaticIndicator(ImportanceIndicator):
    def __init__(self, indicator_name: str, scores: dict[str, float]) -> None:
        self._name = indicator_name
        self._scores = scores
        self.calls: list[list[str]] = []

    @property
    def name(self) -> str:
        return self._name

    def compute(self, source_dirs: list[str]) -> dict[str, float]:
        self.calls.append(source_dirs)
        return self._scores


def test_lookup_score_supports_symbol_and_file_path_variants() -> None:
    """Verify score lookup resolves exact and suffix-matched symbol and file keys."""
    assert _lookup_score("module.py", {"module.py::run": 0.8}, "run") == 0.8
    assert _lookup_score("src/module.py", {"module.py::run": 0.7}, "run") == 0.7
    assert _lookup_score("module.py", {"module.py": 0.6}, "run") == 0.6
    assert _lookup_score("src/module.py", {"module.py": 0.5}, "run") == 0.5
    assert _lookup_score("module.py", {}, "run") == 0.0


def test_compute_weighted_coverage_combines_indicators_and_raw_coverage() -> None:
    """Verify weighted coverage combines indicators, minimum importance, and raw coverage."""
    primary = StaticIndicator(
        "primary", {"module.py::hot": 1.0, "module.py::cold": 0.0}
    )
    secondary = StaticIndicator(
        "secondary", {"module.py::hot": 0.5, "module.py::cold": 1.0}
    )
    functions = [
        FunctionCoverage("module.py", "hot", 0.5, 1, 2),
        FunctionCoverage("module.py", "cold", 1.0, 2, 2),
    ]

    result = compute_weighted_coverage(
        functions,
        [IndicatorConfig(primary, weight=2.0), IndicatorConfig(secondary)],
        ["src"],
        min_importance=0.2,
    )

    assert primary.calls == [["src"]]
    assert secondary.calls == [["src"]]
    assert result.global_score == 0.642857
    assert result.global_score_pct == 64.29
    assert result.raw_coverage == 0.75
    assert result.total_functions == 2
    assert result.indicators == ["primary", "secondary"]
    assert [item.function for item in result.functions] == ["hot", "cold"]
    assert result.functions[0].importance == 0.8333333333333334
    assert result.functions[1].importance == 0.3333333333333333
    assert result.functions[0].indicator_scores == {"primary": 1.0, "secondary": 0.5}


def test_compute_weighted_coverage_handles_empty_functions() -> None:
    """Verify empty function input returns an empty result without evaluating indicators."""
    indicator = StaticIndicator("unused", {})
    result = compute_weighted_coverage([], [IndicatorConfig(indicator)], ["src"])

    assert result.global_score == 0.0
    assert result.global_score_pct == 0.0
    assert result.raw_coverage == 0.0
    assert result.total_functions == 0
    assert result.functions == []
    assert result.indicators == ["unused"]
    assert indicator.calls == []


def test_compute_weighted_coverage_handles_zero_total_importance_and_lines() -> None:
    """Verify zero importance and zero executable lines do not cause division errors."""
    result = compute_weighted_coverage(
        [FunctionCoverage("module.py", "empty", 0.0, 0, 0)],
        [],
        [],
        min_importance=0.0,
    )

    assert result.global_score == 0.0
    assert result.raw_coverage == 0.0
    assert result.functions[0].importance == 0.0


def test_compute_weighted_coverage_ignores_entries_without_measurable_lines() -> None:
    indicator = StaticIndicator(
        "importance",
        {
            "module.py::measured": 0.5,
            "module.py::empty": 1.0,
            "empty.py::<module>": 1.0,
        },
    )
    result = compute_weighted_coverage(
        [
            FunctionCoverage("module.py", "measured", 0.5, 1, 2),
            FunctionCoverage("module.py", "empty", 0.0, 0, 0),
            FunctionCoverage("empty.py", "<module>", 0.0, 0, 0),
        ],
        [IndicatorConfig(indicator)],
        ["src"],
    )

    assert result.global_score == 0.5
    assert result.global_score_pct == 50.0
    assert result.raw_coverage == 0.5
    assert result.total_functions == 3


def test_compute_weighted_coverage_applies_minimum_importance_without_indicators() -> None:
    """Verify functions without indicator scores receive the configured minimum importance."""
    result = compute_weighted_coverage(
        [FunctionCoverage("module.py", "run", 1.0, 1, 1)],
        [],
        ["src"],
        min_importance=0.25,
    )

    assert result.global_score == 1.0
    assert result.functions[0].importance == 0.25
