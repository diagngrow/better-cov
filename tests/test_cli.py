import json
import runpy
import sys
import warnings
from pathlib import Path

import pytest

from better_cov import cli
from better_cov.cli import _resolve_args, build_parser, main

_FIXTURES = Path(__file__).parent / "fixtures"


def write_coverage_report(path, hits: tuple[int, int] = (1, 0)) -> None:
    path.write_text(
        f"""\
<coverage><packages><package><classes><class filename="app.py"><lines>
  <line number="1" hits="{hits[0]}"/><line number="2" hits="{hits[1]}"/>
  <line number="4" hits="0"/>
</lines></class></classes></package></packages></coverage>
""",
        encoding="utf-8",
    )


def test_build_parser_has_documented_defaults_and_options() -> None:
    """Verify the parser exposes documented defaults and accepts every supported option."""
    args = build_parser().parse_args([])
    assert args.project_dir is None
    assert args.coverage_xml == "coverage.xml"
    assert args.source_dirs == ["src/"]
    assert args.language == "auto"
    assert args.output == "better_cov.json"
    assert args.min_score is None
    assert args.min_importance == 0.1
    assert args.top_n == 10
    assert args.markdown_output is None

    args = build_parser().parse_args(
        [
            "project",
            "--coverage-xml",
            "report.xml",
            "--source-dirs",
            "one",
            "two",
            "--language",
            "javascript",
            "--output",
            "result.json",
            "--min-score",
            "80",
            "--min-importance",
            "0.2",
            "--top-n",
            "3",
            "--markdown-output",
            "report.md",
        ]
    )
    assert args.project_dir == "project"
    assert args.coverage_xml == "report.xml"
    assert args.source_dirs == ["one", "two"]
    assert args.language == "javascript"
    assert args.output == "result.json"
    assert args.min_score == 80.0
    assert args.min_importance == 0.2
    assert args.top_n == 3
    assert args.markdown_output == "report.md"


def test_resolve_args_uses_direct_project_src_directory(tmp_path) -> None:
    """Verify a direct project src directory supplies the default input paths."""
    (tmp_path / "src").mkdir()
    args = build_parser().parse_args([str(tmp_path)])

    resolved = _resolve_args(args)

    assert resolved.coverage_xml == str(tmp_path / "coverage.xml")
    assert resolved.source_dirs == [str(tmp_path / "src")]


def test_resolve_args_discovers_jest_vitest_cobertura_report(tmp_path) -> None:
    """Verify project resolution discovers the standard Istanbul report path."""
    (tmp_path / "src").mkdir()
    coverage_dir = tmp_path / "coverage"
    coverage_dir.mkdir()
    report = coverage_dir / "cobertura-coverage.xml"
    report.write_text("<coverage />", encoding="utf-8")

    resolved = _resolve_args(build_parser().parse_args([str(tmp_path)]))

    assert resolved.coverage_xml == str(report)


def test_resolve_args_finds_nested_src_directories(tmp_path) -> None:
    """Verify project resolution discovers src directories nested below the root."""
    nested_src = tmp_path / "packages" / "one" / "src"
    nested_src.mkdir(parents=True)
    (tmp_path / "node_modules" / "dependency" / "src").mkdir(parents=True)
    args = build_parser().parse_args([str(tmp_path)])

    resolved = _resolve_args(args)

    assert resolved.source_dirs == [str(nested_src)]


def test_resolve_args_preserves_explicit_paths_and_no_project_args() -> None:
    """Verify explicit paths remain unchanged and no-project arguments are untouched."""
    args = build_parser().parse_args([])
    assert _resolve_args(args) is args

    explicit = build_parser().parse_args(
        [
            "project",
            "--coverage-xml",
            "custom.xml",
            "--source-dirs",
            "custom-src",
        ]
    )
    resolved = _resolve_args(explicit)
    assert resolved.coverage_xml == "custom.xml"
    assert resolved.source_dirs == ["custom-src"]


def test_main_returns_two_for_missing_coverage_report(tmp_path, capsys) -> None:
    """Verify missing coverage input returns exit code 2 and reports an error."""
    code = main(["--coverage-xml", str(tmp_path / "missing.xml")])

    captured = capsys.readouterr()
    assert code == 2
    assert "Error: coverage.xml not found" in captured.err


def test_main_generates_json_and_markdown_reports(tmp_path, capsys) -> None:
    """Verify a pytest-cov report produces JSON and Markdown output."""
    project = _FIXTURES / "projects" / "python_project"
    source_dir = project / "src"
    coverage_path = project / "python-cobertura.xml"
    json_path = tmp_path / "output" / "better_cov.json"
    markdown_path = tmp_path / "output" / "better_cov.md"

    code = main(
        [
            "--coverage-xml",
            str(coverage_path),
            "--source-dirs",
            str(source_dir),
            "--output",
            str(json_path),
            "--markdown-output",
            str(markdown_path),
            "--top-n",
            "1",
        ]
    )

    captured = capsys.readouterr()
    assert code == 0
    assert "Weighted Coverage Report" in captured.out
    assert "Markdown report" in captured.out
    assert json.loads(json_path.read_text(encoding="utf-8"))["config"]["total_functions"] == 4
    assert "Weighted Coverage Report" in markdown_path.read_text(encoding="utf-8")


def test_main_auto_detects_jest_project_and_cobertura_report(tmp_path, capsys) -> None:
    """Verify project mode runs end to end on Jest Cobertura output."""
    project = _FIXTURES / "projects" / "javascript_project"
    output = tmp_path / "result.json"

    code = main([str(project), "--output", str(output)])

    assert code == 0
    assert "Weighted Coverage Report" in capsys.readouterr().out
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["config"]["total_functions"] == 1
    assert data["functions"][0]["file"] == "src/module.js"
    assert data["functions"][0]["function"] == "run"
    assert data["functions"][0]["line_rate"] == 0.75
    assert data["functions"][0]["importance"] == 1.0


def test_main_auto_detects_vitest_project_and_cobertura_report(tmp_path, capsys) -> None:
    """Verify project mode runs end to end on Vitest Cobertura output."""
    project = _FIXTURES / "projects" / "typescript_project"
    output = tmp_path / "result.json"

    code = main([str(project), "--output", str(output)])

    assert code == 0
    assert "Weighted Coverage Report" in capsys.readouterr().out
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["config"]["total_functions"] == 2
    assert data["functions"][0]["file"] == "src/lib/tool.ts"
    assert data["functions"][0]["function"] == "run"
    assert data["functions"][0]["line_rate"] == 0.5
    assert data["functions"][0]["importance"] == 1.0
    assert data["functions"][1]["function"] == "unused"
    assert data["functions"][1]["line_rate"] == 0.0


def test_main_returns_one_when_score_is_below_threshold(tmp_path, capsys) -> None:
    """Verify a score below the requested threshold returns exit code 1."""
    source_dir = _FIXTURES / "projects" / "python_cli_project" / "src"
    coverage_path = tmp_path / "coverage.xml"
    write_coverage_report(coverage_path)

    code = main(
        [
            "--coverage-xml",
            str(coverage_path),
            "--source-dirs",
            str(source_dir),
            "--output",
            str(tmp_path / "result.json"),
            "--min-score",
            "100",
        ]
    )

    captured = capsys.readouterr()
    assert code == 1
    assert "Score" in captured.err
    assert "threshold 100.0%" in captured.err


def test_main_warns_and_exports_when_report_contains_no_functions(tmp_path, capsys) -> None:
    """Verify an empty coverage report warns and still produces an empty result."""
    coverage_path = tmp_path / "coverage.xml"
    coverage_path.write_text("<coverage><packages /></coverage>", encoding="utf-8")
    output_path = tmp_path / "result.json"

    code = main(
        ["--coverage-xml", str(coverage_path), "--output", str(output_path)]
    )

    captured = capsys.readouterr()
    assert code == 0
    assert "Warning: no functions found" in captured.err
    assert json.loads(output_path.read_text(encoding="utf-8"))["config"]["total_functions"] == 0


def test_package_module_entrypoint_exits_with_cli_result(monkeypatch) -> None:
    """Verify the package entry point exits with the status returned by the CLI."""
    monkeypatch.setattr(cli, "main", lambda: 7)

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("better_cov", run_name="__main__")

    assert exc_info.value.code == 7


def test_cli_module_entrypoint_calls_main(monkeypatch, tmp_path) -> None:
    """Verify executing cli.py as a module propagates main's exit status."""
    monkeypatch.setattr(
        sys, "argv", ["better-cov", "--coverage-xml", str(tmp_path / "missing.xml")]
    )

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_module("better_cov.cli", run_name="__main__")

    assert exc_info.value.code == 2
