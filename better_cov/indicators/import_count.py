"""Importance indicator based on source-level symbol imports."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from better_cov.indicators.base import ImportanceIndicator
from better_cov.languages.base import ImportReference, LanguageAdapter
from better_cov.languages.registry import detect_language_adapter, get_language_adapters


class ImportCountIndicator(ImportanceIndicator):
    """Compute importance from imports resolved by source-language adapters."""

    def __init__(self, language: str = "auto") -> None:
        self.language = language

    @property
    def name(self) -> str:
        return "import_count"

    def _count_reference(
        self,
        reference: ImportReference,
        adapter: LanguageAdapter,
        source_file: Path,
        source_files: list[Path],
        roots: list[Path],
        source_cache: dict[Path, str | None],
        export_cache: dict[tuple[Path, str], dict[str, str]],
        symbol_counts: dict[str, int],
    ) -> None:
        """Resolve one import reference and add its symbol counts."""
        module = f"{'.' * reference.level}{reference.module}"
        resolved = adapter.resolve_import(module, source_file, source_files, roots)
        if resolved is None:
            return
        if not reference.symbols:
            symbol_counts[self._path_key(resolved)] += 1
            return
        target_adapter = detect_language_adapter(resolved, "auto")
        exports = self._exports_for(resolved, target_adapter, source_cache, export_cache)
        for symbol in reference.symbols:
            key = self._path_key(resolved)
            if symbol != "*":
                key = f"{key}::{exports.get(symbol, symbol)}"
            symbol_counts[key] += 1

    def compute(self, source_dirs: list[str]) -> dict[str, float]:
        """Scan source directories and return normalized scores per symbol."""
        roots = [Path(source_dir).resolve() for source_dir in source_dirs]
        adapters = get_language_adapters(self.language)
        source_files = self._collect_source_files(roots, adapters)
        symbol_counts: dict[str, int] = defaultdict(int)
        source_cache: dict[Path, str | None] = {}
        export_cache: dict[tuple[Path, str], dict[str, str]] = {}
        for source_file in source_files:
            adapter = detect_language_adapter(source_file, self.language)
            source = self._read_source(source_file, source_cache) if adapter else None
            if adapter is None or source is None:
                continue
            for reference in adapter.extract_imports(source, source_file.suffix.lower()):
                self._count_reference(
                    reference, adapter, source_file, source_files, roots,
                    source_cache, export_cache, symbol_counts,
                )
        return self._normalize(dict(symbol_counts))

    def _collect_source_files(
        self,
        source_dirs: list[Path],
        adapters: list[LanguageAdapter],
    ) -> list[Path]:
        extensions = {suffix for adapter in adapters for suffix in adapter.extensions}
        files: list[Path] = []
        for base in source_dirs:
            if (
                base.is_file()
                and base.suffix.lower() in extensions
                and not self._is_ignored_path(base)
            ):
                files.append(base)
            elif base.is_dir():
                files.extend(
                    path
                    for path in base.rglob("*")
                    if path.is_file()
                    and path.suffix.lower() in extensions
                    and not self._is_ignored_path(path)
                )
        return files

    def _is_ignored_path(self, path: Path) -> bool:
        return any(part in {".git", ".venv", "node_modules"} for part in path.parts)

    def _read_source(
        self,
        source_file: Path,
        cache: dict[Path, str | None],
    ) -> str | None:
        if source_file not in cache:
            try:
                cache[source_file] = source_file.read_text(
                    encoding="utf-8",
                    errors="replace",
                )
            except OSError:
                cache[source_file] = None
        return cache[source_file]

    def _exports_for(
        self,
        source_file: Path,
        adapter: LanguageAdapter | None,
        source_cache: dict[Path, str | None],
        export_cache: dict[tuple[Path, str], dict[str, str]],
    ) -> dict[str, str]:
        if adapter is None:
            return {}
        key = (source_file, adapter.name)
        if key not in export_cache:
            source = self._read_source(source_file, source_cache)
            export_cache[key] = (
                adapter.extract_exports(source, source_file.suffix.lower())
                if source is not None
                else {}
            )
        return export_cache[key]

    def _path_key(self, source_file: Path) -> str:
        return str(source_file).replace("\\", "/")

    def _normalize(self, scores: dict[str, int]) -> dict[str, float]:
        """Normalize scores between zero and one."""
        if not scores:
            return {}
        max_score = max(scores.values())
        if max_score == 0:
            return dict.fromkeys(scores, 0.0)
        return {key: value / max_score for key, value in scores.items()}
