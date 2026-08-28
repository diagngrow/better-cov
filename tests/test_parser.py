import xml.etree.ElementTree as ET

import pytest

from better_cov.parsers import cobertura
from better_cov.parsers.cobertura import FunctionCoverage, parse_coverage_xml


def test_safe_converters_use_defaults_for_missing_and_invalid_values() -> None:
    """Verify numeric converters use defaults for missing or malformed values."""
    assert cobertura._safe_float(None) == 0.0
    assert cobertura._safe_float("invalid", default=1.5) == 1.5
    assert cobertura._safe_float("2.5") == 2.5
    assert cobertura._safe_int(None) == 0
    assert cobertura._safe_int("invalid", default=3) == 3
    assert cobertura._safe_int("4") == 4


def test_count_lines_from_element_counts_positive_hits() -> None:
    """Verify positive hits are counted as covered and missing lines are handled safely."""
    element = ET.fromstring(
        "<method><lines><line hits='1'/><line hits='0'/><line hits='bad'/></lines></method>"
    )
    assert cobertura._count_lines_from_element(element) == (1, 3)
    assert cobertura._count_lines_from_element(ET.fromstring("<method/>")) == (0, 0)


def test_extract_function_ranges_handles_classes_async_and_nested_functions() -> None:
    """Verify AST extraction handles top-level, nested, class, and async functions."""
    source = """\
def top():
    def nested():
        return 1
    return nested()

class Worker:
    def run(self):
        return 2

async def wait():
    return 3
"""
    ranges = cobertura._extract_function_ranges(source)

    assert [(item.name, item.start, item.end) for item in ranges] == [
        ("top", 1, 4),
        ("nested", 2, 3),
        ("Worker.run", 7, 8),
        ("wait", 10, 11),
    ]
    assert cobertura._extract_function_ranges("def broken(:\n") == []


def test_assign_lines_to_functions_includes_module_lines() -> None:
    """Verify executable lines map to functions and remaining lines map to module coverage."""
    ranges = [cobertura._FuncRange(name="run", start=2, end=3)]
    results = cobertura._assign_lines_to_functions(
        {1: 1, 2: 1, 3: 0, 5: 0}, ranges, "module.py"
    )

    assert results == [
        FunctionCoverage("module.py", "run", 0.5, 1, 2),
        FunctionCoverage("module.py", "<module>", 0.5, 1, 2),
    ]


def test_assign_lines_without_functions_returns_module_entry() -> None:
    """Verify files without functions produce one module-level coverage entry."""
    results = cobertura._assign_lines_to_functions({1: 1, 2: 0}, [], "module.py")
    assert results == [FunctionCoverage("module.py", "<module>", 0.5, 1, 2)]


def test_find_source_file_checks_xml_directory_and_source_roots(tmp_path) -> None:
    """Verify source lookup checks the report directory before configured source roots."""
    xml_dir = tmp_path / "reports"
    source_root = tmp_path / "src"
    xml_dir.mkdir()
    source_root.mkdir()
    xml_file = xml_dir / "from-report.py"
    source_file = source_root / "from-root.py"
    xml_file.write_text("", encoding="utf-8")
    source_file.write_text("", encoding="utf-8")

    assert cobertura._find_source_file("from-report.py", xml_dir, [source_root]) == xml_file
    assert cobertura._find_source_file("from-root.py", xml_dir, [source_root]) == source_file
    assert cobertura._find_source_file("missing.py", xml_dir, [source_root]) is None


def test_parse_coverage_xml_rejects_missing_file(tmp_path) -> None:
    """Verify parsing raises a clear error for a missing coverage report."""
    with pytest.raises(FileNotFoundError, match="coverage.xml not found"):
        parse_coverage_xml(tmp_path / "coverage.xml")


def test_parse_coverage_xml_reads_method_level_reports(tmp_path) -> None:
    """Verify method-level Cobertura data is preferred with safe line fallbacks."""
    report = tmp_path / "coverage.xml"
    report.write_text(
        """\
<coverage>
  <packages><package><classes>
    <class filename="module.py">
      <methods>
        <method name="covered" line-rate="1.0">
          <lines><line number="1" hits="2"/><line number="2" hits="0"/></lines>
        </method>
        <method name="empty" line-rate="0.0" />
        <method name="full-without-lines" line-rate="1.0" />
      </methods>
    </class>
  </classes></package></packages>
</coverage>
""",
        encoding="utf-8",
    )

    result = parse_coverage_xml(report)

    assert result == [
        FunctionCoverage("module.py", "covered", 1.0, 1, 2),
        FunctionCoverage("module.py", "empty", 0.0, 0, 1),
        FunctionCoverage("module.py", "full-without-lines", 1.0, 1, 1),
    ]


def test_parse_coverage_xml_extracts_functions_with_ast(tmp_path) -> None:
    """Verify AST fallback extracts function coverage and preserves module-level lines."""
    source_root = tmp_path / "src"
    source_root.mkdir()
    (source_root / "module.py").write_text(
        """\
def alpha():
    return 1

class Worker:
    def beta(self):
        return 2

async def gamma():
    return 3

constant = 4
""",
        encoding="utf-8",
    )
    report = tmp_path / "coverage.xml"
    report.write_text(
        """\
<coverage><packages><package><classes><class filename="module.py"><lines>
  <line number="1" hits="1"/><line number="2" hits="1"/>
  <line number="5" hits="1"/><line number="6" hits="0"/>
  <line number="8" hits="0"/><line number="9" hits="0"/>
  <line number="11" hits="1"/>
</lines></class></classes></package></packages></coverage>
""",
        encoding="utf-8",
    )

    result = parse_coverage_xml(report, source_roots=[source_root])

    assert [(item.function, item.lines_covered, item.lines_total) for item in result] == [
        ("alpha", 2, 2),
        ("Worker.beta", 1, 2),
        ("gamma", 0, 2),
        ("<module>", 1, 1),
    ]
    assert result[1].line_rate == 0.5


def test_parse_coverage_xml_falls_back_to_file_level_when_source_is_missing(tmp_path) -> None:
    """Verify missing source files fall back to file-level coverage."""
    report = tmp_path / "coverage.xml"
    report.write_text(
        """\
<coverage><packages><package><classes><class filename="missing.py"><lines>
  <line number="1" hits="1"/><line number="2" hits="0"/>
</lines></class></classes></package></packages></coverage>
""",
        encoding="utf-8",
    )

    assert parse_coverage_xml(report) == [
        FunctionCoverage("missing.py", "<module>", 0.5, 1, 2)
    ]


def test_parse_coverage_xml_handles_malformed_attributes_and_empty_lines(tmp_path) -> None:
    """Verify malformed attributes and empty line sections use safe fallback values."""
    report = tmp_path / "coverage.xml"
    report.write_text(
        """\
<coverage><packages><package><classes>
  <class filename="module.py"><lines>
    <line number="bad" hits="1"/><line number="2" hits="bad"/>
  </lines></class>
  <class><lines /></class>
</classes></package></packages></coverage>
""",
        encoding="utf-8",
    )

    result = parse_coverage_xml(report)

    assert result == [
        FunctionCoverage("module.py", "<module>", 0.0, 0, 1),
        FunctionCoverage("<unknown>", "<module>", 0.0, 0, 1),
    ]


def test_parse_coverage_xml_falls_back_when_source_cannot_be_read(tmp_path, monkeypatch) -> None:
    """Verify unreadable source files fall back to file-level coverage."""
    source_root = tmp_path / "src"
    source_root.mkdir()
    source_file = source_root / "module.py"
    source_file.write_text("def run():\n    return 1\n", encoding="utf-8")
    report = tmp_path / "coverage.xml"
    report.write_text(
        """\
<coverage><packages><package><classes><class filename="module.py"><lines>
  <line number="1" hits="1"/><line number="2" hits="0"/>
</lines></class></classes></package></packages></coverage>
""",
        encoding="utf-8",
    )

    def fail_read_text(self, *args, **kwargs):
        if self == source_file:
            raise OSError("permission denied")
        raise AssertionError(f"unexpected read: {self}")

    monkeypatch.setattr(cobertura.Path, "read_text", fail_read_text)
    assert parse_coverage_xml(report, source_roots=[source_root]) == [
        FunctionCoverage("module.py", "<module>", 0.5, 1, 2)
    ]
