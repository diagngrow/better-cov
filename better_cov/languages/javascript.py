from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import tree_sitter_javascript
from tree_sitter import Language, Node, Parser, Tree

from better_cov.languages.base import (
    FunctionRange,
    ImportReference,
    LanguageAdapter,
    source_file_index,
)

_JS_LANGUAGE = Language(tree_sitter_javascript.language())
_JS_EXTENSIONS = (".js", ".jsx", ".mjs", ".cjs")
_FUNCTIONS = {
    "arrow_function",
    "function_declaration",
    "function_expression",
    "generator_function",
    "generator_function_declaration",
    "method_definition",
}
_TYPE_CONTEXTS = {
    "ambient_declaration",
    "interface_declaration",
    "type_alias_declaration",
    "type_annotation",
    "type_arguments",
    "type_parameter",
    "type_parameters",
    "type_query",
}
_EXPORT_DEFAULT = "export default"
_TYPEOF_PREFIX = "typeof "
_TYPE_PREFIX = "type "


def _parse(source: str, language: Language = _JS_LANGUAGE) -> tuple[Tree, bytes]:
    """Parse source text with Tree-sitter."""
    data = source.encode("utf-8")
    return Parser(language).parse(data), data


def _text(node: Node | None, data: bytes) -> str:
    """Return node text, or an empty string for a missing node."""
    return "" if node is None else data[node.start_byte : node.end_byte].decode("utf-8")


def _nodes(root: Node) -> Iterator[Node]:
    """Iterate over a syntax tree's named nodes in source order."""
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(reversed(node.named_children))


def _string(node: Node | None, data: bytes) -> str:
    """Return a string or template literal without its delimiters."""
    value = _text(node, data)
    if len(value) >= 2 and value[0] in "'\"`" and value[-1] == value[0]:
        return value[1:-1]
    return value


def _field(node: Node, name: str) -> Node | None:
    """Return a named child field from a syntax node."""
    return node.child_by_field_name(name)


def _unique(values: list[str]) -> tuple[str, ...]:
    """Return non-empty values in first-seen order without duplicates."""
    return tuple(dict.fromkeys(value for value in values if value))


def _name(node: Node | None, data: bytes) -> str:
    """Return a node name without quote delimiters."""
    return _text(node, data).strip("'\"")


def _class_name(body: Node, data: bytes) -> str:
    """Resolve the name of a class body."""
    owner = body.parent
    if owner is None:
        return ""
    name = _text(_field(owner, "name"), data)
    if name:
        return name
    parent = owner.parent
    if parent is not None and parent.type == "variable_declarator":
        return _text(_field(parent, "name"), data)
    if parent is not None and parent.type == "assignment_expression":
        return _text(_field(parent, "left"), data)
    if parent is not None and parent.type == "export_statement" and _text(parent, data).lstrip().startswith(_EXPORT_DEFAULT):
        return "default"
    return ""


def _assigned_name(node: Node, data: bytes) -> str:
    """Resolve the name associated with a syntax node."""
    own = _name(_field(node, "name"), data)
    current = node
    parent = current.parent
    while parent is not None and parent.type in {
        "as_expression",
        "non_null_expression",
        "parenthesized_expression",
        "satisfies_expression",
        "type_assertion",
    }:
        current, parent = parent, parent.parent
    if parent is None:
        return own
    if parent.type == "variable_declarator" and _field(parent, "value") == current:
        return _name(_field(parent, "name"), data)
    if parent.type == "assignment_expression" and _field(parent, "right") == current:
        return _name(_field(parent, "left"), data)
    if parent.type == "pair" and _field(parent, "value") == current:
        return _name(_field(parent, "key"), data)
    if parent.type in {"field_definition", "public_field_definition"}:
        name = _name(_field(parent, "property") or _field(parent, "name"), data)
        body = parent.parent
        if body is not None and body.type == "class_body":
            owner = _class_name(body, data)
            return f"{owner}.{name}" if owner and name else name
        return name
    if parent.type == "export_statement" and "default" in _text(parent, data)[: node.start_byte - parent.start_byte]:
        return own or "default"
    return own


def _function_name(node: Node, data: bytes) -> str:
    """Resolve a function's display name from its syntax node."""
    if node.type in {"function_declaration", "generator_function_declaration"}:
        name = _text(_field(node, "name"), data)
        parent = node.parent
        if not name and parent is not None and parent.type == "export_statement" and _text(parent, data).lstrip().startswith(_EXPORT_DEFAULT):
            return "default"
        return name
    if node.type == "method_definition":
        name = _name(_field(node, "name"), data)
        parent = node.parent
        if parent is not None and parent.type == "class_body":
            owner = _class_name(parent, data)
            return f"{owner}.{name}" if owner and name else name
        return name
    return _assigned_name(node, data)


def _has_body(node: Node) -> bool:
    """Return whether a syntax node has a body field."""
    return _field(node, "body") is not None


def _ranges(tree: Tree, data: bytes) -> list[FunctionRange]:
    """Extract function ranges from a parsed source tree."""
    result: list[FunctionRange] = []
    for node in _nodes(tree.root_node):
        if node.type not in _FUNCTIONS or not _has_body(node):
            continue
        name = _function_name(node, data)
        if not name:
            continue
        end = node.end_point.row + (1 if node.end_point.column else 0)
        result.append(FunctionRange(name, node.start_point.row + 1, max(node.start_point.row + 1, end)))
    return result


def _is_type_context(node: Node) -> bool:
    """Return whether a call node appears in a type context."""
    parent = node.parent
    while parent is not None:
        if parent.type in _TYPE_CONTEXTS or parent.type.endswith("_type"):
            return True
        if parent.type in {"expression_statement", "export_statement", "program", "statement_block"}:
            return False
        parent = parent.parent
    return False


def _import_clause_symbols(
    clause: Node, data: bytes, typescript: bool
) -> tuple[tuple[str, ...], bool]:
    """Extract symbols from an import clause and report skipped type imports."""
    symbols: list[str] = []
    first = next(
        (child for child in clause.named_children if child.type in {"identifier", "type_identifier"}),
        None,
    )
    if first is not None:
        symbols.append("default")
    skipped_type = False
    for child in _nodes(clause):
        if child.type == "namespace_import":
            symbols.append("*")
            continue
        if child.type != "import_specifier":
            continue
        value = _text(child, data).lstrip()
        if typescript and value.startswith((_TYPE_PREFIX, _TYPEOF_PREFIX)):
            skipped_type = True
        else:
            symbols.append(_name(_field(child, "name"), data))
    return _unique(symbols), skipped_type


def _import_symbols(
    node: Node,
    data: bytes,
    *,
    typescript: bool,
) -> tuple[str, ...] | None:
    """Extract imported symbols from an import statement."""
    prefix = _text(node, data).lstrip()
    if typescript and prefix.startswith("import type"):
        return None
    require_clause = next(
        (child for child in node.named_children if child.type == "import_require_clause"),
        None,
    )
    if require_clause is not None:
        return ("default",)
    clause = next(
        (child for child in node.named_children if child.type == "import_clause"),
        None,
    )
    if clause is None:
        return ()
    symbols, skipped_type = _import_clause_symbols(clause, data, typescript)
    return None if skipped_type and not symbols else symbols


def _pattern_symbols(pattern: Node | None, data: bytes) -> tuple[str, ...]:
    """Extract symbols bound by a destructuring pattern."""
    if pattern is None:
        return ("*",)
    if pattern.type != "object_pattern":
        return ("default",)
    symbols: list[str] = []
    for node in pattern.named_children:
        if node.type in {"shorthand_property_identifier_pattern", "identifier"}:
            symbols.append(_text(node, data))
        elif node.type in {"pair_pattern", "pair"}:
            symbols.append(_name(_field(node, "key"), data))
        elif node.type == "assignment_pattern":
            symbols.append(_text(_field(node, "left"), data))
        elif node.type == "rest_pattern":
            symbols.append("*")
    return _unique(symbols)


def _call_module(node: Node, data: bytes) -> tuple[str, str] | None:
    """Return the module call kind and source module, if present."""
    function = _field(node, "function")
    kind = _text(function, data)
    if kind not in {"require", "import"}:
        return None
    arguments = _field(node, "arguments")
    if arguments is None:
        return None
    argument = next((child for child in arguments.named_children if child.type in {"string", "template_string"}), None)
    if argument is None:
        return None
    return kind, _string(argument, data)


def _call_symbols(node: Node, kind: str, data: bytes) -> tuple[str, ...]:
    """Extract symbols bound by a module call."""
    if kind == "import":
        return ("*",)
    parent = node.parent
    if parent is not None and parent.type == "member_expression" and _field(parent, "object") == node:
        return (_text(_field(parent, "property"), data),)
    while parent is not None and parent.type in {"parenthesized_expression", "await_expression"}:
        parent = parent.parent
    if parent is not None and parent.type == "variable_declarator":
        return _pattern_symbols(_field(parent, "name"), data)
    if parent is not None and parent.type == "assignment_expression":
        return _pattern_symbols(_field(parent, "left"), data)
    return ("*",)


def _reexport_symbols(
    node: Node,
    data: bytes,
    *,
    typescript: bool,
) -> tuple[str, ...] | None:
    """Extract symbols re-exported by an export statement."""
    text = _text(node, data).lstrip()
    if typescript and text.startswith("export type"):
        return None
    symbols: list[str] = []
    skipped_type = False
    for child in _nodes(node):
        if child.type == "export_specifier":
            value = _text(child, data).lstrip()
            if typescript and value.startswith((_TYPE_PREFIX, _TYPEOF_PREFIX)):
                skipped_type = True
                continue
            symbols.append(_name(_field(child, "name"), data))
        elif child.type == "namespace_export":
            symbols.append("*")
    if not symbols and "*" in text[: max(0, text.rfind("from"))]:
        symbols.append("*")
    return None if skipped_type and not symbols else _unique(symbols)


def _import_reference(
    node: Node, data: bytes, typescript: bool
) -> ImportReference | None:
    """Build an import reference from an import statement."""
    source = _field(node, "source")
    if source is None:
        require_clause = next(
            (child for child in node.named_children if child.type == "import_require_clause"),
            None,
        )
        source = _field(require_clause, "source") if require_clause is not None else None
    symbols = _import_symbols(node, data, typescript=typescript)
    return (
        ImportReference(_string(source, data), symbols)
        if source is not None and symbols is not None
        else None
    )


def _reexport_reference(
    node: Node, data: bytes, typescript: bool
) -> ImportReference | None:
    """Build an import reference from a re-export statement."""
    source = _field(node, "source")
    if source is None:
        return None
    symbols = _reexport_symbols(node, data, typescript=typescript)
    return ImportReference(_string(source, data), symbols) if symbols is not None else None


def _call_reference(node: Node, data: bytes) -> ImportReference | None:
    """Build an import reference from a dynamic or CommonJS call."""
    call = _call_module(node, data)
    if call is None:
        return None
    kind, module = call
    return ImportReference(module, _call_symbols(node, kind, data))


def _imports(
    tree: Tree,
    data: bytes,
    *,
    typescript: bool = False,
) -> list[ImportReference]:
    """Extract runtime imports and re-exports from a parsed source tree."""
    result: list[ImportReference] = []
    for node in _nodes(tree.root_node):
        reference = None
        if node.type == "import_statement":
            reference = _import_reference(node, data, typescript)
        elif node.type == "export_statement":
            reference = _reexport_reference(node, data, typescript)
        elif node.type == "call_expression" and not (typescript and _is_type_context(node)):
            reference = _call_reference(node, data)
        if reference is not None:
            result.append(reference)
    return result


def _declared_names(node: Node, data: bytes) -> list[str]:
    """Extract names declared by a declaration node."""
    name = _text(_field(node, "name"), data)
    if name:
        return [name]
    names: list[str] = []
    for child in node.named_children:
        if child.type == "variable_declarator":
            pattern = _field(child, "name")
            if pattern is not None and pattern.type in {"identifier", "type_identifier"}:
                names.append(_text(pattern, data))
    return names


_TYPE_DECLARATIONS = {
    "ambient_declaration",
    "function_signature",
    "interface_declaration",
    "type_alias_declaration",
}
_EXPORTABLE_VALUES = {"identifier", "function_expression", "generator_function", "arrow_function"}


def _export_specifiers(node: Node, data: bytes, typescript: bool) -> dict[str, str]:
    """Map named export specifiers to their local symbols."""
    exports: dict[str, str] = {}
    for child in _nodes(node):
        if child.type != "export_specifier":
            continue
        value = _text(child, data).lstrip()
        if typescript and value.startswith((_TYPE_PREFIX, _TYPEOF_PREFIX)):
            continue
        local = _name(_field(child, "name"), data)
        exported = _name(_field(child, "alias"), data) or local
        if exported and local:
            exports[exported] = local
    return exports


def _export_statement_map(node: Node, data: bytes, typescript: bool) -> dict[str, str]:
    """Map exports declared by one export statement."""
    text = _text(node, data).lstrip()
    if typescript and text.startswith("export type"):
        return {}
    declaration = _field(node, "declaration")
    if typescript and declaration is not None and declaration.type in _TYPE_DECLARATIONS:
        return {}
    exports = _export_specifiers(node, data, typescript)
    if declaration is not None:
        names = _declared_names(declaration, data)
        if text.startswith(_EXPORT_DEFAULT):
            exports["default"] = names[0] if names else "default"
        else:
            exports.update((name, name) for name in names)
    if declaration is None and text.startswith(_EXPORT_DEFAULT):
        value = _field(node, "value")
        is_identifier = value is not None and value.type in {"identifier", "type_identifier"}
        exports["default"] = _text(value, data) if is_identifier else "default"
    return exports


def _object_exports(node: Node, data: bytes) -> dict[str, str]:
    """Map properties of a CommonJS export object."""
    exports: dict[str, str] = {}
    for item in node.named_children:
        if item.type in {"shorthand_property_identifier", "identifier"}:
            name = _text(item, data)
            exports[name] = name
            continue
        if item.type != "pair":
            continue
        key = _text(_field(item, "key"), data).strip("'\"")
        value = _field(item, "value")
        if key and value is not None and value.type in _EXPORTABLE_VALUES:
            exports[key] = _text(value, data) if value.type == "identifier" else key
    return exports


def _assignment_exports(node: Node, data: bytes) -> dict[str, str]:
    """Map one CommonJS assignment to exported symbols."""
    left = _text(_field(node, "left"), data)
    right = _field(node, "right")
    if left == "module.exports":
        if right is not None and right.type == "object":
            return _object_exports(right, data)
        return {"default": _text(right, data) if right is not None and right.type == "identifier" else "default"}
    if left.startswith(("exports.", "module.exports.")):
        exported = left.rsplit(".", 1)[-1]
        local = _text(right, data) if right is not None and right.type == "identifier" else exported
        return {exported: local}
    return {}


def _export_map(
    tree: Tree,
    data: bytes,
    *,
    typescript: bool = False,
) -> dict[str, str]:
    """Map exported names to local names in a parsed source tree."""
    exports: dict[str, str] = {}
    for node in _nodes(tree.root_node):
        if node.type == "export_statement":
            exports.update(_export_statement_map(node, data, typescript))
        elif node.type == "assignment_expression":
            exports.update(_assignment_exports(node, data))
    return exports


def _resolve_relative(module: str, importer: Path, source_files: list[Path], extensions: tuple[str, ...]) -> Path | None:
    """Resolve a relative module against the scanned source files."""
    if not module.startswith("."):
        return None
    base = importer.parent / module
    candidates = [base]
    if not base.suffix:
        candidates.extend(base.with_suffix(extension) for extension in extensions)
        candidates.extend(base / f"index{extension}" for extension in extensions)
    files = source_file_index(source_files)
    for candidate in candidates:
        match = files.get(candidate.resolve())
        if match is not None:
            return match
    return None


class JavaScriptLanguageAdapter(LanguageAdapter):
    @property
    def name(self) -> str:
        """Stable language name exposed by the CLI."""
        return "javascript"

    @property
    def extensions(self) -> frozenset[str]:
        """File suffixes supported by this adapter."""
        return frozenset(_JS_EXTENSIONS)

    def _resolution_extensions(self) -> tuple[str, ...]:
        """Return extensions used for relative module resolution."""
        return _JS_EXTENSIONS

    def extract_function_ranges(self, source: str, suffix: str) -> list[FunctionRange]:
        """Extract executable function ranges from source text."""
        tree, data = _parse(source)
        return _ranges(tree, data)

    def extract_imports(self, source: str, suffix: str) -> list[ImportReference]:
        """Extract runtime imports from source text."""
        tree, data = _parse(source)
        return _imports(tree, data)

    def extract_exports(self, source: str, suffix: str) -> dict[str, str]:
        """Map exported names to local symbol names."""
        tree, data = _parse(source)
        return _export_map(tree, data)

    def resolve_import(
        self,
        module: str,
        importer: Path,
        source_files: list[Path],
        source_dirs: list[Path],
    ) -> Path | None:
        """Resolve an imported module to one of the scanned source files."""
        return _resolve_relative(module, importer, source_files, self._resolution_extensions())
