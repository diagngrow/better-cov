"""Importance indicator based on the number of imports of each function/symbol.

Counts occurrences of ``from module import symbol`` for each symbol
exported by source files. The score is normalized between 0.0 and 1.0.

Returned keys are in the format ``file_path::function_name``
(e.g., ``agent_audit_software/helpers.py::interrupt_response_to_text``)
to enable direct matching with ``FunctionCoverage``.
"""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from pathlib import Path

from better_cov.indicators.base import ImportanceIndicator


_FROM_IMPORT_RE = re.compile(
    r"^\s*from\s+([\w.]+)\s+import\s+(.+)$",
    re.MULTILINE,
)


def _extract_symbol_imports_ast(source: str) -> list[tuple[str, str]]:
    """Extracts (module, symbol) pairs from ``from module import symbol``.

    Returns a list of tuples ``(module_dotted, symbol_name)``.
    Simple ``import module`` statements are ignored (no specific symbol).
    """
    pairs: list[tuple[str, str]] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return _extract_symbol_imports_regex(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                if alias.name != "*":
                    pairs.append((node.module, alias.name))

    return pairs


def _extract_symbol_imports_regex(source: str) -> list[tuple[str, str]]:
    """Fallback regex when ast.parse fails."""
    pairs: list[tuple[str, str]] = []
    for match in _FROM_IMPORT_RE.finditer(source):
        module = match.group(1).strip()
        symbols_raw = match.group(2).strip().strip("()")
        for sym in symbols_raw.split(","):
            sym = sym.strip().split(" as ")[0].strip()
            if sym and sym != "*":
                pairs.append((module, sym))
    return pairs


def _module_to_file_candidates(module_name: str) -> list[str]:
    """Converts a Python module name to candidate file paths.

    Example: ``agent_audit_software.helpers`` →
    ``["agent_audit_software/helpers.py", "agent_audit_software/helpers/__init__.py"]``
    """
    parts = module_name.replace(".", "/")
    return [
        f"{parts}.py",
        f"{parts}/__init__.py",
    ]


class ImportCountIndicator(ImportanceIndicator):
    """Computes a function's importance based on how many times it is imported.

    How it works:
    1. Scans all .py files in ``source_dirs``.
    2. For each file, extracts ``from module import symbol`` via ast.
    3. Resolves ``module`` → relative source file path.
    4. Builds keys ``file_path::symbol_name`` and counts occurrences.
    5. Normalizes scores between 0.0 and 1.0 (max_count → 1.0).

    Returned keys (``file_path::symbol``) match the format
    ``FunctionCoverage.file + '::' + FunctionCoverage.function`` used
    by the scorer for resolution.
    """

    @property
    def name(self) -> str:
        return "import_count"

    def compute(self, source_dirs: list[str]) -> dict[str, float]:
        """Scans source_dirs and returns a score per function/symbol."""
        symbol_counts: dict[str, int] = defaultdict(int)

        py_files = self._collect_python_files(source_dirs)
        file_index = self._build_file_index(py_files)

        for py_file in py_files:
            try:
                source = py_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            for module, symbol in _extract_symbol_imports_ast(source):
                resolved = self._resolve_module_to_file(module, file_index)
                if resolved:
                    key = f"{resolved}::{symbol}"
                    symbol_counts[key] += 1

        return self._normalize(dict(symbol_counts))

    def _collect_python_files(self, source_dirs: list[str]) -> list[Path]:
        """Recursively collects all .py files in the given directories."""
        files: list[Path] = []
        for dir_str in source_dirs:
            base = Path(dir_str)
            if base.is_file() and base.suffix == ".py":
                files.append(base)
            elif base.is_dir():
                files.extend(base.rglob("*.py"))
        return files

    def _build_file_index(self, py_files: list[Path]) -> dict[str, str]:
        """Builds a suffix→relative_path index to resolve modules.

        For each known file, we store all possible suffixes
        (e.g., ``agent_audit_software/helpers.py``, ``helpers.py``).
        Returns a dict suffix → normalized_relative_path.
        """
        index: dict[str, str] = {}
        for f in py_files:
            f_str = str(f).replace("\\", "/")
            parts = f_str.split("/")
            for i in range(len(parts)):
                suffix = "/".join(parts[i:])
                if suffix not in index:
                    index[suffix] = f_str
        return index

    def _resolve_module_to_file(self, module: str, file_index: dict[str, str]) -> str | None:
        """Resolves a Python module name to a known relative file path."""
        for candidate in _module_to_file_candidates(module):
            if candidate in file_index:
                return file_index[candidate]
        return None

    def _normalize(self, scores: dict[str, int]) -> dict[str, float]:
        """Normalizes scores between 0.0 and 1.0."""
        if not scores:
            return {}
        max_score = max(scores.values())
        if max_score == 0:
            return {k: 0.0 for k in scores}
        return {k: v / max_score for k, v in scores.items()}
