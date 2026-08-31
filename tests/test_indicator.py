from pathlib import Path

import pytest

from better_cov.indicators.import_count import ImportCountIndicator

_FIXTURES = Path(__file__).parent / "fixtures"


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


def test_language_is_required() -> None:
    """Verify the source language must be selected explicitly."""
    with pytest.raises(TypeError):
        ImportCountIndicator()


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

    def fail_read_text(self, *args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "read_text", fail_read_text)
    assert ImportCountIndicator(language="python").compute([str(source_file)]) == {}
