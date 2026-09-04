"""Python source-language adapter."""

from __future__ import annotations

import ast
import keyword
from pathlib import Path

from better_cov.languages.base import (
    FunctionRange,
    ImportReference,
    LanguageAdapter,
    source_file_index,
)


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


def _from_import_reference(
    module: str,
    symbol: str,
    level: int,
) -> ImportReference:
    """Build a symbol or sibling-module reference from a from-import."""
    if module:
        return ImportReference(module, (symbol,), level)
    if symbol == "*":
        return ImportReference("", (symbol,), level)
    return ImportReference(symbol, level=level)


def _parse_import_module(raw_module: str) -> tuple[int, str] | None:
    """Return a relative-import level and module, or reject invalid syntax."""
    level = len(raw_module) - len(raw_module.lstrip("."))
    module = raw_module[level:]
    if not module:
        return (level, module) if level else None
    if any(
        not component.isidentifier() or keyword.iskeyword(component)
        for component in module.split(".")
    ):
        return None
    return level, module


def _clean_import_line(line: str) -> str:
    """Remove a Python comment from one import line."""
    return line.split("#", 1)[0].rstrip()


def _remove_line_continuation(line: str) -> str:
    """Remove a trailing explicit line-continuation marker."""
    return line[:-1].rstrip() if line.endswith("\\") else line


def _extract_import_pairs_fallback(source: str) -> list[ImportReference]:
    """Extract from-import references from syntax-invalid source."""
    references: list[ImportReference] = []
    lines = source.splitlines()
    line_index = 0
    while line_index < len(lines):
        line = _clean_import_line(lines[line_index])
        parts = line.lstrip().split(None, 3)
        if len(parts) != 4 or parts[0] != "from" or parts[2] != "import":
            line_index += 1
            continue
        parsed_module = _parse_import_module(parts[1])
        continued = parts[3].endswith("\\")
        raw_symbols = _remove_line_continuation(parts[3])
        balance = raw_symbols.count("(") - raw_symbols.count(")")
        while (balance > 0 or continued) and line_index + 1 < len(lines):
            line_index += 1
            continuation = _clean_import_line(lines[line_index])
            continued = continuation.endswith("\\")
            continuation = _remove_line_continuation(continuation)
            raw_symbols = f"{raw_symbols} {continuation}"
            balance += continuation.count("(") - continuation.count(")")
        if parsed_module is not None and balance <= 0 and not continued:
            level, module = parsed_module
            symbols = raw_symbols.strip().strip("()")
            for raw_symbol in symbols.split(","):
                symbol = raw_symbol.strip().split(" as ", 1)[0].strip()
                if symbol:
                    references.append(_from_import_reference(module, symbol, level))
        line_index += 1
    return references


def _extract_import_pairs(source: str) -> list[ImportReference]:
    """Extract import references using the AST or line-based fallback."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return _extract_import_pairs_fallback(source)
    references: list[ImportReference] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            references.extend(ImportReference(alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            references.extend(
                _from_import_reference(module, alias.name, node.level)
                for alias in node.names
            )
    return references


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
        return _extract_import_pairs(source)

    def resolve_import(
        self,
        module: str,
        importer: Path,
        source_files: list[Path],
        source_dirs: list[Path],
    ) -> Path | None:
        """Resolve a Python module against the scanned source files."""
        relative_level = len(module) - len(module.lstrip("."))
        module_name = module[relative_level:]
        if relative_level:
            target = importer.parent
            for _ in range(relative_level - 1):
                target = target.parent
            if module_name:
                target = target.joinpath(*module_name.split("."))
            files = source_file_index(source_files)
            candidates = (
                (target.with_suffix(".py"), target / "__init__.py")
                if module_name
                else (target / "__init__.py",)
            )
            return next(
                (
                    files[normalized]
                    for candidate in candidates
                    if (normalized := candidate.resolve(strict=False)) in files
                ),
                None,
            )
        candidates = (
            f"{module_name.replace('.', '/')}.py",
            f"{module_name.replace('.', '/')}/__init__.py",
        )
        index: dict[str, Path] = {}
        for source_file in source_files:
            normalized = str(source_file).replace("\\", "/")
            parts = normalized.split("/")
            for position in range(len(parts)):
                index.setdefault("/".join(parts[position:]), source_file)
        return next((index[candidate] for candidate in candidates if candidate in index), None)
