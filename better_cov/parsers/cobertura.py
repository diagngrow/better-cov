"""Parse Cobertura XML from pytest-cov, Jest, and Vitest.

Method-level rates are used when present. Otherwise, source-language adapters
extract function ranges and receive the class line hits. Missing or unreadable
sources fall back to Istanbul method hits and then file-level granularity.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

from better_cov.languages.base import FunctionRange
from better_cov.languages.python import PythonLanguageAdapter
from better_cov.languages.registry import detect_language_adapter
from better_cov.models import FunctionCoverage


def _safe_float(value: str | None, default: float = 0.0) -> float:
    """Converts a string to float, returns default on failure."""
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _safe_int(value: str | None, default: int = 0) -> int:
    """Converts a string to int, returns default on failure."""
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        try:
            numeric = float(value)
        except ValueError:
            return default
        return int(numeric) if numeric.is_integer() else default


def _count_lines_from_element(element: ET.Element) -> tuple[int, int]:
    """Counts covered and total lines from a <lines> element."""
    lines_el = element.find("lines")
    if lines_el is None:
        return 0, 0
    all_lines = lines_el.findall("line")
    total = len(all_lines)
    covered = sum(1 for ln in all_lines if _safe_int(ln.get("hits")) > 0)
    return covered, total


# ---------------------------------------------------------------------------
# Python compatibility helpers
# ---------------------------------------------------------------------------

_FuncRange = FunctionRange


def _extract_function_ranges(source: str) -> list[FunctionRange]:
    """Extracts Python function ranges through the language adapter."""
    return PythonLanguageAdapter().extract_function_ranges(source, ".py")


def _assign_lines_to_functions(
    line_hits: dict[int, int],
    func_ranges: list[FunctionRange],
    filename: str,
) -> list[FunctionCoverage]:
    """Associates each coverage line to the function containing it.

    Lines outside any function are grouped under ``<module>``.
    """
    if not func_ranges:
        covered = sum(1 for h in line_hits.values() if h > 0)
        total = len(line_hits)
        rate = covered / total if total else 0.0
        return [
            FunctionCoverage(
                file=filename,
                function="<module>",
                line_rate=rate,
                lines_covered=covered,
                lines_total=total,
            )
        ]

    func_covered = [0] * len(func_ranges)
    func_total = [0] * len(func_ranges)
    module_covered = 0
    module_total = 0

    for lineno, hits in line_hits.items():
        matches = [
            (index, function_range)
            for index, function_range in enumerate(func_ranges)
            if function_range.start <= lineno <= function_range.end
        ]
        if matches:
            index, _ = min(
                matches,
                key=lambda item: (item[1].end - item[1].start, -item[1].start),
            )
            func_total[index] += 1
            if hits > 0:
                func_covered[index] += 1
        else:
            module_total += 1
            if hits > 0:
                module_covered += 1

    results: list[FunctionCoverage] = []

    for index, function_range in enumerate(func_ranges):
        total = func_total[index]
        covered = func_covered[index]
        rate = covered / total if total else 0.0
        results.append(
            FunctionCoverage(
                file=filename,
                function=function_range.name,
                line_rate=rate,
                lines_covered=covered,
                lines_total=total,
            )
        )

    if module_total > 0:
        results.append(
            FunctionCoverage(
                file=filename,
                function="<module>",
                line_rate=module_covered / module_total,
                lines_covered=module_covered,
                lines_total=module_total,
            )
        )

    return results


def _find_source_file(
    filename: str,
    xml_dir: Path,
    source_roots: list[Path],
) -> Path | None:
    """Attempts to locate the source file from its Cobertura relative path."""
    normalized = Path(filename.replace("\\", "/"))
    candidates = [xml_dir / normalized]
    for root in source_roots:
        candidates.append(root / normalized)
        for position, part in enumerate(normalized.parts):
            if part == root.name and position + 1 < len(normalized.parts):
                candidates.append(root / Path(*normalized.parts[position + 1 :]))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _line_hits_from_element(element: ET.Element) -> dict[int, int]:
    """Return valid line numbers and hit counts from an element."""
    lines_el = element.find("lines")
    if lines_el is None:
        return {}
    line_hits: dict[int, int] = {}
    for line in lines_el.findall("line"):
        lineno = _safe_int(line.get("number"))
        if lineno > 0:
            line_hits[lineno] = _safe_int(line.get("hits"))
    return line_hits


def _coverage_from_methods(
    methods: list[ET.Element],
    filename: str,
) -> list[FunctionCoverage]:
    """Build method coverage, including Istanbul's hits-only variant."""
    results: list[FunctionCoverage] = []
    for method in methods:
        line_rate_attr = method.get("line-rate")
        covered, total = _count_lines_from_element(method)
        if line_rate_attr is None:
            hits = _safe_int(method.get("hits"))
            if total == 0:
                covered, total = (1, 1) if hits > 0 else (0, 1)
            line_rate = covered / total
        else:
            line_rate = _safe_float(line_rate_attr)
            if total == 0:
                if 0.0 < line_rate < 1.0:
                    fraction = Fraction(str(line_rate))
                    covered, total = fraction.numerator, fraction.denominator
                else:
                    covered, total = (1, 1) if line_rate >= 1.0 else (0, 1)
        results.append(
            FunctionCoverage(
                file=filename,
                function=method.get("name", "<unknown>"),
                line_rate=line_rate,
                lines_covered=covered,
                lines_total=total,
            )
        )
    return results


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def parse_coverage_xml(
    xml_path: str | Path,
    source_roots: list[str | Path] | None = None,
    language: str = "python",
) -> list[FunctionCoverage]:
    """Parses a Cobertura coverage.xml file and returns per-function coverage.

    Args:
        xml_path: Path to the ``coverage.xml`` file.
        source_roots: Source root directories used to locate source files.
            If ``None``, the parent directory of ``coverage.xml`` is used.
        language: Source language to use, or ``auto`` to detect by extension.
    """
    path = Path(xml_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"coverage.xml not found: {path}")

    xml_dir = path.parent
    tree = ET.parse(path)
    root = tree.getroot()
    roots = [Path(item).resolve() for item in source_roots] if source_roots else [xml_dir]
    for source in root.findall(".//sources/source"):
        if source.text and source.text.strip():
            candidate = Path(source.text.strip()).expanduser()
            roots.append((xml_dir / candidate).resolve() if not candidate.is_absolute() else candidate)

    results: list[FunctionCoverage] = []

    for package in root.iter("package"):
        for cls in package.iter("class"):
            filename = cls.get("filename", "<unknown>")
            methods_el = cls.find("methods")
            methods = methods_el.findall("method") if methods_el is not None else []
            if methods and all(method.get("line-rate") is not None for method in methods):
                results.extend(_coverage_from_methods(methods, filename))
                continue

            line_hits = _line_hits_from_element(cls)
            src_file = _find_source_file(filename, xml_dir, roots)
            adapter = detect_language_adapter(filename, language)
            if src_file is not None and adapter is not None:
                try:
                    source = src_file.read_text(encoding="utf-8", errors="replace")
                    func_ranges = adapter.extract_function_ranges(source, src_file.suffix.lower())
                    if func_ranges or not methods:
                        results.extend(
                            _assign_lines_to_functions(line_hits, func_ranges, filename)
                        )
                        continue
                except OSError:
                    pass

            if methods:
                results.extend(_coverage_from_methods(methods, filename))
                continue

            covered = sum(1 for hits in line_hits.values() if hits > 0)
            total = len(line_hits) or 1
            results.append(
                FunctionCoverage(
                    file=filename,
                    function="<module>",
                    line_rate=covered / total,
                    lines_covered=covered,
                    lines_total=total,
                )
            )

    return results
