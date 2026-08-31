from __future__ import annotations

from pathlib import Path

import tree_sitter_typescript
from tree_sitter import Language

from better_cov.languages.base import ImportReference
from better_cov.languages.javascript import (
    _JS_EXTENSIONS,
    JavaScriptLanguageAdapter,
    _export_map,
    _imports,
    _parse,
)
from better_cov.languages.typescript_config import TypeScriptConfigResolver

_TS_LANGUAGE = Language(tree_sitter_typescript.language_typescript())
_TSX_LANGUAGE = Language(tree_sitter_typescript.language_tsx())
_TS_EXTENSIONS = (".ts", ".tsx", ".mts", ".cts")


class TypeScriptLanguageAdapter(JavaScriptLanguageAdapter):
    def __init__(self) -> None:
        """Initialize the TypeScript-aware module resolver."""
        self._resolver = TypeScriptConfigResolver()

    @property
    def name(self) -> str:
        """Return the stable language name used by the CLI."""
        return "typescript"

    @property
    def extensions(self) -> frozenset[str]:
        """Return supported TypeScript, TSX, and module extensions."""
        return frozenset(_TS_EXTENSIONS)

    def _language(self, suffix: str) -> Language:
        """Select TSX for `.tsx` files and TypeScript otherwise."""
        return _TSX_LANGUAGE if suffix.lower() == ".tsx" else _TS_LANGUAGE

    def _resolution_extensions(self) -> tuple[str, ...]:
        """Return TypeScript and JavaScript suffixes for import resolution."""
        return _TS_EXTENSIONS + _JS_EXTENSIONS

    def extract_imports(self, source: str, suffix: str) -> list[ImportReference]:
        """Extract runtime imports from TypeScript or TSX source."""
        tree, data = _parse(source, self._language(suffix))
        return _imports(tree, data, True)

    def extract_exports(self, source: str, suffix: str) -> dict[str, str]:
        """Extract exported names from TypeScript or TSX source."""
        tree, data = _parse(source, self._language(suffix))
        return _export_map(tree, data, True)

    def resolve_import(
        self,
        module: str,
        importer: Path,
        source_files: list[Path],
        source_dirs: list[Path],
    ) -> Path | None:
        """Resolve relative imports conventionally and aliases via TypeScript configuration."""
        if module.startswith("."):
            return super().resolve_import(module, importer, source_files, source_dirs)
        return self._resolver.resolve(module, importer, source_files, source_dirs)
