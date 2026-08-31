"""Python source-language adapter."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from better_cov.languages.base import FunctionRange, ImportReference, LanguageAdapter

_FROM_IMPORT_RE = re.compile(r"^\s*from\s+([\w.]+)\s+import\s+(.+)$", re.MULTILINE)


class _FunctionRangeVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        """Initialize an empty function-range visitor."""
        self.ranges: list[FunctionRange] = []
        self._class_stack: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit a class and track its name for contained methods."""
        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Record a function range and visit nested functions."""
        end = getattr(node, "end_lineno", node.lineno)
        name = f"{self._class_stack[-1]}.{node.name}" if self._class_stack else node.name
        self.ranges.append(FunctionRange(name=name, start=node.lineno, end=end))
        saved = self._class_stack[:]
        self._class_stack.clear()
        self.generic_visit(node)
        self._class_stack[:] = saved

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit a synchronous function definition."""
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visit an asynchronous function definition."""
        self._visit_function(node)


def _extract_import_pairs_regex(source: str) -> list[tuple[str, str]]:
    """Extract from-import pairs with a regular-expression fallback."""
    pairs: list[tuple[str, str]] = []
    for match in _FROM_IMPORT_RE.finditer(source):
        module = match.group(1).strip()
        symbols = match.group(2).strip().strip("()")
        for symbol in symbols.split(","):
            symbol = symbol.strip().split(" as ")[0].strip()
            if symbol and symbol != "*":
                pairs.append((module, symbol))
    return pairs


def _extract_import_pairs(source: str) -> list[tuple[str, str]]:
    """Extract from-import pairs using the AST or regex fallback."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return _extract_import_pairs_regex(source)
    return [
        (node.module, alias.name)
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
        for alias in node.names
        if alias.name != "*"
    ]


class PythonLanguageAdapter(LanguageAdapter):
    @property
    def name(self) -> str:
        """Return the adapter's language name."""
        return "python"

    @property
    def extensions(self) -> frozenset[str]:
        """Return file extensions supported by the adapter."""
        return frozenset({".py"})

    def extract_function_ranges(self, source: str, suffix: str) -> list[FunctionRange]:
        """Extract function ranges from valid Python source."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []
        visitor = _FunctionRangeVisitor()
        visitor.visit(tree)
        visitor.ranges.sort(key=lambda item: item.start)
        return visitor.ranges

    def extract_imports(self, source: str, suffix: str) -> list[ImportReference]:
        """Extract imported symbols from Python source."""
        return [
            ImportReference(module=module, symbols=(symbol,))
            for module, symbol in _extract_import_pairs(source)
        ]

    def resolve_import(
        self,
        module: str,
        importer: Path,
        source_files: list[Path],
        source_dirs: list[Path],
    ) -> Path | None:
        """Resolve a Python module against the scanned source files."""
        candidates = (
            f"{module.replace('.', '/')}.py",
            f"{module.replace('.', '/')}/__init__.py",
        )
        index: dict[str, Path] = {}
        for source_file in source_files:
            normalized = str(source_file).replace("\\", "/")
            parts = normalized.split("/")
            for position in range(len(parts)):
                index.setdefault("/".join(parts[position:]), source_file)
        return next((index[candidate] for candidate in candidates if candidate in index), None)
