from pathlib import Path
from typing import NoReturn

from better_cov.indicators.import_count import ImportCountIndicator
from better_cov.languages.python import PythonLanguageAdapter

_FIXTURES = Path(__file__).parent / "fixtures"


def test_python_fallback_parses_imports_without_regex_backtracking() -> None:
    """Verify syntax-invalid Python still yields aliased and wildcard imports."""
    source = "from package.module import first as alias, second, *\ndef broken(:\n"

    references = PythonLanguageAdapter().extract_imports(source, ".py")

    assert [
        (reference.module, reference.symbols, reference.level)
        for reference in references
    ] == [
        ("package.module", ("first",), 0),
        ("package.module", ("second",), 0),
        ("package.module", ("*",), 0),
    ]


def test_compute_counts_and_normalizes_imports() -> None:
    """Verify imports are counted per symbol and normalized against the maximum count."""
    source_dir = _FIXTURES / "projects" / "python_project" / "src"
    package_dir = (source_dir / "package").resolve()

    result = ImportCountIndicator(language="python").compute([str(source_dir)])

    first_key = f"{package_dir / 'module.py'}::first"
    second_key = f"{package_dir / 'module.py'}::second"
    exported_key = f"{package_dir / '__init__.py'}::exported"
    assert result[first_key] == 1.0
    assert result[second_key] == 0.5
    assert result[exported_key] == 0.5


def test_compute_counts_javascript_named_imports() -> None:
    """Verify JavaScript named imports are resolved and normalized per symbol."""
    source_dir = _FIXTURES / "projects" / "javascript_imports" / "src"
    module = (source_dir / "module.js").resolve()

    result = ImportCountIndicator(language="javascript").compute([str(source_dir)])

    assert result[f"{module}::first"] == 1.0
    assert result[f"{module}::second"] == 0.5
    assert result[str(module)] == 0.5


def test_compute_resolves_typescript_paths_and_ignores_type_imports() -> None:
    """Verify TypeScript aliases resolve runtime symbols without type-only imports."""
    project = _FIXTURES / "projects" / "typescript_project"
    source_dir = project / "src"
    module = (source_dir / "lib" / "tool.ts").resolve()

    result = ImportCountIndicator(language="typescript").compute([str(project)])

    assert result == {f"{module}::run": 1.0}


def test_compute_counts_direct_and_relative_python_imports(tmp_path) -> None:
    """Verify direct modules and relative levels resolve from the importing file."""
    source_dir = tmp_path / "src"
    package = source_dir / "package"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "consumer.py").write_text(
        "import direct\nfrom . import sibling\nfrom ..shared import run\n",
        encoding="utf-8",
    )
    direct = source_dir / "direct.py"
    sibling = package / "sibling.py"
    shared = source_dir / "shared.py"
    direct.write_text("", encoding="utf-8")
    sibling.write_text("", encoding="utf-8")
    shared.write_text("def run():\n    pass\n", encoding="utf-8")

    result = ImportCountIndicator(language="python").compute([str(source_dir)])

    assert result == {
        str(direct.resolve()): 1.0,
        str(sibling.resolve()): 1.0,
        f"{shared.resolve()}::run": 1.0,
    }


def test_language_defaults_to_auto() -> None:
    """Verify callers can omit the source language for automatic detection."""
    assert ImportCountIndicator().language == "auto"


def test_indicator_name_and_empty_normalization() -> None:
    """Verify indicator identity, empty computation, and normalization edge cases."""
    indicator = ImportCountIndicator(language="python")
    assert indicator.name == "import_count"
    assert indicator.compute([]) == {}
    assert indicator._normalize({}) == {}
    assert indicator._normalize({"a": 0, "b": 0}) == {"a": 0.0, "b": 0.0}
    assert indicator._normalize({"a": 2, "b": 1}) == {"a": 1.0, "b": 0.5}


def test_compute_skips_unreadable_python_files(tmp_path, monkeypatch) -> None:
    """Verify unreadable Python files are skipped without failing the indicator."""
    source_file = tmp_path / "module.py"
    source_file.write_text("", encoding="utf-8")

    def fail_read_text(
        _self: Path,
        *_args: object,
        **_kwargs: object,
    ) -> NoReturn:
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "read_text", fail_read_text)
    assert ImportCountIndicator(language="python").compute([str(source_file)]) == {}
