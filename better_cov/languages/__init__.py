"""Source-language adapters supported by better-cov."""

from better_cov.languages.base import FunctionRange, ImportReference, LanguageAdapter
from better_cov.languages.registry import (
    LANGUAGE_NAMES,
    detect_language_adapter,
    get_language_adapters,
)

__all__ = [
    "LANGUAGE_NAMES",
    "FunctionRange",
    "ImportReference",
    "LanguageAdapter",
    "detect_language_adapter",
    "get_language_adapters",
]
