"""Registry and detection helpers for source-language adapters."""

from __future__ import annotations

from pathlib import Path

from better_cov.languages.base import LanguageAdapter
from better_cov.languages.javascript import JavaScriptLanguageAdapter
from better_cov.languages.python import PythonLanguageAdapter
from better_cov.languages.typescript import TypeScriptLanguageAdapter

LANGUAGE_NAMES = ("auto", "python", "javascript", "typescript")
_ADAPTERS: tuple[LanguageAdapter, ...] = (
    PythonLanguageAdapter(),
    JavaScriptLanguageAdapter(),
    TypeScriptLanguageAdapter(),
)


def get_language_adapters(language: str = "auto") -> list[LanguageAdapter]:
    """Return the adapters enabled by a CLI or API language selection."""
    if language == "auto":
        return list(_ADAPTERS)
    selected = [adapter for adapter in _ADAPTERS if adapter.name == language]
    if not selected:
        raise ValueError(f"Unsupported language: {language}")
    return selected


def detect_language_adapter(
    filename: str | Path,
    language: str = "auto",
) -> LanguageAdapter | None:
    """Select an adapter explicitly or from a source filename suffix."""
    adapters = get_language_adapters(language)
    if language != "auto":
        return adapters[0]
    suffix = Path(str(filename).replace("\\", "/")).suffix.lower()
    return next((adapter for adapter in adapters if suffix in adapter.extensions), None)
