from pathlib import Path

import pytest

from better_cov.indicators.import_count import (
    ImportCountIndicator,
    _extract_symbol_imports_ast,
    _extract_symbol_imports_regex,
    _module_to_file_candidates,
)


def test_extract_symbol_imports_with_ast_ignores_plain_and_star_imports() -> None:
    """Verify AST extraction keeps named imports and ignores unsupported import forms."""
    source = """\
from package.module import first, second as alias
from package import *
import package.module
from . import relative
"""

    assert _extract_symbol_imports_ast(source) == [
        ("package.module", "first"),
        ("package.module", "second"),
    ]


def test_extract_symbol_imports_uses_regex_fallback_for_invalid_python() -> None:
    """Verify invalid Python uses the regex fallback and ignores wildcard imports."""
    source = "from package.module import first as alias, second\ndef broken(:\n"
    assert _extract_symbol_imports_ast(source) == [
        ("package.module", "first"),
        ("package.module", "second"),
    ]
    assert _extract_symbol_imports_regex("from package import *") == []


def test_module_to_file_candidates() -> None:
    """Verify dotted module names map to module and package file candidates."""
    assert _module_to_file_candidates("package.module") == [
        "package/module.py",
        "package/module/__init__.py",
    ]


def test_collect_python_files_supports_files_directories_and_ignores_other_paths(tmp_path) -> None:
    """Verify collection accepts Python files and directories while ignoring other paths."""
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    py_file = source_dir / "module.py"
    txt_file = source_dir / "notes.txt"
    py_file.write_text("", encoding="utf-8")
    txt_file.write_text("", encoding="utf-8")
    indicator = ImportCountIndicator()

    collected = indicator._collect_python_files(
        [str(py_file), str(source_dir), str(txt_file), str(tmp_path / "missing")]
    )

    assert py_file in collected
    assert collected.count(py_file) == 2
    assert txt_file not in collected


def test_build_file_index_preserves_first_match_for_duplicate_suffixes(tmp_path) -> None:
    """Verify duplicate suffixes keep their first entry while unique suffixes remain resolvable."""
    first = tmp_path / "first" / "common.py"
    second = tmp_path / "second" / "common.py"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text("", encoding="utf-8")
    second.write_text("", encoding="utf-8")
    indicator = ImportCountIndicator()

    index = indicator._build_file_index([first, second])

    assert index["common.py"] == str(first)
    assert index["first/common.py"] == str(first)
    assert index["second/common.py"] == str(second)


def test_resolve_module_to_file_checks_module_and_package_candidates(tmp_path) -> None:
    """Verify module resolution handles regular modules, packages, and unknown modules."""
    package_file = tmp_path / "package" / "__init__.py"
    module_file = tmp_path / "package" / "module.py"
    package_file.parent.mkdir()
    package_file.write_text("", encoding="utf-8")
    module_file.write_text("", encoding="utf-8")
    indicator = ImportCountIndicator()
    index = indicator._build_file_index([package_file, module_file])

    assert indicator._resolve_module_to_file("package.module", index) == str(module_file)
    assert indicator._resolve_module_to_file("package", index) == str(package_file)
    assert indicator._resolve_module_to_file("unknown", index) is None


def test_compute_counts_and_normalizes_imports(tmp_path) -> None:
    """Verify imports are counted per symbol and normalized against the maximum count."""
    source_dir = tmp_path / "src"
    package_dir = source_dir / "package"
    package_dir.mkdir(parents=True)
    (package_dir / "__init__.py").write_text("def exported():\n    pass\n", encoding="utf-8")
    (package_dir / "module.py").write_text(
        "def first():\n    pass\n\ndef second():\n    pass\n", encoding="utf-8"
    )
    (source_dir / "consumer.py").write_text(
        "from package.module import first, second\nfrom package.module import first\n"
        "from package import exported\n",
        encoding="utf-8",
    )

    result = ImportCountIndicator().compute([str(source_dir)])

    first_key = f"{package_dir / 'module.py'}::first"
    second_key = f"{package_dir / 'module.py'}::second"
    exported_key = f"{package_dir / '__init__.py'}::exported"
    assert result[first_key] == 1.0
    assert result[second_key] == 0.5
    assert result[exported_key] == 0.5


def test_indicator_name_and_empty_normalization() -> None:
    """Verify indicator identity, empty computation, and normalization edge cases."""
    indicator = ImportCountIndicator()
    assert indicator.name == "import_count"
    assert indicator.compute([]) == {}
    assert indicator._normalize({}) == {}
    assert indicator._normalize({"a": 0, "b": 0}) == {"a": 0.0, "b": 0.0}
    assert indicator._normalize({"a": 2, "b": 1}) == {"a": 1.0, "b": 0.5}


def test_compute_skips_unreadable_python_files(tmp_path, monkeypatch) -> None:
    """Verify unreadable Python files are skipped without failing the indicator."""
    source_file = tmp_path / "module.py"
    source_file.write_text("from other import value\n", encoding="utf-8")

    def fail_read_text(self, *args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "read_text", fail_read_text)
    assert ImportCountIndicator().compute([str(source_file)]) == {}


@pytest.mark.parametrize(
    ("module", "expected"),
    [("package.module", "package/module.py"), ("package", "package.py")],
)
def test_module_candidate_first_entry(module: str, expected: str) -> None:
    """Verify the first candidate maps each module name to its expected Python file."""
    assert _module_to_file_candidates(module)[0] == expected
