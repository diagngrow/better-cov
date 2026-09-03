import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from better_cov.models import FunctionCoverage
from better_cov.parsers import cobertura
from better_cov.parsers.cobertura import parse_coverage_xml

_FIXTURES = Path(__file__).parent / "fixtures"


def test_safe_converters_use_defaults_for_missing_and_invalid_values() -> None:
    """Verify numeric converters use defaults for missing or malformed values."""
    assert cobertura._safe_float(None) == 0.0
    assert cobertura._safe_float("invalid", default=1.5) == 1.5
    assert cobertura._safe_float("2.5") == 2.5
    assert cobertura._safe_int(None) == 0
    assert cobertura._safe_int("invalid", default=3) == 3
    assert cobertura._safe_int("1.0") == 1
    assert cobertura._safe_int("1.5", default=3) == 3
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
    source = (_FIXTURES / "projects" / "python_project" / "src" / "function_forms.py").read_text(
        encoding="utf-8"
    )
    ranges = cobertura._extract_function_ranges(source)

    assert [(item.name, item.start, item.end) for item in ranges] == [
        ("top", 1, 4),
        ("nested", 2, 3),
        ("Worker.run", 7, 8),
        ("wait", 10, 11),
    ]
    invalid_source = (_FIXTURES / "sources" / "python" / "invalid_imports.txt").read_text(
        encoding="utf-8"
    )
    assert cobertura._extract_function_ranges(invalid_source) == []


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


def test_assign_lines_prefers_nested_ranges_and_keeps_duplicate_names() -> None:
    """Verify nested and duplicate function names keep independent coverage."""
    ranges = [
        cobertura._FuncRange(name="same", start=1, end=5),
        cobertura._FuncRange(name="inner", start=2, end=3),
        cobertura._FuncRange(name="same", start=10, end=10),
    ]

    results = cobertura._assign_lines_to_functions(
        {1: 1, 2: 0, 3: 1, 5: 0, 10: 1},
        ranges,
        "module.js",
    )

    assert results == [
        FunctionCoverage("module.js", "same", 0.5, 1, 2),
        FunctionCoverage("module.js", "inner", 0.5, 1, 2),
        FunctionCoverage("module.js", "same", 1.0, 1, 1),
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
    nested_root = tmp_path / "workspace" / "src"
    nested_root.mkdir(parents=True)
    nested_file = nested_root / "index.ts"
    ancestor_file = tmp_path / "outside.py"
    xml_file.write_text("", encoding="utf-8")
    source_file.write_text("", encoding="utf-8")
    nested_file.write_text("", encoding="utf-8")
    ancestor_file.write_text("", encoding="utf-8")

    assert cobertura._find_source_file("from-report.py", xml_dir, [source_root]) == xml_file
    assert cobertura._find_source_file("from-root.py", xml_dir, [source_root]) == source_file
    assert (
        cobertura._find_source_file(
            "packages/app/src/index.ts",
            xml_dir,
            [nested_root],
        )
        == nested_file
    )
    assert cobertura._find_source_file("outside.py", xml_dir, [source_root]) is None
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
        <method name="half-without-lines" line-rate="0.5" />
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
        FunctionCoverage("module.py", "half-without-lines", 0.5, 1, 2),
        FunctionCoverage("module.py", "full-without-lines", 1.0, 1, 1),
    ]


def test_parse_pytest_cov_report_extracts_functions_with_ast() -> None:
    """Verify a pytest-cov report maps coverage.py lines to Python functions."""
    project = _FIXTURES / "projects" / "python_project"
    source_root = project / "src"
    report = project / "python-cobertura.xml"

    result = parse_coverage_xml(report, source_roots=[source_root])

    assert result == [
        FunctionCoverage("src/module.py", "alpha", 1.0, 2, 2),
        FunctionCoverage("src/module.py", "Worker.beta", 1.0, 2, 2),
        FunctionCoverage("src/module.py", "gamma", 0.5, 1, 2),
        FunctionCoverage("src/module.py", "<module>", 1.0, 2, 2),
    ]


def test_parse_coverage_xml_falls_back_to_module_when_source_has_no_functions(
    tmp_path,
) -> None:
    """Verify a readable source without functions uses the module-level fallback."""
    source_root = tmp_path / "src"
    source_root.mkdir()
    (source_root / "module.py").write_text("value = 1\n", encoding="utf-8")
    report = tmp_path / "coverage.xml"
    report.write_text(
        """<coverage><packages><package><classes><class filename="module.py"><lines /></class>
</classes></package></packages></coverage>""",
        encoding="utf-8",
    )

    assert parse_coverage_xml(report, source_roots=[source_root]) == [
        FunctionCoverage("module.py", "<module>", 0.0, 0, 1)
    ]


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
    source_file.write_text("", encoding="utf-8")
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


def test_parse_jest_report_uses_javascript_ranges_for_istanbul_methods() -> None:
    """Verify a Jest report maps Istanbul class lines to JavaScript functions."""
    project = _FIXTURES / "projects" / "javascript_project"
    result = parse_coverage_xml(
        project / "coverage" / "cobertura-coverage.xml",
        source_roots=[project / "src"],
        language="javascript",
    )

    assert result == [FunctionCoverage("src/module.js", "run", 0.75, 3, 4)]


def test_parse_vitest_report_uses_typescript_ranges_for_istanbul_methods() -> None:
    """Verify a Vitest report maps remapped V8 lines to TypeScript functions."""
    project = _FIXTURES / "projects" / "typescript_project"
    result = parse_coverage_xml(
        project / "coverage" / "cobertura-coverage.xml",
        source_roots=[project / "src"],
        language="typescript",
    )

    assert result == [
        FunctionCoverage("src/lib/tool.ts", "run", 0.5, 1, 2),
        FunctionCoverage("src/lib/tool.ts", "unused", 0.0, 0, 1),
    ]


def test_parse_coverage_xml_uses_istanbul_hits_when_javascript_source_is_missing(
    tmp_path,
) -> None:
    """Verify missing JavaScript source falls back to binary method hits."""
    report = tmp_path / "coverage.xml"
    report.write_text(
        """\
<coverage><packages><package><classes><class filename="missing.js"><methods>
  <method name="covered" hits="2"><lines><line number="1" hits="2"/></lines></method>
  <method name="missed" hits="0"><lines><line number="4" hits="0"/></lines></method>
</methods></class></classes></package></packages></coverage>
""",
        encoding="utf-8",
    )

    assert parse_coverage_xml(report, language="javascript") == [
        FunctionCoverage("missing.js", "covered", 1.0, 1, 1),
        FunctionCoverage("missing.js", "missed", 0.0, 0, 1),
    ]
