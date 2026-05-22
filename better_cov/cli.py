"""CLI entry point for better-cov.

Usage:
    # Shorthand: pass a project directory, coverage.xml and src/ are auto-detected
    python -m better_cov /path/to/project

    # Explicit:
    python -m better_cov \\
        --coverage-xml coverage.xml \\
        --source-dirs src/ tests/ \\
        --output better_cov.json \\
        [--min-score 80] \\
        [--top-n 10]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from better_cov.indicators.import_count import ImportCountIndicator
from better_cov.parsers.cobertura import parse_coverage_xml
from better_cov.reporter import export_json, export_markdown, print_report
from better_cov.scorer import IndicatorConfig, compute_weighted_coverage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="better_cov",
        description="Computes a coverage score weighted by function importance.",
    )
    parser.add_argument(
        "project_dir",
        nargs="?",
        default=None,
        metavar="PROJECT_DIR",
        help=(
            "Optional project root directory. When provided, --coverage-xml defaults to "
            "<PROJECT_DIR>/coverage.xml and --source-dirs defaults to <PROJECT_DIR>/src/."
        ),
    )
    parser.add_argument(
        "--coverage-xml",
        default="coverage.xml",
        metavar="PATH",
        help="Path to the coverage.xml file (default: coverage.xml)",
    )
    parser.add_argument(
        "--source-dirs",
        nargs="+",
        default=["src/"],
        metavar="DIR",
        help="Directories to scan for computing importance (default: src/)",
    )
    parser.add_argument(
        "--output",
        default="better_cov.json",
        metavar="PATH",
        help="Output JSON file (default: better_cov.json)",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=None,
        metavar="PCT",
        help=(
            "Minimum expected score in %%. "
            "If the computed score is lower, exit code 1 (useful in CI)."
        ),
    )
    parser.add_argument(
        "--min-importance",
        type=float,
        default=0.1,
        metavar="FLOAT",
        help=(
            "Minimum importance for functions not referenced "
            "by any indicator (default: 0.1)"
        ),
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=10,
        metavar="N",
        help="Number of functions to display in the console report (default: 10)",
    )
    parser.add_argument(
        "--markdown-output",
        default=None,
        metavar="PATH",
        help="Optional path to write a Markdown report (e.g. better_cov.md) for PR comments",
    )
    return parser


def _resolve_args(args: argparse.Namespace) -> argparse.Namespace:
    """Fills in coverage_xml and source_dirs from project_dir when not explicitly set."""
    if args.project_dir is None:
        return args
    root = Path(args.project_dir)
    parser = build_parser()
    defaults = parser.parse_args([])
    if args.coverage_xml == defaults.coverage_xml:
        candidate = root / "coverage.xml"
        args.coverage_xml = str(candidate)
    if args.source_dirs == defaults.source_dirs:
        direct = root / "src"
        if direct.is_dir():
            args.source_dirs = [str(direct)]
        else:
            found = sorted(str(p) for p in root.rglob("src") if p.is_dir())
            args.source_dirs = found if found else [str(direct)]
    return args


def main(argv: list[str] | None = None) -> int:
    """Main entry point. Returns the exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    args = _resolve_args(args)

    try:
        functions = parse_coverage_xml(args.coverage_xml, source_roots=args.source_dirs)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    if not functions:
        print(
            "Warning: no functions found in coverage.xml.",
            file=sys.stderr,
        )

    indicators = [
        IndicatorConfig(indicator=ImportCountIndicator(), weight=1.0),
    ]

    result = compute_weighted_coverage(
        functions=functions,
        indicator_configs=indicators,
        source_dirs=args.source_dirs,
        min_importance=args.min_importance,
    )

    print_report(result, top_n=args.top_n)
    export_json(result, args.output)
    print(f"  Result exported → {args.output}")

    if args.markdown_output is not None:
        export_markdown(result, args.markdown_output, top_n=args.top_n)
        print(f"  Markdown report → {args.markdown_output}")
    print()

    if args.min_score is not None and result.global_score_pct < args.min_score:
        print(
            f"  Score {result.global_score_pct:.1f}% < threshold {args.min_score:.1f}% → failure",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
