"""Parses a coverage.xml report (Cobertura format) produced by pytest-cov.

Extracts per-function/method coverage as FunctionCoverage objects.

Strategy:
- If the report contains ``<method>`` elements, use them directly.
- Otherwise (standard pytest-cov case), read source files via ``ast`` to
  identify functions and their line ranges, then map annotated coverage lines
  in ``<line hits=...>`` to each function.
- If the source file cannot be found, return a single entry per file
  (minimum granularity).
"""

from __future__ import annotations

import ast
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FunctionCoverage:
    """Coverage of an individual function or method."""

    file: str
    """Relative path of the source file (as in coverage.xml)."""

    function: str
    """Qualified name of the function or method (e.g., ``MyClass.my_method``)."""

    line_rate: float
    """Coverage rate between 0.0 and 1.0."""

    lines_covered: int
    """Number of covered lines."""

    lines_total: int
    """Total number of executable lines."""


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
        return default


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
# Function extraction via AST
# ---------------------------------------------------------------------------

@dataclass
class _FuncRange:
    """Line range of a function in a source file."""

    name: str
    """Qualified name (``ClassName.method`` or ``function``)."""
    start: int
    end: int


class _FuncRangeVisitor(ast.NodeVisitor):
    """AST visitor that collects line ranges per function/method."""

    def __init__(self) -> None:
        self.ranges: list[_FuncRange] = []
        self._class_stack: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()

    def _visit_func(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        end = getattr(node, "end_lineno", node.lineno)
        if self._class_stack:
            name = f"{self._class_stack[-1]}.{node.name}"
        else:
            name = node.name
        self.ranges.append(_FuncRange(name=name, start=node.lineno, end=end))
        saved = self._class_stack[:]
        self._class_stack.clear()
        self.generic_visit(node)
        self._class_stack[:] = saved

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_func(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_func(node)


def _extract_function_ranges(source: str) -> list[_FuncRange]:
    """Extracts line ranges of each function/method via ast.

    Returns a list sorted by ascending ``start``.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    visitor = _FuncRangeVisitor()
    visitor.visit(tree)
    visitor.ranges.sort(key=lambda r: r.start)
    return visitor.ranges


def _assign_lines_to_functions(
    line_hits: dict[int, int],
    func_ranges: list[_FuncRange],
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

    func_covered: dict[str, int] = {r.name: 0 for r in func_ranges}
    func_total: dict[str, int] = {r.name: 0 for r in func_ranges}
    module_covered = 0
    module_total = 0

    for lineno, hits in line_hits.items():
        matched = False
        for r in func_ranges:
            if r.start <= lineno <= r.end:
                func_total[r.name] += 1
                if hits > 0:
                    func_covered[r.name] += 1
                matched = True
                break
        if not matched:
            module_total += 1
            if hits > 0:
                module_covered += 1

    results: list[FunctionCoverage] = []

    for r in func_ranges:
        total = func_total[r.name]
        covered = func_covered[r.name]
        rate = covered / total if total else 0.0
        results.append(
            FunctionCoverage(
                file=filename,
                function=r.name,
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
    candidates = [
        xml_dir / filename,
        *[root / filename for root in source_roots],
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def parse_coverage_xml(
    xml_path: str | Path,
    source_roots: list[str | Path] | None = None,
) -> list[FunctionCoverage]:
    """Parses a Cobertura coverage.xml file and returns per-function coverage.

    Args:
        xml_path: Path to the ``coverage.xml`` file.
        source_roots: Source root directories (used to locate .py files
            for analysis via ast). If ``None``, the parent directory of
            ``coverage.xml`` is used.
    """
    path = Path(xml_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"coverage.xml not found: {path}")

    xml_dir = path.parent
    roots: list[Path] = (
        [Path(r).resolve() for r in source_roots]
        if source_roots
        else [xml_dir]
    )

    tree = ET.parse(path)
    root = tree.getroot()

    results: list[FunctionCoverage] = []

    for package in root.iter("package"):
        for cls in package.iter("class"):
            filename = cls.get("filename", "<unknown>")

            # ── Case 1: report has <method> elements ─────────────────────
            methods_el = cls.find("methods")
            if methods_el is not None and len(methods_el) > 0:
                for method in methods_el.findall("method"):
                    func_name = method.get("name", "<unknown>")
                    line_rate = _safe_float(method.get("line-rate"))
                    covered, total = _count_lines_from_element(method)
                    if total == 0:
                        covered, total = (1, 1) if line_rate == 1.0 else (0, 1)
                    results.append(
                        FunctionCoverage(
                            file=filename,
                            function=func_name,
                            line_rate=line_rate,
                            lines_covered=covered,
                            lines_total=total,
                        )
                    )
                continue

            # ── Case 2: no <method> → parse source file via ast ────────────
            lines_el = cls.find("lines")
            line_hits: dict[int, int] = {}
            if lines_el is not None:
                for ln in lines_el.findall("line"):
                    lineno = _safe_int(ln.get("number"))
                    hits = _safe_int(ln.get("hits"))
                    if lineno > 0:
                        line_hits[lineno] = hits

            src_file = _find_source_file(filename, xml_dir, roots)
            if src_file is not None:
                try:
                    source = src_file.read_text(encoding="utf-8", errors="replace")
                    func_ranges = _extract_function_ranges(source)
                    results.extend(
                        _assign_lines_to_functions(line_hits, func_ranges, filename)
                    )
                    continue
                except OSError:
                    pass

            # ── Case 3: source file not found → file-level granularity ─────
            covered = sum(1 for h in line_hits.values() if h > 0)
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
