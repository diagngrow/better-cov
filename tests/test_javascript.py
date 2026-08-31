from __future__ import annotations

from pathlib import Path

from better_cov.languages.base import FunctionRange, ImportReference
from better_cov.languages.javascript import JavaScriptLanguageAdapter
from better_cov.languages.typescript import TypeScriptLanguageAdapter

_FIXTURES = Path(__file__).parent / "fixtures"


def _read_fixture(*parts: str) -> str:
    return (_FIXTURES.joinpath(*parts)).read_text(encoding="utf-8")


def test_javascript_function_ranges_cover_common_runtime_forms() -> None:
    """Extract declarations, assigned functions, methods, nesting, and JSX."""
    source = _read_fixture("sources", "javascript", "common_forms.jsx")

    assert JavaScriptLanguageAdapter().extract_function_ranges(source, ".jsx") == [
        FunctionRange("declared", 1, 3),
        FunctionRange("load", 5, 7),
        FunctionRange("identifiers", 9, 11),
        FunctionRange("doubled", 13, 15),
        FunctionRange("Worker.run", 18, 20),
        FunctionRange("Worker.build", 22, 24),
        FunctionRange("format", 28, 30),
        FunctionRange("normalize", 31, 33),
        FunctionRange("outer", 36, 41),
        FunctionRange("inner", 37, 39),
        FunctionRange("View", 43, 47),
    ]


def test_typescript_function_ranges_handle_types_generics_and_tsx() -> None:
    """Extract executable TS/TSX functions but not bodyless signatures."""
    source = _read_fixture("sources", "typescript", "function_forms.tsx")

    assert TypeScriptLanguageAdapter().extract_function_ranges(source, ".tsx") == [
        FunctionRange("identity", 7, 9),
        FunctionRange("select", 11, 13),
        FunctionRange("List", 16, 20),
        FunctionRange("Repository.get", 23, 25),
        FunctionRange("parse", 32, 34),
    ]


def test_javascript_extracts_esm_commonjs_and_dynamic_imports() -> None:
    """Track source symbols for ESM, CommonJS, reexports, and import()."""
    source = _read_fixture("sources", "javascript", "imports.js")

    assert JavaScriptLanguageAdapter().extract_imports(source, ".js") == [
        ImportReference("./esm", ("default", "named", "original")),
        ImportReference("./toolkit", ("*",)),
        ImportReference("./setup"),
        ImportReference("./fs", ("read", "write")),
        ImportReference("./config", ("value",)),
        ImportReference("./library", ("default",)),
        ImportReference("./side-effect", ("*",)),
        ImportReference("./lazy", ("*",)),
        ImportReference("./source", ("alpha", "beta")),
        ImportReference("./all", ("*",)),
        ImportReference("./namespace", ("*",)),
    ]


def test_typescript_ignores_type_only_imports_and_reexports() -> None:
    """Keep runtime TS dependencies while excluding type-only references."""
    source = _read_fixture("sources", "typescript", "imports.ts")

    assert TypeScriptLanguageAdapter().extract_imports(source, ".ts") == [
        ImportReference("./mixed", ("runtime",)),
        ImportReference("./factory", ("make",)),
        ImportReference("./runtime", ("*",)),
    ]


def test_javascript_extracts_default_alias_and_commonjs_exports() -> None:
    """Map ESM and CommonJS public names back to their local symbols."""
    source = _read_fixture("sources", "javascript", "exports.cjs")

    assert JavaScriptLanguageAdapter().extract_exports(source, ".cjs") == {
        "publicName": "local",
        "helper": "helper",
        "default": "local",
        "renamed": "local",
        "generated": "generated",
        "direct": "helper",
        "alias": "local",
    }


def test_typescript_exports_exclude_type_only_declarations() -> None:
    """Expose TS runtime values without treating type declarations as exports."""
    source = _read_fixture("sources", "typescript", "exports.ts")

    assert TypeScriptLanguageAdapter().extract_exports(source, ".ts") == {
        "value": "value",
        "renamed": "value",
        "default": "value",
    }


def test_relative_resolution_supports_extensions_and_directory_indexes(tmp_path) -> None:
    """Resolve extensionless sibling modules and package index files."""
    importer = tmp_path / "src" / "app.js"
    utility = tmp_path / "src" / "utility.js"
    feature_index = tmp_path / "src" / "feature" / "index.jsx"
    explicit = tmp_path / "src" / "config.mjs"
    source_files = [utility, feature_index, explicit]
    adapter = JavaScriptLanguageAdapter()

    assert adapter.resolve_import("./utility", importer, source_files, []) == utility
    assert adapter.resolve_import("./feature", importer, source_files, []) == feature_index
    assert adapter.resolve_import("./config.mjs", importer, source_files, []) == explicit
    assert adapter.resolve_import("external", importer, source_files, []) is None


def test_typescript_relative_resolution_prefers_ts_and_supports_js(tmp_path) -> None:
    """Resolve TS indexes first while allowing relative JavaScript modules."""
    importer = tmp_path / "src" / "app.ts"
    typed = tmp_path / "src" / "utility.ts"
    javascript = tmp_path / "src" / "utility.js"
    package_index = tmp_path / "src" / "feature" / "index.tsx"
    source_files = [javascript, typed, package_index]
    adapter = TypeScriptLanguageAdapter()

    assert adapter.resolve_import("./utility", importer, source_files, []) == typed
    assert adapter.resolve_import("./feature", importer, source_files, []) == package_index
