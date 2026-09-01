"""Contracts shared by source-language adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class FunctionRange:
    """One executable function and its inclusive source line range."""

    name: str
    start: int
    end: int


@dataclass(frozen=True)
class ImportReference:
    """Symbols imported from a source module."""

    module: str
    symbols: tuple[str, ...] = ()
    level: int = 0


@lru_cache(maxsize=32)
def _cached_source_file_index(
    source_files: tuple[Path, ...],
    ignored_dirs: frozenset[str],
) -> dict[Path, Path]:
    """Build a normalized source-file index for a stable path collection."""
    files: dict[Path, Path] = {}
    for source in source_files:
        normalized = source.expanduser().resolve(strict=False)
        if not any(part.lower() in ignored_dirs for part in normalized.parts):
            files.setdefault(normalized, source)
    return files


def source_file_index(
    source_files: list[Path],
    ignored_dirs: frozenset[str] = frozenset(),
) -> dict[Path, Path]:
    """Reuse normalized source paths across repeated import resolutions."""
    return _cached_source_file_index(tuple(source_files), ignored_dirs)


class LanguageAdapter(ABC):
    """Source analysis and module resolution for one programming language."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable language name exposed by the CLI."""

    @property
    @abstractmethod
    def extensions(self) -> frozenset[str]:
        """File suffixes supported by this adapter."""

    @abstractmethod
    def extract_function_ranges(self, source: str, suffix: str) -> list[FunctionRange]:
        """Extract executable function ranges from source text."""

    @abstractmethod
    def extract_imports(self, source: str, suffix: str) -> list[ImportReference]:
        """Extract runtime imports from source text."""

    def extract_exports(self, source: str, suffix: str) -> dict[str, str]:
        """Map exported names to local symbol names."""
        return {}

    @abstractmethod
    def resolve_import(
        self,
        module: str,
        importer: Path,
        source_files: list[Path],
        source_dirs: list[Path],
    ) -> Path | None:
        """Resolve an imported module to one of the scanned source files."""
