"""
TypeScript parser: trích xuất exported functions, React components, custom hooks,
interfaces/types từ .ts và .tsx files.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional, Generator
import tree_sitter_typescript as tst
from tree_sitter import Language, Parser, Node

from schema import FunctionInfo, StructInfo, ModuleContext

TS_LANG  = Language(tst.language_typescript())
TSX_LANG = Language(tst.language_tsx())

_ts_parser  = Parser(TS_LANG)
_tsx_parser = Parser(TSX_LANG)


# ─── helpers ────────────────────────────────────────────────────────────────

def _text(node: Optional[Node], src: bytes) -> str:
    if node is None:
        return ""
    return src[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _walk(node: Node) -> Generator[Node, None, None]:
    yield node
    for child in node.children:
        yield from _walk(child)


def _first_child_of_type(node: Node, *types: str) -> Optional[Node]:
    return next((c for c in node.children if c.type in types), None)


def _extract_jsdoc(node: Node, src: bytes) -> Optional[str]:
    """Lấy /** JSDoc */ hoặc // comment đứng ngay trước node."""
    parent = node.parent
    if parent is None:
        return None
    siblings = parent.children
    idx = next((i for i, c in enumerate(siblings) if c.id == node.id), -1)
    if idx <= 0:
        return None
    sib = siblings[idx - 1]
    if sib.type in ("comment",):
        t = _text(sib, src).strip()
        # Strip /** */ or //
        if t.startswith("/**"):
            lines = t[3:-2].strip().splitlines()
            return " ".join(l.strip().lstrip("*").strip() for l in lines if l.strip().lstrip("*").strip())
        if t.startswith("//"):
            return t[2:].strip()
    return None


# ─── function / arrow function detection ────────────────────────────────────

def _is_exported(node: Node, src: bytes) -> bool:
    """Check if node is directly exported."""
    parent = node.parent
    if parent is None:
        return False
    if parent.type == "export_statement":
        return True
    # export const foo = ...
    if parent.type in ("variable_declarator",):
        gp = parent.parent
        if gp and gp.parent and gp.parent.type == "export_statement":
            return True
    return False


def _parse_ts_function(node: Node, src: bytes) -> Optional[FunctionInfo]:
    """Parse function_declaration hoặc lexical_declaration với arrow."""
    name = ""
    is_async = False
    params: list[str] = []
    ret_type: Optional[str] = None

    if node.type == "function_declaration":
        for c in node.children:
            if c.type == "async":
                is_async = True
            elif c.type == "identifier":
                name = _text(c, src)
            elif c.type == "formal_parameters":
                for p in c.children:
                    if p.type in ("required_parameter", "optional_parameter",
                                  "rest_parameter", "identifier"):
                        t = _text(p, src).strip()
                        if t and t not in ("(", ")", ","):
                            params.append(t)
            elif c.type == "type_annotation":
                # : ReturnType
                inner = src[c.start_byte + 1:c.end_byte].decode("utf-8", errors="replace").strip()
                ret_type = inner

    elif node.type in ("lexical_declaration", "variable_declaration"):
        # export const foo = async (...) => ...
        for decl in node.children:
            if decl.type == "variable_declarator":
                name_node = _first_child_of_type(decl, "identifier")
                if name_node:
                    name = _text(name_node, src)
                val = next((c for c in decl.children if c.type in
                            ("arrow_function", "function")), None)
                if val:
                    for c in val.children:
                        if c.type == "async":
                            is_async = True
                        elif c.type == "formal_parameters":
                            for p in c.children:
                                if p.type in ("required_parameter", "optional_parameter",
                                              "rest_parameter"):
                                    params.append(_text(p, src).strip())
                        elif c.type == "type_annotation":
                            ret_type = src[c.start_byte + 1:c.end_byte].decode("utf-8", errors="replace").strip()

    if not name:
        return None

    doc = _extract_jsdoc(node, src)
    return FunctionInfo(
        name=name,
        is_public=True,  # exported = public
        is_async=is_async,
        params=params,
        return_type=ret_type,
        doc_comment=doc,
        line=node.start_point[0] + 1,
    )


def _parse_ts_interface(node: Node, src: bytes) -> Optional[StructInfo]:
    """Parse interface_declaration hoặc type_alias_declaration."""
    name_node = _first_child_of_type(node, "type_identifier")
    if not name_node:
        return None
    name = _text(name_node, src)

    fields: list[str] = []
    body = _first_child_of_type(node, "object_type")
    if body:
        for child in body.children:
            if child.type in ("property_signature", "method_signature",
                              "index_signature", "call_signature"):
                fields.append(_text(child, src).strip().rstrip(";"))

    doc = _extract_jsdoc(node, src)
    return StructInfo(
        name=name,
        is_public=True,
        fields=fields,
        doc_comment=doc,
        derives=[],
    )


# ─── file parser ─────────────────────────────────────────────────────────────

def parse_ts_file(path: Path) -> tuple[list[FunctionInfo], list[StructInfo], list[str]]:
    """Returns (functions, interfaces, imports)."""
    src = path.read_bytes()
    is_tsx = path.suffix == ".tsx"
    parser = _tsx_parser if is_tsx else _ts_parser

    tree = parser.parse(src)
    functions: list[FunctionInfo] = []
    interfaces: list[StructInfo] = []
    imports: list[str] = []

    for node in _walk(tree.root_node):
        # exports
        if node.type == "export_statement":
            for child in node.children:
                if child.type == "function_declaration":
                    fn = _parse_ts_function(child, src)
                    if fn:
                        functions.append(fn)
                elif child.type in ("lexical_declaration", "variable_declaration"):
                    fn = _parse_ts_function(child, src)
                    if fn:
                        functions.append(fn)
                elif child.type == "interface_declaration":
                    iface = _parse_ts_interface(child, src)
                    if iface:
                        interfaces.append(iface)
                elif child.type == "type_alias_declaration":
                    iface = _parse_ts_interface(child, src)
                    if iface:
                        interfaces.append(iface)

        elif node.type == "import_statement":
            t = _text(node, src).strip()
            if t:
                imports.append(t)

    return functions, interfaces, imports


# ─── directory parser ────────────────────────────────────────────────────────

def parse_ts_directory(dir_path: Path, project_root: Path) -> ModuleContext:
    """Parse toàn bộ .ts/.tsx files trong một thư mục (không recursive)."""
    rel = str(dir_path.relative_to(project_root))
    ctx = ModuleContext(path=rel, language="typescript")

    ts_files = sorted(
        list(dir_path.glob("*.ts")) + list(dir_path.glob("*.tsx"))
    )
    for f in ts_files:
        ctx.source_files.append(str(f.relative_to(project_root)))
        fns, ifaces, imports = parse_ts_file(f)
        ctx.public_functions.extend(fns)
        ctx.structs.extend(ifaces)
        for imp in imports:
            if imp not in ctx.imports:
                ctx.imports.append(imp)

    return ctx
